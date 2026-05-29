import io
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from scripts.add_users_all_org_members_github_team import (
    GithubApiRequestError,
    GithubTeamSyncService,
    get_config_for_organization,
    get_environment_variables,
    write_added_users_output,
)


class FakeResponse:
    # Minimal response object for mocking urllib context-manager responses.
    def __init__(self, body: str, headers: dict[str, str] | None = None) -> None:
        self._body = body
        self.headers = headers or {}

    def read(self) -> bytes:
        return self._body.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        return None


class TestEnvironmentVariables(unittest.TestCase):
    # Validate fail-fast behavior for required runtime environment variables.
    def test_get_environment_variables_returns_values(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "ADMIN_GITHUB_TOKEN": "token123",
                "GITHUB_ORGANIZATION_NAME": "ministryofjustice",
            },
            clear=True,
        ):
            token, organization = get_environment_variables()

        self.assertEqual(token, "token123")
        self.assertEqual(organization, "ministryofjustice")

    def test_get_environment_variables_requires_token(self) -> None:
        with patch.dict(
            "os.environ", {"GITHUB_ORGANIZATION_NAME": "ministryofjustice"}, clear=True
        ):
            with self.assertRaises(ValueError) as context:
                get_environment_variables()

        self.assertIn("ADMIN_GITHUB_TOKEN", str(context.exception))

    def test_get_environment_variables_requires_organization(self) -> None:
        with patch.dict("os.environ", {"ADMIN_GITHUB_TOKEN": "token123"}, clear=True):
            with self.assertRaises(ValueError) as context:
                get_environment_variables()

        self.assertIn("GITHUB_ORGANIZATION_NAME", str(context.exception))


class TestOrganizationConfig(unittest.TestCase):
    # Guard organization-to-team mapping used by the sync entrypoint.
    def test_get_config_for_moj(self) -> None:
        org, team = get_config_for_organization("ministryofjustice")
        self.assertEqual(org, "ministryofjustice")
        self.assertEqual(team, "all-org-members")

    def test_get_config_for_mojas(self) -> None:
        org, team = get_config_for_organization("moj-analytical-services")
        self.assertEqual(org, "moj-analytical-services")
        self.assertEqual(team, "everyone")

    def test_get_config_raises_for_unsupported_org(self) -> None:
        with self.assertRaises(ValueError) as context:
            get_config_for_organization("unknown-org")

        self.assertIn("Unsupported GitHub organization name", str(context.exception))


class TestHelpers(unittest.TestCase):
    # Helper methods are pure and cheap to test directly.
    def test_build_url_without_params(self) -> None:
        url = GithubTeamSyncService._build_url("/orgs/moj/members")
        self.assertEqual(url, "https://api.github.com/orgs/moj/members")

    def test_build_url_with_params(self) -> None:
        url = GithubTeamSyncService._build_url("/orgs/moj/members", {"per_page": 100})
        self.assertEqual(url, "https://api.github.com/orgs/moj/members?per_page=100")

    def test_get_next_link_returns_next_url(self) -> None:
        header = '<https://api.github.com/page2>; rel="next", <https://api.github.com/page4>; rel="last"'
        self.assertEqual(
            GithubTeamSyncService._get_next_link(header), "https://api.github.com/page2"
        )

    def test_get_next_link_returns_none_without_next(self) -> None:
        header = '<https://api.github.com/page4>; rel="last"'
        self.assertIsNone(GithubTeamSyncService._get_next_link(header))

    def test_is_user_missing_2fa_true(self) -> None:
        error = GithubApiRequestError(
            method="PUT",
            url="https://api.github.com/example",
            status_code=422,
            response_body={"errors": [{"code": "no_2fa"}]},
        )
        self.assertTrue(GithubTeamSyncService._is_user_missing_2fa(error))

    def test_is_user_missing_2fa_false_for_other_error(self) -> None:
        error = GithubApiRequestError(
            method="PUT",
            url="https://api.github.com/example",
            status_code=422,
            response_body={"errors": [{"code": "different_error"}]},
        )
        self.assertFalse(GithubTeamSyncService._is_user_missing_2fa(error))

    def test_is_user_missing_2fa_false_for_non_422(self) -> None:
        error = GithubApiRequestError(
            method="PUT",
            url="https://api.github.com/example",
            status_code=500,
            response_body={"errors": [{"code": "no_2fa"}]},
        )
        self.assertFalse(GithubTeamSyncService._is_user_missing_2fa(error))


class TestRequestAndPagination(unittest.TestCase):
    def setUp(self) -> None:
        self.service = GithubTeamSyncService("token123", "ministryofjustice")

    @patch("urllib.request.urlopen")
    def test_request_success_returns_body_and_headers(self, mock_urlopen) -> None:
        mock_urlopen.return_value = FakeResponse(
            body='[{"login": "alpha"}]',
            headers={"Link": '<https://api.github.com/page2>; rel="next"'},
        )

        body, headers = self.service._request("GET", "https://api.github.com/test")

        self.assertEqual(body, [{"login": "alpha"}])
        self.assertEqual(headers["Link"], '<https://api.github.com/page2>; rel="next"')

    @patch("urllib.request.urlopen")
    def test_request_http_error_with_json_body(self, mock_urlopen) -> None:
        # GitHub API often returns structured JSON errors; preserve that structure.
        error = HTTPError(
            url="https://api.github.com/test",
            code=422,
            msg="unprocessable",
            hdrs={},
            fp=io.BytesIO(b'{"errors":[{"code":"no_2fa"}]}'),
        )
        mock_urlopen.side_effect = error

        with self.assertRaises(GithubApiRequestError) as context:
            self.service._request("PUT", "https://api.github.com/test", {"role": "member"})

        self.assertEqual(context.exception.status_code, 422)
        self.assertEqual(
            context.exception.response_body,
            {"errors": [{"code": "no_2fa"}]},
        )

    @patch("urllib.request.urlopen")
    def test_request_http_error_with_text_body(self, mock_urlopen) -> None:
        # Some failures may return plain text; ensure we still surface useful details.
        error = HTTPError(
            url="https://api.github.com/test",
            code=500,
            msg="server_error",
            hdrs={},
            fp=io.BytesIO(b"server down"),
        )
        mock_urlopen.side_effect = error

        with self.assertRaises(GithubApiRequestError) as context:
            self.service._request("GET", "https://api.github.com/test")

        self.assertEqual(context.exception.status_code, 500)
        self.assertEqual(context.exception.response_body, "server down")

    @patch.object(GithubTeamSyncService, "_request")
    @patch.object(GithubTeamSyncService, "_get_next_link")
    def test_get_paginated_logins_aggregates_across_pages(
        self, mock_get_next_link, mock_request
    ) -> None:
        # Mixed-case usernames should collapse to a unique lowercase set.
        mock_request.side_effect = [
            ([{"login": "Alice"}, {"login": "bob"}], {"Link": "header1"}),
            ([{"login": "ALICE"}, {"login": "charlie"}], {"Link": "header2"}),
        ]
        mock_get_next_link.side_effect = ["https://api.github.com/page2", None]

        users = self.service._get_paginated_logins("/orgs/moj/members")

        self.assertEqual(users, {"alice", "bob", "charlie"})


class TestTeamSyncBehaviour(unittest.TestCase):
    # These tests focus on branch behavior in add_all_users_to_team.
    def setUp(self) -> None:
        self.service = GithubTeamSyncService("token123", "ministryofjustice")

    @patch.object(GithubTeamSyncService, "_get_paginated_logins")
    @patch.object(GithubTeamSyncService, "_put")
    @patch.object(GithubTeamSyncService, "_report_missing_2fa_users")
    def test_add_all_users_adds_only_missing_members(
        self,
        mock_report_missing_2fa,
        mock_put,
        mock_get_paginated,
    ) -> None:
        # First call returns org members, second returns existing team members.
        mock_get_paginated.side_effect = [
            {"alice", "bob", "charlie"},
            {"alice"},
        ]

        added_users = self.service.add_all_users_to_team("all-org-members")

        self.assertEqual(mock_put.call_count, 2)
        self.assertEqual(added_users, ["bob", "charlie"])
        self.assertFalse(mock_report_missing_2fa.called)

    @patch.object(GithubTeamSyncService, "_get_paginated_logins")
    @patch.object(GithubTeamSyncService, "_put")
    @patch.object(GithubTeamSyncService, "_report_missing_2fa_users")
    def test_add_all_users_skips_no_2fa_and_reports(
        self,
        mock_report_missing_2fa,
        mock_put,
        mock_get_paginated,
    ) -> None:
        # no_2fa errors are recoverable and should be reported, not raised.
        mock_get_paginated.side_effect = [
            {"alice", "bob"},
            set(),
        ]
        no_2fa_error = GithubApiRequestError(
            method="PUT",
            url="https://api.github.com/test",
            status_code=422,
            response_body={"errors": [{"code": "no_2fa"}]},
        )
        mock_put.side_effect = [None, no_2fa_error]

        added_users = self.service.add_all_users_to_team("all-org-members")

        mock_report_missing_2fa.assert_called_once_with("all-org-members", ["bob"])
        self.assertEqual(added_users, ["alice"])

    @patch.object(GithubTeamSyncService, "_get_paginated_logins")
    @patch.object(GithubTeamSyncService, "_put")
    def test_add_all_users_raises_non_2fa_error(
        self,
        mock_put,
        mock_get_paginated,
    ) -> None:
        # Non-2FA API failures should fail the run immediately.
        mock_get_paginated.side_effect = [
            {"alice"},
            set(),
        ]
        generic_error = GithubApiRequestError(
            method="PUT",
            url="https://api.github.com/test",
            status_code=500,
            response_body={"message": "boom"},
        )
        mock_put.side_effect = generic_error

        with self.assertRaises(GithubApiRequestError):
            self.service.add_all_users_to_team("all-org-members")

    def test_report_missing_2fa_users_writes_summary(self) -> None:
        # Summary output is used by Actions UI for quick operator visibility.
        with tempfile.NamedTemporaryFile(mode="w+", delete=True) as summary_file:
            with patch.dict(
                "os.environ", {"GITHUB_STEP_SUMMARY": summary_file.name}, clear=False
            ):
                self.service._report_missing_2fa_users(
                    "all-org-members", ["charlie", "alice"]
                )

            summary_file.seek(0)
            content = summary_file.read()

        self.assertIn("Users skipped due to missing 2FA", content)
        self.assertIn("Team: `all-org-members` in `ministryofjustice`.", content)
        self.assertIn("- `alice`", content)
        self.assertIn("- `charlie`", content)

    def test_write_added_users_output_writes_expected_json(self) -> None:
        with tempfile.NamedTemporaryFile(mode="r+", delete=True) as output_file:
            with patch.dict(
                "os.environ", {"ADDED_USERS_OUTPUT_PATH": output_file.name}, clear=False
            ):
                write_added_users_output(["alice", "bob"])

            output_file.seek(0)
            content = output_file.read()

        self.assertEqual(content, '{"added_users": ["alice", "bob"]}')

    def test_write_added_users_output_noop_without_env_var(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            write_added_users_output(["alice"])


if __name__ == "__main__":
    unittest.main()
