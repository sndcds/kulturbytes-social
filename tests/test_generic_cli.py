import os
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import httpx
from click.testing import CliRunner
from dotenv_support import HTTPXClient, IsolatedEnvironmentTestCase

from kulturbytes_common.sources.models import RenderedPost
from kulturbytes_facebook import cli as facebook
from kulturbytes_instagram import cli as instagram
from kulturbytes_mastodon import cli as mastodon
from kulturbytes_social.cli import cli


class GenericCLITests(IsolatedEnvironmentTestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.sources = self.root / "sources"
        self.sources.mkdir()
        for name in ("flat", "nested"):
            fields = (
                "  id: id\n  title: name\n  text: description\n  city: city\n  image_url: picture"
                if name == "flat"
                else "  id: event.id\n  title: event.headline\n  text: event.body\n  city: event.location.city\n  image_url: media[0].url"
            )
            (self.sources / f"{name}.yaml").write_text(
                f"name: {name}\nadapter: json\nmedia:\n  allowed_hosts: [images.example.org]\nendpoint: https://example.org/{name}\nroot: "
                + ("events" if name == "flat" else "data.items")
                + "\nfields:\n"
                + fields
                + "\n"
            )
        self.item = {
            "id": "1",
            "name": "Jazzabend",
            "description": "Musik aus einer JSON-Quelle.",
            "city": "Flensburg",
            "picture": "https://images.example.org/image.jpg",
        }
        self.calls = []

    def invoke(
        self,
        platform="facebook",
        args=(),
        input="",
        payload=None,
        source="flat",
        generic_command=False,
    ):
        def respond(request):
            self.calls.append(request)
            if request.url.host == "example.org":
                self.assertNotIn("Authorization", request.headers)
                if payload is not None:
                    return httpx.Response(200, json=payload)
                if request.url.path == "/flat":
                    return httpx.Response(200, json={"events": [self.item]})
                nested = {
                    "event": {
                        "id": self.item.get("id"),
                        "headline": self.item["name"],
                        "body": self.item.get("description"),
                        "location": {"city": self.item.get("city")},
                    },
                    "media": [{"url": self.item["picture"]}],
                }
                return httpx.Response(200, json={"data": {"items": [nested]}})
            if request.url.path == "/api/v2/instance":
                return httpx.Response(
                    200, json={"configuration": {"statuses": {"max_characters": 500}}}
                )
            if request.url.host == "images.example.org":
                return httpx.Response(
                    200,
                    content=b"\xff\xd8\xffJPEG",
                    headers={"Content-Type": "image/jpeg"},
                )
            if request.method == "GET":
                return httpx.Response(
                    200,
                    json={
                        "status_code": "FINISHED",
                        "url": "https://norden.social/image",
                    },
                )
            return httpx.Response(200, json={"id": "123"})

        module = {"facebook": facebook, "instagram": instagram, "mastodon": mastodon}[
            platform
        ]
        env = {
            "FACEBOOK_PAGE_ID": "123",
            "FACEBOOK_PAGE_ACCESS_TOKEN": "test-secret",
            "INSTAGRAM_USER_ID": "123",
            "INSTAGRAM_ACCESS_TOKEN": "test-secret",
            "MASTODON_ACCESS_TOKEN": "test-secret",
            "META_SYSTEM_USER_ACCESS_TOKEN": "",
        }
        with (
            patch.dict(os.environ, env, clear=True),
            patch(
                "kulturbytes_common.sources.loader.config_roots",
                return_value=[self.sources],
            ),
            patch.object(module, "DATABASE_PATH", self.root / f"{platform}.db"),
            patch.object(
                httpx,
                "Client",
                side_effect=lambda **kw: HTTPXClient(
                    **{**kw, "transport": httpx.MockTransport(respond)}
                ),
            ),
            patch.object(facebook, "authenticate", side_effect=facebook.load_config),
            patch.object(instagram, "authenticate", side_effect=instagram.load_config),
        ):
            result = CliRunner().invoke(
                cli,
                (["publish", "--platform", platform] if generic_command else [platform])
                + ["--source", source, *args],
                input=input,
            )
        return result

    def test_flat_and_nested_sources_work_without_python_adapters(self):
        for platform in ("facebook", "instagram", "mastodon"):
            outputs = []
            for source in ("flat", "nested"):
                result = self.invoke(platform, ["--item-id", "1"], source=source)
                self.assertEqual(
                    result.exit_code, 0, result.output + str(result.exception)
                )
                self.assertIn("Jazzabend", result.output)
                self.assertIn("DRY RUN", result.output)
                self.assertNotIn("Welche Inhalte", result.output)
                outputs.append(
                    result.output.replace(f"{source}-Einträge", "source-Einträge")
                )
            self.assertEqual(outputs[0], outputs[1])
        self.assertTrue(all(request.method == "GET" for request in self.calls))

    def test_generic_publish_uses_rendered_post_and_source_scoped_history(self):
        actual = facebook.publish_facebook_photo
        received = []

        def publish(client, post, **kwargs):
            self.assertIsInstance(post, RenderedPost)
            received.append(post)
            return actual(client, post, **kwargs)

        with patch.object(facebook, "publish_facebook_photo", side_effect=publish):
            for source in ("flat", "nested"):
                result = self.invoke(
                    args=["--item-id", "1", "--publish"], input="y\n", source=source
                )
                self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(len(received), 2)
        with closing(sqlite3.connect(self.root / "facebook.db")) as conn, conn:
            self.assertEqual(
                set(
                    row[0]
                    for row in conn.execute("SELECT date_uuid FROM published_events")
                ),
                {"flat:1", "nested:1"},
            )
        result = self.invoke(args=["--item-id", "1", "--publish"], input="y\n")
        self.assertNotEqual(result.exit_code, 0)

    def test_all_publishers_complete_generic_remote_flow(self):
        columns = {
            "facebook": "facebook_post_id",
            "instagram": "instagram_media_id",
            "mastodon": "mastodon_status_id",
        }
        for platform, column in columns.items():
            with self.subTest(platform=platform):
                result = self.invoke(
                    platform, ["--item-id", "1", "--publish"], input="y\n"
                )
                self.assertEqual(
                    result.exit_code, 0, result.output + str(result.exception)
                )
                with (
                    closing(sqlite3.connect(self.root / f"{platform}.db")) as conn,
                    conn,
                ):
                    row = conn.execute(
                        f"SELECT date_uuid, {column} FROM published_events"
                    ).fetchone()
                self.assertEqual(row, ("flat:1", "123"))

    def test_confirmation_and_repeat_are_required(self):
        self.invoke(args=["--publish"], input="1\nn\n")
        self.assertFalse(any(request.method == "POST" for request in self.calls))
        self.assertEqual(self.invoke(args=["--publish"], input="1\ny\n").exit_code, 0)
        previous = sum(request.method == "POST" for request in self.calls)
        self.invoke(args=["--publish", "--include-published"], input="1\ny\nn\n")
        self.assertEqual(
            sum(request.method == "POST" for request in self.calls), previous
        )
        self.assertEqual(
            self.invoke(
                args=["--publish", "--include-published"], input="1\ny\ny\n"
            ).exit_code,
            0,
        )
        self.assertEqual(
            sum(request.method == "POST" for request in self.calls), previous + 1
        )

    def test_title_only_preview_and_publish_requires_id(self):
        self.item = {"name": "Only title"}
        result = self.invoke(input="1\n")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("DRY RUN", result.output)
        result = self.invoke(args=["--publish"], input="1\ny\n")
        self.assertIn("stabile Quellen-ID", result.output)
        self.assertFalse(any(request.method == "POST" for request in self.calls))

    def test_direct_id_before_limit_filters_and_flag_compatibility(self):
        payload = {
            "events": [dict(self.item, id="first"), dict(self.item, id="chosen")]
        }
        result = self.invoke(
            args=["--item-id", "chosen", "--limit", "1"], payload=payload
        )
        self.assertEqual(result.exit_code, 0, result.output)
        result = self.invoke(
            args=["--item-id", "chosen", "--city", "Hamburg"], payload=payload
        )
        self.assertNotEqual(result.exit_code, 0)
        result = self.invoke(args=["--event-uuid", "1", "--date-identifier", "1"])
        self.assertEqual(result.exit_code, 2)

    def test_source_management_never_connects_or_resolves_credentials(self):
        with (
            patch("httpx.Client", side_effect=AssertionError("Unexpected HTTP")),
            patch(
                "kulturbytes_common.credentials.get_secret",
                side_effect=AssertionError("Unexpected credential lookup"),
            ),
        ):
            for args in (
                ["sources", "list"],
                ["sources", "validate", "kulturbytes"],
                ["sources", "validate", "example-simple"],
                ["sources", "validate", "example-nested"],
            ):
                result = CliRunner().invoke(cli, args)
                self.assertEqual(
                    result.exit_code, 0, result.output + str(result.exception)
                )

    def test_untrusted_image_still_uses_media_security(self):
        self.item["picture"] = "https://127.0.0.1/private.jpg"
        result = self.invoke("instagram", ["--item-id", "1"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertFalse(any(request.url.host == "127.0.0.1" for request in self.calls))
