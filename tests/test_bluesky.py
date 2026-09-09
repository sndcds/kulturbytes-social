"""Offline Bluesky XRPC, identity, credential and publication regressions."""

import base64
import importlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import zipfile
from contextlib import closing, nullcontext
from pathlib import Path
from unittest.mock import Mock, patch

import click
import httpx
import yaml
from canonical_support import canonical
from click.testing import CliRunner
from dotenv_support import HTTPXClient, IsolatedEnvironmentTestCase
from test_publishers import EVENT

from kulturbytes_bluesky import auth, publishing
from kulturbytes_common import environment, storage
from kulturbytes_common.atproto_identity import post_identity
from kulturbytes_common.image_urls import ImageSettings
from kulturbytes_common.publications import (
    get_attempt,
    reserve_attempt,
    resolve_attempt,
)
from kulturbytes_common.rendering import render_post
from kulturbytes_common.sources.models import ContentItem
from kulturbytes_common.text_limits import (
    bluesky_text_fits,
    grapheme_count,
    grapheme_words,
)
from kulturbytes_social.cli import cli

bluesky = importlib.import_module("kulturbytes_bluesky.cli")
DID = "did:plc:abcdefghijklmnopqrstuvwx"
HANDLE = "writer.example.org"
PASSWORD = "app-password-ONLY"
JWT = "header.payload.signature"
REFRESH = "refresh.jwt.secret"
URI = f"at://{DID}/app.bsky.feed.post/3abcdefghijk2"
PDS = "https://pds.example.org"
CID = "b" + base64.b32encode(b"\x01\x71\x12\x20" + b"x" * 32).decode().lower().rstrip(
    "="
)
BLOB_CID = "b" + base64.b32encode(
    b"\x01\x55\x12\x20" + b"x" * 32
).decode().lower().rstrip("=")
JPEG = b"\xff\xd8\xff" + b"image" + b"\xff\xd9"
CONFIG = auth.BlueskyConfig(PDS, HANDLE, PASSWORD)
SESSION = auth.Session(PDS, DID, HANDLE, JWT, (PASSWORD, JWT, REFRESH))
ENV = {
    "BLUESKY_HANDLE": HANDLE,
    "BLUESKY_APP_PASSWORD": PASSWORD,
    "BLUESKY_SERVICE_URL": PDS,
}


def session_response():
    return {"did": DID, "handle": HANDLE, "accessJwt": JWT, "refreshJwt": REFRESH}


def blob_response():
    return {
        "blob": {
            "$type": "blob",
            "ref": {"$link": BLOB_CID},
            "mimeType": "image/jpeg",
            "size": len(JPEG),
        }
    }


class BlueskyTests(IsolatedEnvironmentTestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.db = self.root / "bluesky.db"
        self.item = canonical(EVENT)
        self.calls = []
        self.stage_checks = []

    def response(self, request):
        self.calls.append(request)
        if request.url.host == "api.kulturbytes.de":
            self.assertNotIn("Authorization", request.headers)
            self.assertNotIn(PASSWORD, str(request.url))
            if request.url.path == "/api/events":
                from test_publishers import SUMMARY

                return httpx.Response(200, json={"data": {"events": [SUMMARY]}})
            if request.url.path.startswith("/api/event/"):
                return httpx.Response(200, json={"data": EVENT})
            return httpx.Response(
                200, content=JPEG, headers={"Content-Type": "image/jpg"}
            )
        if request.url.host == "source.example.org":
            self.assertNotIn("Authorization", request.headers)
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": "article-1",
                            "title": "Synthetic article",
                            "body": "独立 content",
                        }
                    ]
                },
            )
        self.assertEqual(request.url.host, "pds.example.org")
        self.assertEqual(request.method, "POST")
        method = request.url.path.rsplit("/", 1)[-1]
        if method == "com.atproto.server.createSession":
            self.assertNotIn("Authorization", request.headers)
            self.assertEqual(
                json.loads(request.content),
                {"identifier": HANDLE, "password": PASSWORD},
            )
            return httpx.Response(200, json=session_response())
        self.assertEqual(request.headers["Authorization"], f"Bearer {JWT}")
        self.assertNotIn(PASSWORD.encode(), request.content)
        self.assertNotIn(REFRESH.encode(), request.content)
        if self.db.exists():
            with closing(sqlite3.connect(self.db)) as observer:
                stage = observer.execute(
                    "SELECT state,mutation_stage FROM publication_attempts ORDER BY rowid DESC LIMIT 1"
                ).fetchone()
                self.stage_checks.append(stage)
        if method == "com.atproto.repo.uploadBlob":
            self.assertEqual(request.headers["Content-Type"], "image/jpeg")
            self.assertEqual(request.content, JPEG)
            return httpx.Response(200, json=blob_response())
        self.assertEqual(method, "com.atproto.repo.createRecord")
        payload = json.loads(request.content)
        self.assertEqual(payload["repo"], DID)
        self.assertEqual(payload["collection"], "app.bsky.feed.post")
        self.assertTrue(payload["record"]["createdAt"].endswith("Z"))
        return httpx.Response(200, json={"uri": URI, "cid": CID})

    def client(self, handler=None):
        return HTTPXClient(
            transport=httpx.MockTransport(handler or self.response), trust_env=False
        )

    def connection(self):
        conn = storage.init_database("bluesky", self.db)
        self.addCleanup(conn.close)
        return conn

    def invoke(self, args, *, env=None, handler=None, input="y\n", source_roots=None):
        def factory(*args, **kwargs):
            return self.client(handler)

        with (
            patch.dict(os.environ, ENV if env is None else env, clear=True),
            patch.object(bluesky, "DATABASE_PATH", self.db),
            patch("httpx.Client", side_effect=factory),
            patch(
                "kulturbytes_common.sources.loader.config_roots",
                return_value=source_roots,
            )
            if source_roots
            else nullcontext(),
        ):
            return CliRunner().invoke(cli, args, input=input)

    def test_help_import_and_dry_run_without_credentials(self):
        with (
            patch.object(
                auth, "load_config", side_effect=AssertionError("credential access")
            ),
            patch(
                "kulturbytes_common.credentials.get_secret",
                side_effect=AssertionError("keyring access"),
            ),
        ):
            for args in (["--help"], ["bluesky", "--help"], ["publish", "--help"]):
                result = CliRunner().invoke(cli, args)
                self.assertEqual(result.exit_code, 0, result.output)
        result = subprocess.run(
            [sys.executable, "-c", "import kulturbytes_bluesky"],
            env={},
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.invoke(
            ["bluesky", "--event-uuid", "event-1", "--date-identifier", "date-1"],
            env={},
        )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("DRY RUN", result.output)
        self.assertTrue(all(request.method == "GET" for request in self.calls))
        with closing(sqlite3.connect(self.db)) as conn:
            self.assertEqual(
                conn.execute("SELECT count(*) FROM publication_attempts").fetchone()[0],
                0,
            )

    def test_missing_credentials_before_network_or_database(self):
        for env in ({}, {"BLUESKY_HANDLE": HANDLE, "BLUESKY_APP_PASSWORD": ""}):
            with self.subTest(env=env):
                result = self.invoke(["bluesky", "--publish"], env=env)
                self.assertNotEqual(result.exit_code, 0)
                self.assertEqual(self.calls, [])
                self.assertFalse(self.db.exists())

    def test_config_url_and_credential_precedence(self):
        with patch.dict(os.environ, ENV, clear=True):
            self.assertEqual(auth.load_config(), CONFIG)
            for url in (
                "http://pds.example.org",
                "https://a:secret@pds.example.org",
                "https://pds.example.org/x",
                "https://pds.example.org?token=x",
                "https://pds.example.org:bad",
                "",
            ):
                with (
                    patch.dict(os.environ, {"BLUESKY_SERVICE_URL": url}),
                    self.assertRaises(click.ClickException),
                ):
                    auth.load_config()
            with patch.dict(
                os.environ, {"BLUESKY_SERVICE_URL": "https://PDS.EXAMPLE.ORG/"}
            ):
                self.assertEqual(auth.load_config().service_url, PDS)
            environment.get_env_file_path().write_text(
                "BLUESKY_APP_PASSWORD=dotenv-app-password\n"
            )
            with patch(
                "kulturbytes_common.credentials.get_secret",
                side_effect=AssertionError("keyring"),
            ):
                self.assertEqual(auth.load_config().app_password, "dotenv-app-password")
            environment.get_env_file_path().write_text("")
        with (
            patch.dict(os.environ, {"BLUESKY_HANDLE": HANDLE}, clear=True),
            patch(
                "kulturbytes_common.credentials.get_secret", return_value=PASSWORD
            ) as keyring,
        ):
            self.assertEqual(auth.load_config().app_password, PASSWORD)
            keyring.assert_called_once_with(
                "kulturbytes-social/bluesky", "app-password"
            )

    def test_explicit_credential_management_is_offline(self):
        with patch("kulturbytes_common.credentials.set_secret") as save:
            result = CliRunner().invoke(
                cli, ["bluesky", "--credentials", "set"], input=PASSWORD + "\n"
            )
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertNotIn(PASSWORD, result.output)
            save.assert_called_once_with(
                "kulturbytes-social/bluesky", "app-password", PASSWORD
            )
        with patch.dict(os.environ, ENV, clear=True):
            result = CliRunner().invoke(cli, ["bluesky", "--credentials", "status"])
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertNotIn(PASSWORD, result.output)
        self.assertFalse(self.db.exists())

    def test_auth_success_custom_pds_and_check_auth(self):
        with self.client() as client:
            session = auth.authenticate(client, CONFIG)
        self.assertEqual(session.did, DID)
        self.assertNotIn(PASSWORD, repr(CONFIG))
        for secret in (PASSWORD, JWT, REFRESH):
            self.assertNotIn(secret, repr(session))
        self.calls.clear()
        result = self.invoke(["bluesky", "--check-auth"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(len(self.calls), 1)
        self.assertFalse(self.db.exists())

    def test_malformed_session_fails_closed(self):
        bad = [
            {},
            [],
            None,
            {**session_response(), "did": "bad"},
            {**session_response(), "handle": "other.example.org"},
            {**session_response(), "accessJwt": PASSWORD},
            {**session_response(), "accessJwt": "a.b.c\nAuthorization: x"},
            {**session_response(), "did": f"did:web:{PASSWORD}"},
        ]
        for payload in bad:
            with (
                self.subTest(payload=payload),
                self.client(lambda r: httpx.Response(200, json=payload)) as client,
                self.assertRaises(click.ClickException) as raised,
            ):
                auth.authenticate(client, CONFIG)
            for secret in (PASSWORD, JWT, REFRESH):
                self.assertNotIn(secret, str(raised.exception))
        with (
            self.client(lambda r: httpx.Response(200, content=b"not json")) as client,
            self.assertRaises(click.ClickException),
        ):
            auth.authenticate(client, CONFIG)

    def test_auth_rejection_and_transport_redact_all_secrets(self):
        for status in (400, 401, 403, 429, 500, 503, 302):
            result = self.invoke(
                ["bluesky", "--check-auth"],
                handler=lambda r: httpx.Response(
                    status,
                    json={"error": f"{PASSWORD} {JWT} {REFRESH}"},
                    headers={"Location": "https://evil.example.org"},
                ),
            )
            self.assertNotEqual(result.exit_code, 0)
            for secret in (PASSWORD, JWT, REFRESH):
                self.assertNotIn(secret, result.output + str(result.exception))

        def broken(request):
            raise httpx.ReadTimeout(PASSWORD + JWT + REFRESH, request=request)

        result = self.invoke(["bluesky", "--check-auth"], handler=broken)
        self.assertNotIn(PASSWORD, result.output + str(result.exception))

    def test_facet_uri_normalization_preserves_visible_utf8_ranges(self):
        cases = [
            ("https://example.org/über", "https://example.org/%C3%BCber"),
            ("https://münchen.example/path", "https://xn--mnchen-3ya.example/path"),
            (
                "https://example.org/search?q=grün",
                "https://example.org/search?q=gr%C3%BCn",
            ),
            ("https://example.org/page#über", "https://example.org/page#%C3%BCber"),
            ("https://example.org/a%20b", "https://example.org/a%20b"),
            ("https://example.org:8443/path", "https://example.org:8443/path"),
            ("https://example.org/foo", "https://example.org/foo"),
            (
                "https://EXAMPLE.org/a%2fb?q=a/b&x=é#café",
                "https://example.org/a%2fb?q=a/b&x=%C3%A9#caf%C3%A9",
            ),
            ("http://example.org:80/a", "http://example.org:80/a"),
            ("https://[2001:db8::1]:8443/über", "https://[2001:db8::1]:8443/%C3%BCber"),
        ]
        for visible, normalized in cases:
            with self.subTest(visible=visible):
                prefix = "👩‍💻 café "
                text = prefix + visible + ", weiter."
                facets = publishing.link_facets(text)
                self.assertEqual(len(facets), 1)
                facet = facets[0]
                self.assertEqual(facet["features"][0]["uri"], normalized)
                self.assertEqual(
                    facet["index"]["byteStart"], len(prefix.encode("utf-8"))
                )
                self.assertEqual(
                    facet["index"]["byteEnd"], len((prefix + visible).encode("utf-8"))
                )
                self.assertEqual(
                    text.encode("utf-8")[
                        facet["index"]["byteStart"] : facet["index"]["byteEnd"]
                    ].decode("utf-8"),
                    visible,
                )
        self.assertEqual(
            publishing.facet_uri("HTTPS://EXAMPLE.ORG/foo"), "https://example.org/foo"
        )

    def test_multiple_unicode_facets_and_trailing_punctuation(self):
        urls = ["https://example.org/über", "https://münchen.example/a?q=grün#über"]
        text = f"👩‍💻 café {urls[0]}, schön 🌍 {urls[1]}!"
        facets = publishing.link_facets(text)
        self.assertEqual(len(facets), 2)
        self.assertLess(facets[0]["index"]["byteEnd"], facets[1]["index"]["byteStart"])
        for facet, visible in zip(facets, urls, strict=True):
            offsets = facet["index"]
            self.assertEqual(
                text.encode("utf-8")[offsets["byteStart"] : offsets["byteEnd"]].decode(
                    "utf-8"
                ),
                visible,
            )
        for punctuation in ".,!?;:":
            visible = "https://example.org/a,b!c;d:e?q=x:y"
            facet = publishing.link_facets(visible + punctuation)[0]
            self.assertEqual(facet["features"][0]["uri"], visible)
            self.assertEqual(facet["index"]["byteEnd"], len(visible.encode("utf-8")))

    def test_facet_uri_rejects_unsafe_candidates_without_echoing_input(self):
        invalid = [
            "https://user@example.org/path",
            "https://user:secret@example.org/path",
            "https://example.org:bad/path",
            "https://example.org:65536/path",
            "https://example.org:/path",
            "https:///path",
            "ftp://example.org/path",
            "https://example.org/a b",
            "https://example.org/a\tb",
            "https://example.org/a\nb",
            "https://example.org/\x00",
            "https://example.org/\x7f",
            "https://example.org/\x85",
            "https://example.org/%zz",
            "https://example.org/%2",
            "https://example.org/%",
            "https://bad_host.example/path",
            "https://example..org/path",
            "https://example.org\\evil/path",
            "https://[invalid]/path",
            "https://[::1]garbage/path",
            "https://[fe80::1%25eth0]/path",
        ]
        for candidate in invalid:
            with (
                self.subTest(candidate=candidate),
                self.assertRaises(click.ClickException) as raised,
            ):
                publishing.facet_uri(candidate)
            self.assertEqual(
                str(raised.exception), "Bluesky: ungültige Link-URL im Beitrag."
            )
        for candidate in invalid[:6] + [
            "https://example.org/%zz",
            "https://example.org/\x00",
        ]:
            with self.assertRaises(click.ClickException) as raised:
                publishing.link_facets("Text " + candidate)
            self.assertEqual(
                str(raised.exception), "Bluesky: ungültige Link-URL im Beitrag."
            )

    def test_text_post_identity_facets_and_journal(self):
        conn = self.connection()
        with self.client() as client, patch("click.confirm", return_value=True):
            self.assertTrue(
                bluesky.publish_event(client, conn, self.item, False, session=SESSION)
            )
        self.assertEqual(self.stage_checks, [("publishing", "bluesky_post")])
        row = conn.execute(
            "SELECT state,remote_id,remote_url,target_ref,mutation_stage FROM publication_attempts"
        ).fetchone()
        self.assertEqual(
            row,
            (
                "published",
                URI,
                f"https://bsky.app/profile/{HANDLE}/post/3abcdefghijk2",
                DID,
                "bluesky_post",
            ),
        )
        self.assertEqual(
            conn.execute("SELECT bluesky_post_uri FROM published_events").fetchone()[0],
            URI,
        )
        data = json.loads(self.calls[-1].content)
        self.assertEqual(data["record"]["text"], render_post(self.item, "bluesky").text)
        text = "👩‍💻 café https://example.org/über\nhttps://example.org/two"
        facets = publishing.link_facets(text)
        self.assertEqual(len(facets), 2)
        self.assertLessEqual(
            facets[0]["index"]["byteEnd"], facets[1]["index"]["byteStart"]
        )
        for facet, visible, uri in zip(
            facets,
            ("https://example.org/über", "https://example.org/two"),
            ("https://example.org/%C3%BCber", "https://example.org/two"),
            strict=True,
        ):
            offsets = facet["index"]
            self.assertEqual(
                text.encode()[offsets["byteStart"] : offsets["byteEnd"]].decode(),
                visible,
            )
            self.assertEqual(facet["features"][0]["uri"], uri)
        for secret in (PASSWORD, JWT, REFRESH):
            self.assertNotIn(secret, "\n".join(conn.iterdump()))

    def test_image_embed_alt_pluto_security_and_journal(self):
        conn = self.connection()
        item = canonical(
            {
                **EVENT,
                "images": {
                    "main": {
                        "url": "https://api.kulturbytes.de/image",
                        "alt": "Musiker auf der Bühne",
                    }
                },
            }
        )
        with self.client() as client, patch("click.confirm", return_value=True):
            bluesky.publish_event(client, conn, item, False, session=SESSION)
        self.assertEqual(
            self.stage_checks,
            [("publishing", "bluesky_blob"), ("publishing", "bluesky_post")],
        )
        image_request = self.calls[0]
        self.assertEqual(
            dict(image_request.url.params),
            {"ratio": "4:3", "width": "1920", "type": "jpg"},
        )
        record = json.loads(self.calls[-1].content)["record"]
        image = record["embed"]["images"][0]
        self.assertEqual(image["alt"], "Musiker auf der Bühne")
        self.assertEqual(image["image"], blob_response()["blob"])
        self.assertNotIn("aspectRatio", image)
        self.assertNotIn("Authorization", image_request.headers)
        self.assertEqual(
            render_post(
                canonical(
                    {
                        **EVENT,
                        "images": {"main": {"url": "https://api.kulturbytes.de/image"}},
                    }
                ),
                "bluesky",
            ).image_alt,
            "Veranstaltungsbild zu Kulturabend",
        )

    def test_image_limits_mime_and_host_block_before_upload(self):
        for content, mime in (
            (b"bad", "image/jpeg"),
            (JPEG, "text/html"),
            (JPEG + b"x" * publishing.IMAGE_MAX_BYTES, "image/jpeg"),
        ):
            calls = []

            def respond(request):
                calls.append(request)
                return httpx.Response(
                    200, content=content, headers={"Content-Type": mime}
                )

            item = canonical(
                {
                    **EVENT,
                    "images": {"main": {"url": "https://api.kulturbytes.de/image"}},
                }
            )
            with (
                self.subTest(mime=mime, length=len(content)),
                self.client(respond) as client,
                self.assertRaises(click.ClickException),
            ):
                publishing.publish_post(client, SESSION, render_post(item, "bluesky"))
            self.assertTrue(all(call.method == "GET" for call in calls))
        item = canonical(
            {
                **EVENT,
                "images": {"main": {"url": "https://not-allowed.example.org/image"}},
            }
        )
        with self.client() as client, self.assertRaises(click.ClickException):
            publishing.publish_post(client, SESSION, render_post(item, "bluesky"))
        self.assertEqual(self.calls, [])

    def test_blob_validation_prevents_create_record(self):
        for blob in (
            None,
            {},
            {**blob_response()["blob"], "size": True},
            {**blob_response()["blob"], "size": len(JPEG) + 1},
            {**blob_response()["blob"], "mimeType": "text/html"},
            {**blob_response()["blob"], "ref": {"$link": "fake"}},
        ):
            calls = []

            def respond(request):
                calls.append(request)
                if request.method == "GET":
                    return httpx.Response(
                        200, content=JPEG, headers={"Content-Type": "image/jpeg"}
                    )
                return httpx.Response(200, json={"blob": blob})

            item = canonical(
                {
                    **EVENT,
                    "images": {"main": {"url": "https://api.kulturbytes.de/image"}},
                }
            )
            with (
                self.subTest(blob=blob),
                self.client(respond) as client,
                self.assertRaises(click.ClickException),
            ):
                publishing.publish_post(client, SESSION, render_post(item, "bluesky"))
            self.assertNotIn(
                "com.atproto.repo.createRecord",
                [call.url.path.rsplit("/", 1)[-1] for call in calls],
            )

    def test_record_validation_keeps_uncertain_attempt_active(self):
        for index, payload in enumerate(
            (
                {},
                {"uri": URI, "cid": "fake"},
                {"uri": URI.replace(DID, "did:web:other.org"), "cid": CID},
                {"uri": URI + "?token=" + PASSWORD, "cid": CID},
                {"uri": URI.rsplit("/", 1)[0] + "/" + PASSWORD, "cid": CID},
            )
        ):
            item = canonical(
                {**EVENT, "date": {**EVENT["date"], "uuid": f"date-{index}"}}
            )
            conn = self.connection()
            with (
                self.client(lambda r: httpx.Response(200, json=payload)) as client,
                patch("click.confirm", return_value=True),
                self.assertRaises(click.ClickException) as raised,
            ):
                bluesky.publish_event(client, conn, item, False, session=SESSION)
            self.assertNotIn(PASSWORD, str(raised.exception))
            self.assertEqual(
                conn.execute(
                    "SELECT state FROM publication_attempts ORDER BY rowid DESC LIMIT 1"
                ).fetchone()[0],
                "publishing",
            )
        self.assertFalse(post_identity("https://bsky.app/profile/x/post/y"))
        self.assertEqual(post_identity(URI), (DID, "3abcdefghijk2"))

    def test_concurrent_dedup_and_confirmed_repeat(self):
        a, b = self.connection(), self.connection()
        first = reserve_attempt(a, "bluesky", self.item, target_ref=DID)
        with (
            self.client() as client,
            patch("click.confirm", return_value=True),
            self.assertRaises(click.ClickException),
        ):
            bluesky.publish_event(
                client, b, self.item, False, session=SESSION, allow_repeat=True
            )
        self.assertEqual(self.calls, [])
        resolve_attempt(a, first, "failed", Mock())
        with self.client() as client, patch("click.confirm", return_value=True):
            bluesky.publish_event(client, a, self.item, False, session=SESSION)
            with self.assertRaises(click.ClickException):
                bluesky.publish_event(client, b, self.item, False, session=SESSION)
            bluesky.publish_event(
                client, b, self.item, False, session=SESSION, allow_repeat=True
            )
        self.assertEqual(
            a.execute("SELECT count(*) FROM published_events").fetchone()[0], 1
        )
        self.assertEqual(
            a.execute(
                "SELECT count(*) FROM publication_attempts WHERE state='published'"
            ).fetchone()[0],
            2,
        )

    def test_post_failures_are_not_retried(self):
        for index, status in enumerate((400, 401, 403, 429, 408, 500, 503, None)):
            conn = self.connection()
            item = canonical(
                {**EVENT, "date": {**EVENT["date"], "uuid": f"error-{index}"}}
            )
            calls = []

            def respond(request):
                calls.append(request)
                if status is None:
                    raise httpx.ReadTimeout(PASSWORD + JWT, request=request)
                return httpx.Response(status, json={"error": PASSWORD + JWT + REFRESH})

            with (
                self.subTest(status=status),
                self.client(respond) as client,
                patch("click.confirm", return_value=True),
                self.assertRaises(click.ClickException) as raised,
            ):
                bluesky.publish_event(client, conn, item, False, session=SESSION)
            self.assertEqual(len(calls), 1)
            expected = "failed" if status in (400, 401, 403, 429) else "publishing"
            self.assertEqual(
                conn.execute(
                    "SELECT state FROM publication_attempts ORDER BY rowid DESC LIMIT 1"
                ).fetchone()[0],
                expected,
            )
            for secret in (PASSWORD, JWT, REFRESH):
                self.assertNotIn(secret, str(raised.exception))
                self.assertNotIn(secret, "\n".join(conn.iterdump()))

    def test_recovery_uses_at_uri_and_did_without_network(self):
        conn = self.connection()
        attempt = reserve_attempt(conn, "bluesky", self.item, target_ref=DID)
        args = [
            "attempts",
            "resolve",
            "--platform",
            "bluesky",
            attempt,
            "--outcome",
            "published",
            "--remote-id",
            URI,
        ]
        result = self.invoke(args, env={})
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(self.calls, [])
        self.assertEqual(get_attempt(conn, attempt)["state"], "published")
        with self.assertRaises(click.ClickException):
            storage.init_database("facebook", self.db)
        other = canonical(
            {**EVENT, "date": {**EVENT["date"], "uuid": "recovery-other"}}
        )
        attempt = reserve_attempt(conn, "bluesky", other, target_ref=DID)
        with self.assertRaises(click.ClickException):
            resolve_attempt(
                conn,
                attempt,
                "published",
                Mock(),
                remote_id=URI.replace(DID, "did:web:other.org"),
            )

    def test_generic_synthetic_publish_and_selection(self):
        sources = self.root / "sources"
        sources.mkdir()
        (sources / "articles.yaml").write_text(
            yaml.safe_dump(
                {
                    "name": "articles",
                    "adapter": "json",
                    "endpoint": "https://source.example.org/items",
                    "root": "items",
                    "fields": {"id": "id", "title": "title", "text": "body"},
                }
            )
        )
        args = [
            "publish",
            "--platform",
            "bluesky",
            "--source",
            "articles",
            "--item-id",
            "article-1",
        ]
        result = self.invoke(args, env={}, source_roots=[sources])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Synthetic article", result.output)
        result = self.invoke([*args, "--publish"], source_roots=[sources])
        self.assertEqual(result.exit_code, 0, result.output)
        with closing(sqlite3.connect(self.db)) as conn:
            self.assertEqual(
                conn.execute("SELECT date_uuid FROM published_events").fetchone()[0],
                "articles:article-1",
            )
        record = json.loads(self.calls[-1].content)["record"]
        self.assertNotIn("Kulturbytes", record["text"])
        result = self.invoke([*args, "--publish"], source_roots=[sources])
        self.assertNotEqual(result.exit_code, 0)

    def test_unicode_limits_protected_links_and_golden_output(self):
        self.assertEqual(grapheme_count("👩‍💻e\u0301"), 2)
        self.assertEqual(grapheme_words("a \u0301 b 👩‍💻"), ["a \u0301", "b", "👩‍💻"])
        self.assertTrue(bluesky_text_fits("e\u0301" * 300))
        self.assertFalse(bluesky_text_fits("a" * 301))
        self.assertFalse(bluesky_text_fits("a" + "\u0301" * 1600))
        item = ContentItem(
            title="Title",
            text="👩‍💻 hello " * 300,
            link="https://example.org/über",
            tags=["Keep"],
        )
        text = render_post(item, "bluesky").text
        self.assertTrue(bluesky_text_fits(text))
        self.assertIn(item.link, text)
        self.assertIn("#Keep", text)
        with self.assertRaises(click.ClickException):
            render_post(ContentItem(title="a" * 301), "bluesky")
        golden = (
            (Path(__file__).parent / "fixtures/bluesky_kulturbytes.txt")
            .read_text()
            .rstrip("\n")
        )
        self.assertEqual(render_post(self.item, "bluesky").text, golden)
        self.assertEqual(
            ImageSettings(ratio={"bluesky": "4/3"}, type={"bluesky": "jpg"}).type[
                "bluesky"
            ],
            "jpg",
        )
        with self.assertRaises(ValueError):
            ImageSettings(ratio={"blusky": "4/3"})

    def test_declined_confirmation_dry_image_and_database_path(self):
        conn = self.connection()
        item = canonical(
            {**EVENT, "images": {"main": {"url": "https://api.kulturbytes.de/image"}}}
        )
        with self.client() as client, patch("click.confirm", return_value=False):
            self.assertFalse(bluesky.publish_event(client, conn, item, True))
            self.assertFalse(
                bluesky.publish_event(client, conn, item, False, session=SESSION)
            )
        self.assertEqual(self.calls, [])
        self.assertEqual(
            conn.execute("SELECT count(*) FROM publication_attempts").fetchone()[0], 0
        )
        from kulturbytes_common.database import get_database_path

        with patch.dict(
            os.environ, {"BLUESKY_DATABASE_PATH": str(self.db)}, clear=True
        ):
            self.assertEqual(get_database_path("bluesky"), self.db)

    def test_blob_transport_uncertainty_keeps_blob_stage(self):
        conn = self.connection()
        item = canonical(
            {**EVENT, "images": {"main": {"url": "https://api.kulturbytes.de/image"}}}
        )
        calls = []

        def respond(request):
            calls.append(request)
            if request.method == "GET":
                return httpx.Response(
                    200, content=JPEG, headers={"Content-Type": "image/jpeg"}
                )
            raise httpx.ConnectError(JWT, request=request)

        with (
            self.client(respond) as client,
            patch("click.confirm", return_value=True),
            self.assertRaises(click.ClickException),
        ):
            bluesky.publish_event(client, conn, item, False, session=SESSION)
        self.assertEqual(len(calls), 2)
        self.assertEqual(
            conn.execute(
                "SELECT state,mutation_stage FROM publication_attempts"
            ).fetchone(),
            ("publishing", "bluesky_blob"),
        )

    def test_successful_remote_post_with_failed_finalize_remains_recoverable(self):
        conn = self.connection()
        with (
            self.client() as client,
            patch("click.confirm", return_value=True),
            patch.object(
                bluesky,
                "remember_post",
                side_effect=sqlite3.OperationalError("local failure"),
            ),
            self.assertRaises(click.ClickException),
        ):
            bluesky.publish_event(client, conn, self.item, False, session=SESSION)
        attempt, state, remote_id = conn.execute(
            "SELECT attempt_uuid,state,remote_id FROM publication_attempts"
        ).fetchone()
        self.assertEqual((state, remote_id), ("remote_succeeded", URI))
        with self.assertRaises(click.ClickException):
            resolve_attempt(conn, attempt, "failed", Mock())
        resolve_attempt(
            conn,
            attempt,
            "published",
            lambda event, uri, url: bluesky.remember_post(
                conn, event, uri, url, commit=False
            ),
        )
        self.assertEqual(get_attempt(conn, attempt)["state"], "published")

    def test_malformed_create_record_json_preserves_uncertainty(self):
        conn = self.connection()
        with (
            self.client(
                lambda r: httpx.Response(200, content=PASSWORD.encode())
            ) as client,
            patch("click.confirm", return_value=True),
            self.assertRaises(click.ClickException) as raised,
        ):
            bluesky.publish_event(client, conn, self.item, False, session=SESSION)
        self.assertNotIn(PASSWORD, str(raised.exception))
        self.assertEqual(
            conn.execute("SELECT state FROM publication_attempts").fetchone()[0],
            "publishing",
        )

    def test_wheel_contains_bluesky_code(self):
        repo = Path(__file__).resolve().parents[1]
        output = self.root / "dist"
        result = subprocess.run(
            [
                "uv",
                "build",
                "--package",
                "kulturbytes-bluesky",
                "--out-dir",
                str(output),
            ],
            cwd=repo,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        wheel = next(output.glob("*.whl"))
        with zipfile.ZipFile(wheel) as archive:
            for module in ("__init__", "auth", "publishing", "cli"):
                self.assertIn(f"kulturbytes_bluesky/{module}.py", archive.namelist())
