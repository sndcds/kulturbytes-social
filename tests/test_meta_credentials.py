"""Shared Meta credential and real CLI HTTP sequences, entirely mocked."""

import os
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from urllib.parse import quote

import httpx
from click.testing import CliRunner
from dotenv_support import IsolatedEnvironmentTestCase
from test_instagram import EVENT as IG_EVENT
from test_instagram import instagram
from test_publishers import EVENT, FACEBOOK, SUMMARY

from kulturbytes_common import credentials
from kulturbytes_facebook import auth as facebook_auth
from kulturbytes_social.cli import cli

SYSTEM = "system-secret+/meta"
PAGE_TOKEN = "derived-secret+/page"
LEGACY = "legacy-secret"
ENV = {
    "FACEBOOK_PAGE_ID": "123",
    "INSTAGRAM_USER_ID": "123",
    "META_SYSTEM_USER_ACCESS_TOKEN": SYSTEM,
    "FACEBOOK_PAGE_ACCESS_TOKEN": LEGACY,
    "INSTAGRAM_ACCESS_TOKEN": LEGACY,
}
ACCOUNTS = {
    "data": [
        {"id": "999", "name": "Other", "access_token": "other"},
        {"id": "123", "name": "Kulturbytes", "access_token": PAGE_TOKEN},
    ]
}


class MetaTests(IsolatedEnvironmentTestCase):
    def invoke(
        self,
        platform,
        *,
        env=None,
        stored=None,
        publish=False,
        overrides=None,
        tty=False,
    ):
        module = FACEBOOK if platform == "facebook" else instagram
        calls = []
        overrides = overrides or {}
        client_class = httpx.Client

        def handle(request):
            calls.append(request)
            path = request.url.path
            if path in overrides:
                override = overrides[path]
                return (
                    override(request)
                    if callable(override)
                    else httpx.Response(*override)
                )
            if path == "/v26.0/me/accounts":
                self.assertEqual(request.headers["Authorization"], f"Bearer {SYSTEM}")
                return httpx.Response(200, json=ACCOUNTS)
            if path == "/v26.0/123":
                expected = PAGE_TOKEN if platform == "facebook" else SYSTEM
                self.assertEqual(request.headers["Authorization"], f"Bearer {expected}")
                return httpx.Response(
                    200,
                    json={
                        "id": "123",
                        "name": "Kulturbytes",
                        "username": "kulturbytes",
                    },
                )
            if path == "/api/events":
                return httpx.Response(200, json={"data": {"events": [SUMMARY]}})
            if path.startswith("/api/event/"):
                return httpx.Response(
                    200, json={"data": EVENT if platform == "facebook" else IG_EVENT}
                )
            if path == "/api/image/image-1":
                self.assertNotIn("Authorization", request.headers)
                return httpx.Response(200, content=b"\xff\xd8\xffJPEG")
            expected = PAGE_TOKEN if platform == "facebook" else SYSTEM
            self.assertEqual(request.headers["Authorization"], f"Bearer {expected}")
            self.assertNotIn("access_token", request.url.params)
            self.assertEqual(request.url.host, "graph.facebook.com")
            if path == "/v26.0/456":
                return httpx.Response(200, json={"status_code": "FINISHED"})
            self.assertEqual(request.method, "POST")
            self.assertIn(
                path,
                ["/v26.0/123/feed", "/v26.0/123/media", "/v26.0/123/media_publish"],
            )
            return httpx.Response(200, json={"id": "456"})

        with (
            tempfile.TemporaryDirectory() as directory,
            patch(
                "kulturbytes_common.environment.get_env_file_path",
                return_value=Path(directory) / ".env",
            ),
            patch.dict(os.environ, ENV if env is None else env, clear=True),
            patch.object(
                credentials,
                "get_secret",
                side_effect=lambda service, user: (stored or {}).get((service, user)),
            ) as lookup,
            patch.object(credentials, "set_secret") as save,
            patch.object(facebook_auth, "set_secret") as page_save,
            patch.object(facebook_auth, "interactive", return_value=tty),
            patch.object(
                facebook_auth.click,
                "prompt",
                side_effect=AssertionError("Unexpected token prompt"),
            ),
            patch.object(
                httpx,
                "Client",
                side_effect=lambda **kw: client_class(
                    transport=httpx.MockTransport(handle), **kw
                ),
            ),
            patch.object(module, "DATABASE_PATH", Path(directory) / "state.sqlite3"),
        ):
            args = (
                [
                    "--publish",
                    "--event-uuid",
                    "event-1",
                    "--date-identifier",
                    SUMMARY["date_slug"],
                ]
                if publish
                else ["--check-auth"]
            )
            result = CliRunner().invoke(
                cli, [platform, *args], input="y\n" if publish else ""
            )
            database = Path(directory) / "state.sqlite3"
            if publish and result.exit_code == 0:
                with closing(sqlite3.connect(database)) as conn, conn:
                    self.assertEqual(
                        conn.execute(
                            "SELECT COUNT(*) FROM published_events"
                        ).fetchone(),
                        (1,),
                    )
            else:
                self.assertFalse(database.exists())
            save.assert_not_called()
            page_save.assert_not_called()
        for token in (SYSTEM, PAGE_TOKEN, LEGACY):
            self.assertNotIn(token, result.output)
            self.assertNotIn(quote(token, safe=""), result.output)
        return result, calls, lookup

    def test_shared_env_precedence_and_read_only_checks(self):
        for platform in ("facebook", "instagram"):
            for tty in (False, True):
                result, calls, lookup = self.invoke(
                    platform,
                    tty=tty,
                    stored={
                        (
                            "kulturbytes-social/meta",
                            "system-user-access-token",
                        ): "ignored"
                    },
                )
                self.assertEqual(
                    result.exit_code, 0, result.output + str(result.exception)
                )
                self.assertTrue(
                    all(
                        r.method == "GET" and r.url.host == "graph.facebook.com"
                        for r in calls
                    )
                )
                self.assertEqual(len(calls), 2 if platform == "facebook" else 1)
                self.assertNotIn("veraltet", result.output)
                lookup.assert_not_called()

    def test_shared_keyring_precedes_legacy_environment(self):
        for platform in ("facebook", "instagram"):
            result, _, lookup = self.invoke(
                platform,
                env={
                    k: v for k, v in ENV.items() if k != "META_SYSTEM_USER_ACCESS_TOKEN"
                },
                stored={
                    ("kulturbytes-social/meta", "system-user-access-token"): SYSTEM
                },
            )
            self.assertEqual(result.exit_code, 0, result.output)
            lookup.assert_called_once_with(
                "kulturbytes-social/meta", "system-user-access-token"
            )

    def test_empty_shared_env_suppresses_keyring_and_allows_legacy(self):
        with (
            patch.dict(
                os.environ, {**ENV, "META_SYSTEM_USER_ACCESS_TOKEN": ""}, clear=True
            ),
            patch.object(
                credentials,
                "get_secret",
                side_effect=AssertionError("Unexpected keyring lookup"),
            ),
        ):
            with CliRunner().isolation() as out:
                config = instagram.load_config()
            self.assertEqual(config.access_token, LEGACY)
            self.assertIn("graph.instagram.com", config.base_url)
            self.assertIn(b"veraltet", out[1].getvalue())

    def test_incompatible_instagram_login_fails_before_requests(self):
        result, calls, _ = self.invoke(
            "instagram", env={**ENV, "INSTAGRAM_LOGIN_TYPE": "instagram"}
        )
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("INSTAGRAM_LOGIN_TYPE=facebook", result.output)
        self.assertFalse(calls)

    def test_full_publish_sequences_and_token_reuse(self):
        for platform in ("facebook", "instagram"):
            result, calls, _ = self.invoke(platform, publish=True)
            self.assertEqual(result.exit_code, 0, result.output + str(result.exception))
            self.assertEqual(calls[0].url.host, "graph.facebook.com")
            self.assertEqual(
                calls[1 if platform == "facebook" else 0].url.path, "/v26.0/123"
            )
            self.assertEqual(
                sum(r.method == "POST" for r in calls),
                1 if platform == "facebook" else 2,
            )

    def test_auth_errors_never_fall_back_or_touch_events_and_database(self):
        for platform in ("facebook", "instagram"):
            for payload in [
                {"error": {"code": 190, "message": SYSTEM}},
                {"error": {"code": 200}},
                {"id": "999", "name": "other", "username": "other"},
                {"id": "123"},
                [],
            ]:
                with self.subTest(platform=platform, payload=payload):
                    result, calls, _ = self.invoke(
                        platform,
                        publish=True,
                        overrides={
                            "/v26.0/123": lambda r: httpx.Response(200, json=payload)
                        },
                    )
                    self.assertNotEqual(result.exit_code, 0)
                    self.assertTrue(
                        all(
                            r.method == "GET" and r.url.host == "graph.facebook.com"
                            for r in calls
                        )
                    )

    def test_system_page_lookup_pagination(self):
        def pages(request):
            if "after" in request.url.params:
                self.assertEqual(request.url.params["after"], "second")
                self.assertNotIn("access_token", request.url.params)
                return httpx.Response(200, json=ACCOUNTS)
            return httpx.Response(
                200,
                json={
                    "data": [],
                    "paging": {
                        "next": "https://graph.facebook.com/v26.0/me/accounts?access_token=discarded",
                        "cursors": {"after": "second"},
                    },
                },
            )

        result, calls, _ = self.invoke(
            "facebook", overrides={"/v26.0/me/accounts": pages}
        )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(len(calls), 3)

    def test_shared_status_and_default_management(self):
        for platform in ("facebook", "instagram"):
            with (
                patch.dict(os.environ, {}, clear=True),
                patch.object(credentials, "get_secret", return_value=SYSTEM) as lookup,
                patch.object(credentials, "set_secret") as save,
                patch.object(credentials, "delete_secret", return_value=True) as delete,
            ):
                result = CliRunner().invoke(cli, [platform, "--credentials", "status"])
                self.assertEqual(result.exit_code, 0, result.output)
                self.assertIn("Meta System User Access Token vorhanden", result.output)
                self.assertNotIn(SYSTEM, result.output)
                lookup.assert_called_once_with(
                    "kulturbytes-social/meta", "system-user-access-token"
                )
                result = CliRunner().invoke(
                    cli, [platform, "--credentials", "set"], input=SYSTEM + "\n"
                )
                self.assertEqual(result.exit_code, 0, result.output)
                self.assertNotIn(SYSTEM, result.output)
                save.assert_called_once_with(
                    "kulturbytes-social/meta", "system-user-access-token", SYSTEM
                )
                CliRunner().invoke(
                    cli, [platform, "--credentials", "delete"], input="n\n"
                )
                delete.assert_not_called()
                CliRunner().invoke(
                    cli, [platform, "--credentials", "delete"], input="y\n"
                )
                delete.assert_called_once_with(
                    "kulturbytes-social/meta", "system-user-access-token"
                )

    def test_system_lookup_failure_does_not_attempt_legacy_recovery(self):
        bodies = [
            {"data": []},
            {},
            {"data": "invalid"},
            {"data": [{"id": "123", "name": "Page"}]},
            {"error": {"code": 190, "error_subcode": 463, "message": SYSTEM}},
            {
                "data": [],
                "paging": {"next": "https://evil.example/", "cursors": {"after": "x"}},
            },
        ]
        for body in bodies:
            result, calls, _ = self.invoke(
                "facebook",
                publish=True,
                tty=True,
                overrides={
                    "/v26.0/me/accounts": lambda r: httpx.Response(200, json=body)
                },
            )
            self.assertNotEqual(result.exit_code, 0)
            self.assertEqual(len(calls), 1)
            self.assertNotIn("wiederherstellen?", result.output)

    def test_secret_redaction_on_validation_and_transport_failure(self):
        for platform in ("facebook", "instagram"):
            for name in (SYSTEM, PAGE_TOKEN, quote(SYSTEM, safe="")):
                result, _, _ = self.invoke(
                    platform,
                    overrides={
                        "/v26.0/123": lambda r: httpx.Response(
                            200,
                            json={
                                "id": "123",
                                "name": name,
                                "username": name if name != PAGE_TOKEN else SYSTEM,
                            },
                        )
                    },
                )
                self.assertEqual(result.exit_code, 0, result.output)
                self.assertIn("[REDACTED]", result.output)

            def fail(request):
                raise httpx.ConnectError(SYSTEM, request=request)

            result, calls, _ = self.invoke(
                platform, publish=True, overrides={"/v26.0/123": fail}
            )
            self.assertNotEqual(result.exit_code, 0)
            self.assertTrue(all(r.method == "GET" for r in calls))
