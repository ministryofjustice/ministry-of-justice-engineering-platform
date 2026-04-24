import logging
import json
import os
import urllib.error
import urllib.parse
import urllib.request


MINISTRYOFJUSTICE_GITHUB_ORGANIZATION_NAME = "ministryofjustice"
MINISTRYOFJUSTICE_GITHUB_ORGANIZATION_BASE_TEAM_NAME = "all-org-members"

MOJ_ANALYTICAL_SERVICES_GITHUB_ORGANIZATION_NAME = "moj-analytical-services"
MOJ_ANALYTICAL_SERVICES_GITHUB_ORGANIZATION_BASE_TEAM_NAME = "everyone"

API_BASE_URL = "https://api.github.com"
DEFAULT_LOGGING_LEVEL = "INFO"


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
        logging.info(
            f"Organization {self.organization_name}: {len(all_members)} org members, "
            f"{len(team_members)} team members, {len(missing_members)} missing"
        )

        for login in missing_members:
            self._put(
                f"/orgs/{self.organization_name}/teams/{team_slug}/memberships/{login}",
                {"role": "member"},
            )
            logging.info("Added %s to %s", login, team_slug)

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
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")

        request = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.github_token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "moj-engineering-platform-workflows",
            },
        )

        try:
            with urllib.request.urlopen(request) as response:
                response_body = response.read().decode("utf-8")
                parsed_body = json.loads(response_body) if response_body else {}
                return parsed_body, dict(response.headers.items())
        except urllib.error.HTTPError as error:
            details = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"GitHub API request failed: {method} {url} -> {error.code} {details}"
            ) from error

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