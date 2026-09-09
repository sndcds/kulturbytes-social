"""Request/detail semantics, true content diversity and policy isolation."""

import ast
import socket
import tempfile
from pathlib import Path
from unittest.mock import patch

import click
import httpx
import test_generic_cli as generic_cli
import yaml
from click.testing import CliRunner
from dotenv_support import HTTPXClient, IsolatedEnvironmentTestCase

from kulturbytes_common.media_security import (
    PublicMediaTransport,
    media_response,
)
from kulturbytes_common.network import MediaPolicy, PinnedTransport
from kulturbytes_common.rendering import TemplateRenderer
from kulturbytes_common.sources.errors import (
    SourceConfigurationError,
    SourceFetchError,
    SourceMappingError,
    SourceValidationError,
)
from kulturbytes_common.sources.generic import JsonSourceAdapter
from kulturbytes_common.sources.loader import definitions, load_definition
from kulturbytes_common.sources.models import ContentItem
from kulturbytes_social.cli import cli


class RequestTests(IsolatedEnvironmentTestCase):
    def definition(self, **overrides):
        raw = {
            "name": "museum",
            "adapter": "json",
            "list": {
                "url": "https://content.example.org/items",
                "root": "data.items",
                "mode": "collection",
            },
            "fields": {"id": "id", "title": "name"},
            **overrides,
        }
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "source.yaml"
        path.write_text(yaml.safe_dump(raw))
        return load_definition(path)

    def fetcher(self, handler):
        def factory():
            return HTTPXClient(transport=httpx.MockTransport(handler), trust_env=False)

        return patch(
            "kulturbytes_common.sources.fetching.source_client", side_effect=factory
        )

    def test_list_detail_mapping_and_identity(self):
        definition = self.definition(
            detail={
                "url": "https://content.example.org/items/{id}",
                "root": "data",
                "mode": "object",
                "fields": {"id": "id", "title": "headline", "text": "body"},
            }
        )
        calls = []

        def handle(request):
            calls.append(request)
            return httpx.Response(
                200,
                json={"data": {"items": [{"id": "1", "name": "List title"}]}}
                if len(calls) == 1
                else {
                    "data": {"id": "1", "headline": "Detail title", "body": "Full body"}
                },
            )

        adapter = JsonSourceAdapter(definition)
        with self.fetcher(handle):
            item = adapter.list_items(None)[0]
            self.assertEqual(item.title, "List title")
            enriched = adapter.get_item(None, item)
        self.assertEqual(enriched.text, "Full body")
        self.assertEqual(enriched._source_context.identity.publication_key, "museum:1")
        self.assertEqual([r.url.path for r in calls], ["/items", "/items/1"])

    def test_direct_detail_skips_list_and_encodes_opaque_id(self):
        adapter = JsonSourceAdapter(
            self.definition(
                detail={"url": "https://content.example.org/items/{id}", "root": "data"}
            )
        )
        calls = []
        target = "one/two ?#ü"

        def handle(request):
            calls.append(request)
            return httpx.Response(200, json={"data": {"id": target, "name": "Direct"}})

        with self.fetcher(handle):
            selected = adapter.list_items(None, target=target)
            self.assertIs(adapter.get_item(None, selected[0]), selected[0])
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].url.raw_path, b"/items/one%2Ftwo%20%3F%23%C3%BC")
        self.assertFalse(calls[0].url.query)
        for value in (".", "..", ""):
            with self.assertRaises(SourceConfigurationError):
                adapter.definition.detail.item_url(value)

    def test_detail_requires_matching_unique_identity(self):
        for mode, payload in [
            ("object", {"data": {"id": "other", "name": "Wrong"}}),
            ("collection", {"data": []}),
            (
                "collection",
                {"data": [{"id": "1", "name": "A"}, {"id": "1", "name": "B"}]},
            ),
        ]:
            adapter = JsonSourceAdapter(
                self.definition(
                    detail={
                        "url": "https://content.example.org/items/{id}",
                        "root": "data",
                        "mode": mode,
                    }
                )
            )
            with (
                self.fetcher(lambda r: httpx.Response(200, json=payload)),
                self.assertRaises(SourceValidationError),
            ):
                adapter.list_items(None, target="1")

    def test_collection_and_object_modes_are_explicit(self):
        for mode, payload, valid in [
            ("object", {"id": "1", "name": "Article"}, True),
            ("object", [], False),
            ("collection", [{"id": "1", "name": "Article"}], True),
            ("collection", {}, False),
        ]:
            adapter = JsonSourceAdapter(
                self.definition(
                    list={
                        "url": "https://content.example.org/item",
                        "root": "data",
                        "mode": mode,
                    }
                )
            )
            with (
                self.subTest(mode=mode, payload=payload),
                self.fetcher(lambda r: httpx.Response(200, json={"data": payload})),
            ):
                if valid:
                    self.assertEqual(adapter.list_items(None)[0].title, "Article")
                else:
                    with self.assertRaises(SourceMappingError):
                        adapter.list_items(None)

    def test_static_headers_and_queries_and_no_source_cookie_reuse(self):
        definition = self.definition(
            list={
                "url": "https://content.example.org/items?existing=yes",
                "root": "data.items",
                "headers": {
                    "Accept": "application/json",
                    "User-Agent": "MuseumReader",
                    "X-API-Version": "2",
                },
                "query": {"limit": "100"},
            }
        )
        calls = []

        def handle(request):
            calls.append(request)
            return httpx.Response(
                200,
                json={"data": {"items": []}},
                headers={"Set-Cookie": "source-secret=private"},
            )

        with self.fetcher(handle):
            adapter = JsonSourceAdapter(definition)
            adapter.list_items(None)
            adapter.list_items(None)
        self.assertEqual(calls[0].headers["X-API-Version"], "2")
        self.assertEqual(calls[0].url.params["limit"], "100")
        self.assertEqual(calls[0].url.params["existing"], "yes")
        for request in calls:
            self.assertNotIn("Cookie", request.headers)
            self.assertNotIn("Authorization", request.headers)

    def test_invalid_request_configuration_is_local_and_redacted(self):
        requests = [
            {"method": "POST"},
            {"method": "get"},
            {"mode": "guess"},
            {"url": "http://example.org/x"},
            {"url": "http://localhost/x"},
            {"url": "https://user:secret@host/x"},
            {"url": "https://host:444/x"},
            {"url": "https://host/x#fragment"},
            {"headers": {"Authorization": "secret"}},
            {"headers": {"proxy-authorization": "secret"}},
            {"headers": {"Cookie": "secret"}},
            {"headers": {"Set-Cookie": "secret"}},
            {"headers": {"X-API-Key": "secret"}},
            {"headers": {"Accept": "ok\r\nAuthorization: secret"}},
            {"headers": {"Accept": "a", "accept": "b"}},
            {"query": {"limit": 100}},
            {"query": {"x": ["a"]}},
            {"unknown": True},
        ]
        for override in requests:
            with (
                self.subTest(override=override),
                patch("httpx.Client", side_effect=AssertionError("HTTP")),
                self.assertRaises(SourceConfigurationError) as error,
            ):
                self.definition(
                    list={
                        "url": "https://content.example.org/items",
                        "root": "@",
                        **override,
                    }
                )
            self.assertNotIn("secret", str(error.exception))

    def test_placeholder_and_policy_validation(self):
        for url in (
            "https://{id}.example.org/x",
            "https://example.org/x?key={id}",
            "https://example.org/{slug}",
            "https://example.org/{{id}}",
            "https://example.org/{id}/{id}",
            "https://example.org/no-placeholder",
            "https://example.org/{id}/{other}",
        ):
            with self.subTest(url=url), self.assertRaises(SourceConfigurationError):
                self.definition(detail={"url": url, "root": "data"})
        for media in (
            {"allowed_hosts": "images.example.org"},
            {"allowed_hosts": ["https://images.example.org"]},
            {"allowed_hosts": ["*.example.org"]},
            {"allowed_hosts": ["images.example.org:443"]},
            {"allowed_hosts": [1]},
            {"unknown": True},
        ):
            with self.assertRaises(SourceConfigurationError):
                self.definition(media=media)
        with self.assertRaises(SourceConfigurationError):
            self.definition(behavior={"skip_past": "true"})

    def test_actual_source_transport_pins_and_blocks_rebinding_redirects(self):
        calls = []

        def handler(request):
            calls.append(request)
            self.assertEqual(request.url.host, "8.8.8.8")
            self.assertEqual(request.headers["Host"], "content.example.org")
            self.assertEqual(request.extensions["sni_hostname"], "content.example.org")
            return httpx.Response(503)

        from kulturbytes_common.sources import fetching

        def factory():
            return HTTPXClient(
                transport=PinnedTransport(factory=lambda: httpx.MockTransport(handler)),
                trust_env=False,
            )

        def records(value):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (value, 443))]

        with (
            patch.object(fetching, "source_client", side_effect=factory),
            patch(
                "socket.getaddrinfo",
                side_effect=[records("8.8.8.8"), records("127.0.0.1")],
            ),
            self.assertRaises(SourceFetchError),
        ):
            JsonSourceAdapter(self.definition()).list_items(None)
        self.assertEqual(len(calls), 1)
        for payload in (
            httpx.Response(302, headers={"Location": "https://127.0.0.1/secret"}),
            httpx.Response(200, content=b"private-payload"),
        ):
            calls = []

            def invalid_response_handler(request):
                calls.append(request)
                return payload

            with (
                self.fetcher(invalid_response_handler),
                self.assertRaises(SourceFetchError),
            ):
                JsonSourceAdapter(self.definition()).list_items(None)
            self.assertEqual(len(calls), 1)

    def test_show_redacts_headers_queries_and_validate_all_bundled_sources(self):
        definition = self.definition(
            list={
                "url": "https://content.example.org/items?token=hidden-query",
                "root": "data.items",
                "headers": {"X-API-Version": "hidden-header"},
                "query": {"key": "hidden-value"},
            }
        )
        with (
            patch(
                "kulturbytes_common.sources.loader.definitions",
                return_value={"museum": definition},
            ),
            patch("httpx.Client", side_effect=AssertionError("HTTP")),
        ):
            result = CliRunner().invoke(cli, ["sources", "show", "museum"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("content.example.org/items", result.output)
        for secret in ("hidden-query", "hidden-header", "hidden-value"):
            self.assertNotIn(secret, result.output)
        for source in definitions():
            for command in ("show", "validate"):
                result = CliRunner().invoke(cli, ["sources", command, source])
                self.assertEqual(result.exit_code, 0, result.output)


class GenericContentTests(IsolatedEnvironmentTestCase):
    setUp = generic_cli.GenericCLITests.setUp
    invoke = generic_cli.GenericCLITests.invoke

    def source(self, name, *, fields, skip_past=False, hosts=()):
        raw = {
            "name": name,
            "adapter": "json",
            "endpoint": "https://example.org/content",
            "root": "items",
            "mode": "collection",
            "fields": fields,
            "behavior": {"skip_past": skip_past},
            "media": {"allowed_hosts": list(hosts)},
        }
        (self.sources / f"{name}.yaml").write_text(yaml.safe_dump(raw))

    def test_place_and_article_preview_and_publish_via_generic_command(self):
        cases = [
            (
                "places",
                {"id": "id", "title": "name", "city": "town", "image_url": "picture"},
                {
                    "id": "p1",
                    "name": "Stadtmuseum",
                    "town": "Flensburg",
                    "picture": "https://images.example.org/image.jpg",
                },
                ("facebook", "instagram", "mastodon"),
            ),
            (
                "articles",
                {"id": "slug", "title": "headline", "text": "body", "link": "url"},
                {
                    "slug": "a1",
                    "headline": "Open Data Day",
                    "body": "A useful article.",
                    "url": "https://example.org/article",
                },
                ("facebook", "mastodon"),
            ),
        ]
        for name, fields, raw, platforms in cases:
            self.source(name, fields=fields, hosts=["images.example.org"])
            for platform in platforms:
                with self.subTest(source=name, platform=platform):
                    args = ["--item-id", raw.get("id", raw.get("slug"))]
                    result = self.invoke(
                        platform,
                        args,
                        source=name,
                        payload={"items": [raw]},
                        generic_command=True,
                    )
                    self.assertEqual(
                        result.exit_code, 0, result.output + str(result.exception)
                    )
                    self.assertIn("DRY RUN", result.output)
                    self.assertNotIn("📅", result.output)
                    result = self.invoke(
                        platform,
                        [*args, "--publish"],
                        input="y\n",
                        source=name,
                        payload={"items": [raw]},
                        generic_command=True,
                    )
                    self.assertEqual(
                        result.exit_code, 0, result.output + str(result.exception)
                    )
        self.assertTrue(any(r.url.host == "images.example.org" for r in self.calls))

    def test_event_mapping_and_configurable_past_dates(self):
        fields = {
            "id": "id",
            "title": "name",
            "date": "start",
            "city": "town",
            "image_url": "picture",
        }
        raw = {
            "id": "e1",
            "name": "Historic announcement",
            "start": "2000-01-01",
            "town": "Flensburg",
        }
        for skip_past in (True, False):
            self.source("kulturbytes-like", fields=fields, skip_past=skip_past)
            result = self.invoke(
                args=["--item-id", "e1"],
                source="kulturbytes-like",
                payload={"items": [raw]},
                generic_command=True,
            )
            self.assertEqual(result.exit_code == 0, not skip_past, result.output)
        raw["start"] = "2099-10-01"
        self.source("event-like", fields=fields, skip_past=True)
        result = self.invoke(
            args=["--item-id", "e1"], source="event-like", payload={"items": [raw]}
        )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("01.10.2099", result.output)

    def test_city_filter_without_city_and_neutral_selection(self):
        self.source("article", fields={"id": "id", "title": "name"})
        payload = {"items": [{"id": "1", "name": "Article"}]}
        result = self.invoke(
            args=["--city", "Flensburg", "--item-id", "1"],
            source="article",
            payload=payload,
        )
        self.assertNotEqual(result.exit_code, 0)
        result = self.invoke(input="\n", source="article", payload=payload)
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Verfügbare Inhalte", result.output)
        self.assertIn("[  1] Article", result.output)
        self.assertNotIn("Veranstaltung", result.output)

    def test_source_media_policy_follows_item_through_render_and_publisher(self):
        fields = {"id": "id", "title": "name", "image_url": "picture"}
        payload = {
            "items": [
                {
                    "id": "1",
                    "name": "Place",
                    "picture": "https://images.example.org/image.jpg",
                }
            ]
        }
        for name, hosts, success in [
            ("source-a", ["images.example.org"], True),
            ("source-b", [], False),
        ]:
            self.source(name, fields=fields, hosts=hosts)
            self.calls = []
            result = self.invoke(
                "facebook",
                ["--item-id", "1", "--publish"],
                input="y\n",
                source=name,
                payload=payload,
                generic_command=True,
            )
            self.assertEqual(result.exit_code == 0, success, result.output)
            self.assertEqual(
                any(r.url.host == "images.example.org" for r in self.calls), success
            )
            self.assertEqual(any(r.method == "POST" for r in self.calls), success)

    def test_private_policy_is_not_mappable_or_template_visible(self):
        item = ContentItem(title="Simple")
        self.assertNotIn("media_policy", item.model_dump())
        self.assertNotIn("_source_context", item.model_dump())
        path = self.root / "templates/default"
        path.mkdir(parents=True)
        for field in ("media_policy", "_source_context", "publication_key"):
            (path / "facebook.j2").write_text("{{ " + field + " }}")
            with self.assertRaises(click.ClickException):
                TemplateRenderer([path.parent]).render(item, "facebook")

    def test_generic_core_and_default_templates_have_no_source_branching(self):
        common = Path(__file__).resolve().parents[1] / "common/src/kulturbytes_common"
        for name in (
            "workflow.py",
            "rendering.py",
            "media_security.py",
            "network.py",
            "storage.py",
            "sources/generic.py",
            "sources/fetching.py",
            "sources/models.py",
        ):
            tree = ast.parse((common / name).read_text())
            literals = [
                node.value
                for node in ast.walk(tree)
                if isinstance(node, ast.Constant) and isinstance(node.value, str)
            ]
            self.assertFalse(
                any(
                    "kulturbytes" in value.lower()
                    and not value.startswith("kulturbytes-social attempts")
                    and "Mit kulturbytes-social attempts" not in value
                    for value in literals
                ),
                name,
            )
        for path in (common / "data/templates/default").glob("*.j2"):
            self.assertNotIn("Kulturbytes", path.read_text())
            self.assertNotIn("Veranstaltung", path.read_text())


class ScopedMediaTests(IsolatedEnvironmentTestCase):
    def test_redirect_requires_destination_policy_and_strips_source_auth(self):
        policy = MediaPolicy(allowed_hosts=["images.a.example", "images.b.example"])
        calls = []

        def handle(request):
            calls.append(request)
            return (
                httpx.Response(
                    302,
                    headers={
                        "Location": "https://images.b.example/finish",
                        "Set-Cookie": "secret=source",
                    },
                )
                if request.url.host == "images.a.example"
                else httpx.Response(200, content=b"jpeg")
            )

        # Real media client policy, test transport at its pinned TCP boundary.
        def client(parent, policy):
            return HTTPXClient(
                transport=PublicMediaTransport(
                    policy, httpx.MockTransport(handle_pinned)
                ),
                trust_env=False,
            )

        def handle_pinned(request):
            self.assertEqual(request.url.host, "8.8.8.8")
            self.assertNotIn("Authorization", request.headers)
            self.assertNotIn("Cookie", request.headers)
            logical = httpx.Request(
                request.method,
                request.url.copy_with(host=request.extensions["sni_hostname"]),
                headers=request.headers,
            )
            return handle(logical)

        with (
            HTTPXClient(
                headers={"Authorization": "Bearer private"},
                cookies={"social": "private"},
            ) as parent,
            patch(
                "kulturbytes_common.media_security.create_media_client",
                side_effect=client,
            ),
        ):
            with media_response(
                parent, "https://images.a.example/start", policy
            ) as response:
                self.assertEqual(response.read(), b"jpeg")
            with self.assertRaises(click.ClickException):
                with media_response(
                    parent,
                    "https://images.a.example/start",
                    MediaPolicy(allowed_hosts=["images.a.example"]),
                ):
                    pass
        self.assertEqual(len(calls), 3)

    def test_shared_ip_uses_distinct_origin_pools(self):
        created = []
        seen = []

        def factory():
            number = len(created)

            def handle(request):
                seen.append(
                    (
                        number,
                        request.extensions["sni_hostname"],
                        request.headers["Host"],
                    )
                )
                return httpx.Response(200, content=b"ok")

            transport = httpx.MockTransport(handle)
            created.append(transport)
            return transport

        policy = MediaPolicy(allowed_hosts=["images.a.example", "images.b.example"])
        with HTTPXClient(
            transport=PublicMediaTransport(policy, factory=factory)
        ) as client:
            for host in ("images.a.example", "images.b.example", "images.a.example"):
                client.get(f"https://{host}/image")
        self.assertEqual(len(created), 2)
        self.assertEqual([row[0] for row in seen], [0, 1, 0])
        self.assertTrue(all(sni == host for _, sni, host in seen))
