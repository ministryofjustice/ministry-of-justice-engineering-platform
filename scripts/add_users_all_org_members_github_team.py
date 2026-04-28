import logging
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


MINISTRYOFJUSTICE_GITHUB_ORGANIZATION_NAME = "ministryofjustice"
MINISTRYOFJUSTICE_GITHUB_ORGANIZATION_BASE_TEAM_NAME = "all-org-members"

MOJ_ANALYTICAL_SERVICES_GITHUB_ORGANIZATION_NAME = "moj-analytical-services"
MOJ_ANALYTICAL_SERVICES_GITHUB_ORGANIZATION_BASE_TEAM_NAME = "everyone"

API_BASE_URL = "https://api.github.com"
DEFAULT_LOGGING_LEVEL = "INFO"
DEFAULT_HTTP_TIMEOUT_SECONDS = 30


class GithubApiRequestError(RuntimeError):
    def __init__(
        self,
        method: str,
        url: str,
        status_code: int,
        response_body: Any,
    ) -> None:
        self.method = method
        self.url = url
        self.status_code = status_code
        self.response_body = response_body
        super().__init__(
            f"GitHub API request failed: {method} {url} -> {status_code} {response_body}"
        )


def configure_logging() -> None:
    logging_level = os.getenv("LOGGING_LEVEL", DEFAULT_LOGGING_LEVEL).upper()
    level = getattr(logging, logging_level, logging.INFO)
    logging.basicConfig(level=level, format="%(levelname)s %(message)s")


def get_environment_variables() -> tuple[str, str]:
    github_token = os.getenv("ADMIN_GITHUB_TOKEN")
    if not github_token:
        raise ValueError("The env variable ADMIN_GITHUB_TOKEN is empty or missing")

    github_organization_name = os.getenv("GITHUB_ORGANIZATION_NAME")
    if not github_organization_name:
        raise ValueError("The env variable GITHUB_ORGANIZATION_NAME is empty or missing")

    return github_token, github_organization_name


def get_config_for_organization(github_organization_name: str) -> tuple[str, str]:
    if github_organization_name == MINISTRYOFJUSTICE_GITHUB_ORGANIZATION_NAME:
        return (
            MINISTRYOFJUSTICE_GITHUB_ORGANIZATION_NAME,
            MINISTRYOFJUSTICE_GITHUB_ORGANIZATION_BASE_TEAM_NAME,
        )

    if github_organization_name == MOJ_ANALYTICAL_SERVICES_GITHUB_ORGANIZATION_NAME:
        return (
            MOJ_ANALYTICAL_SERVICES_GITHUB_ORGANIZATION_NAME,
            MOJ_ANALYTICAL_SERVICES_GITHUB_ORGANIZATION_BASE_TEAM_NAME,
        )

    raise ValueError(
        "Unsupported GitHub organization name "
        f"[{github_organization_name}]. Supported values are "
        f"{MINISTRYOFJUSTICE_GITHUB_ORGANIZATION_NAME} and "
        f"{MOJ_ANALYTICAL_SERVICES_GITHUB_ORGANIZATION_NAME}."
    )


class GithubTeamSyncService:
    def __init__(self, github_token: str, organization_name: str) -> None:
        self.github_token = github_token
        self.organization_name = organization_name

    def add_all_users_to_team(self, team_slug: str) -> None:
        all_members = self._get_paginated_logins(
            f"/orgs/{self.organization_name}/members",
        )
        team_members = self._get_paginated_logins(
            f"/orgs/{self.organization_name}/teams/{team_slug}/members",
        )

        missing_members = sorted(all_members - team_members)
        missing_2fa_members: list[str] = []
        logging.info(
            f"Organization {self.organization_name}: {len(all_members)} org members, "
            f"{len(team_members)} team members, {len(missing_members)} missing"
        )

        for login in missing_members:
            try:
                self._put(
                    f"/orgs/{self.organization_name}/teams/{team_slug}/memberships/{login}",
                    {"role": "member"},
                )
                logging.info("Added %s to %s", login, team_slug)
            except GithubApiRequestError as error:
                if self._is_user_missing_2fa(error):
                    missing_2fa_members.append(login)
                    logging.warning(
                        "Skipped %s due to org 2FA requirement", login
                    )
                    continue
                raise

        if missing_2fa_members:
            self._report_missing_2fa_users(team_slug, missing_2fa_members)

    def _get_paginated_logins(self, path: str) -> set[str]:
        next_url = self._build_url(path, {"per_page": 100})
        logins: set[str] = set()

        while next_url:
            body, headers = self._request("GET", next_url)
            for entry in body:
                login = entry.get("login")
                if login:
                    logins.add(login.lower())
            next_url = self._get_next_link(headers.get("Link"))

        return logins

    def _put(self, path: str, payload: dict[str, str]) -> None:
        url = self._build_url(path)
        self._request("PUT", url, payload)

    def _request(
        self,
        method: str,
        url: str,
        payload: dict[str, str] | None = None,
    ) -> tuple[object, dict[str, str]]:
        data = None
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.github_token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "moj-engineering-platform-workflows",
        }

        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers=headers,
        )

        try:
            with urllib.request.urlopen(
                request, timeout=DEFAULT_HTTP_TIMEOUT_SECONDS
            ) as response:
                response_body = response.read().decode("utf-8")
                parsed_body = json.loads(response_body) if response_body else {}
                return parsed_body, dict(response.headers.items())
        except urllib.error.HTTPError as error:
            details = error.read().decode("utf-8", errors="replace")
            try:
                parsed_details: Any = json.loads(details)
            except json.JSONDecodeError:
                parsed_details = details
            raise GithubApiRequestError(
                method=method,
                url=url,
                status_code=error.code,
                response_body=parsed_details,
            ) from error

    @staticmethod
    def _is_user_missing_2fa(error: GithubApiRequestError) -> bool:
        if error.status_code != 422:
            return False

        body = error.response_body
        if not isinstance(body, dict):
            return False

        errors = body.get("errors")
        if not isinstance(errors, list):
            return False

        for entry in errors:
            if isinstance(entry, dict) and entry.get("code") == "no_2fa":
                return True

        return False

    def _report_missing_2fa_users(self, team_slug: str, users: list[str]) -> None:
        users_sorted = sorted(users)
        users_csv = ", ".join(users_sorted)
        logging.warning(
            "Skipped %d users for team %s due to org 2FA requirement: %s",
            len(users_sorted),
            team_slug,
            users_csv,
        )

        # Emit a visible annotation in the workflow logs.
        print(
            "::warning title=Users skipped (2FA required)::"
            f"{len(users_sorted)} users were skipped: {users_csv}"
        )

        # Add a run summary section visible in the GitHub Actions UI.
        summary_path = os.getenv("GITHUB_STEP_SUMMARY")
        if not summary_path:
            return

        with open(summary_path, "a", encoding="utf-8") as summary_file:
            summary_file.write("### Users skipped due to missing 2FA\n\n")
            summary_file.write(
                f"Team: `{team_slug}` in `{self.organization_name}`.\n\n"
            )
            for user in users_sorted:
                summary_file.write(f"- `{user}`\n")
            summary_file.write("\n")

    @staticmethod
    def _build_url(path: str, params: dict[str, int] | None = None) -> str:
        if not params:
            return f"{API_BASE_URL}{path}"
        return f"{API_BASE_URL}{path}?{urllib.parse.urlencode(params)}"

    @staticmethod
    def _get_next_link(link_header: str | None) -> str | None:
        if not link_header:
            return None

        for part in link_header.split(","):
            sections = [section.strip() for section in part.split(";")]
            if len(sections) < 2:
                continue
            if sections[1] == 'rel="next"':
                return sections[0].strip("<>")
        return None


def main() -> None:
    configure_logging()
    github_token, github_organization_name = get_environment_variables()
    organization_name, organization_team_name = get_config_for_organization(
        github_organization_name
    )
    GithubTeamSyncService(github_token, organization_name).add_all_users_to_team(
        organization_team_name
    )


if __name__ == "__main__":
    main()