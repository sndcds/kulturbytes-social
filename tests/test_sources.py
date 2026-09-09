"""Canonical boundaries and configured source extraction; no external HTTP calls."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import httpx
import jmespath
from dotenv_support import HTTPXClient, IsolatedEnvironmentTestCase
from kulturbytes_common.sources.errors import (
    SourceConfigurationError,
    SourceMappingError,
    SourceNotFound,
    SourceValidationError,
)
from kulturbytes_common.sources.generic import JsonSourceAdapter
from kulturbytes_common.sources.loader import definitions, load_definition, load_source
from kulturbytes_common.sources.mapping import map_item
from kulturbytes_common.sources.models import RenderedPost, SocialItem
from pydantic import ValidationError


class SourceTests(IsolatedEnvironmentTestCase):
    def definition(self, code):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "source.yaml"
        path.write_text(code)
        return load_definition(path)

    def test_minimal_and_complete_canonical_model(self):
        item = SocialItem(title="Minimal")
        self.assertIsNone(item.date)
        self.assertEqual(item.tags, [])
        item = SocialItem(
            id="opaque id",
            title="Musik",
            subtitle="Abend",
            text="Text",
            city="Flensburg",
            venue="Saal",
            address="Straße 1",
            date="2099-01-01",
            time="18:30",
            end_date="2099-01-02",
            image_url="https://example.org/image.jpg",
            image_alt="Bühne",
            image_name="stage",
            link="https://example.org/event",
            tags=[" Musik ", "Musik"],
            organizer="Verein",
            price="10 Euro",
            ticket_link="https://example.org/tickets",
        )
        self.assertEqual(item.tags, ["Musik"])
        self.assertNotIn("_origin", item.model_dump())
        forbidden = {
            "date_uuid",
            "date_slug",
            "venue_city",
            "images",
            "release_status",
            "org_name",
        }
        self.assertFalse(forbidden & SocialItem.model_fields.keys())

    def test_invalid_types_and_urls_are_rejected(self):
        for values in (
            {"title": ""},
            {"title": " "},
            {"title": 3},
            {"tags": "Musik"},
            {"tags": [1]},
            {"date": "tomorrow"},
            {"time": "25:99"},
            {"image_url": "file:///etc/passwd"},
            {"link": "https://user:secret@host/"},
            {"link": "https://[bad"},
            {"image_url": "https://a.test:bad/x"},
            {"date_uuid": "not canonical"},
        ):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                SocialItem.model_validate({"title": "Valid", **values})
        with self.assertRaises(ValidationError):
            RenderedPost(text="text", image_url="ftp://host/image")

    def test_flat_nested_and_array_extraction_match(self):
        flat = {
            "name": "Jazzabend",
            "city": "Flensburg",
            "picture": "https://example.org/image.jpg",
        }
        nested = {
            "event": {"headline": "Jazzabend", "location": {"city": "Flensburg"}},
            "media": [{"url": flat["picture"]}],
        }
        a = map_item(
            "flat",
            {
                k: jmespath.compile(v)
                for k, v in {
                    "title": "name",
                    "city": "city",
                    "image_url": "picture",
                }.items()
            },
            flat,
        )
        b = map_item(
            "nested",
            {
                k: jmespath.compile(v)
                for k, v in {
                    "title": "event.headline",
                    "city": "event.location.city",
                    "image_url": "media[0].url",
                }.items()
            },
            nested,
        )
        self.assertEqual(a.model_dump(), b.model_dump())

    def test_missing_optional_nulls_and_wrong_required_fields(self):
        expressions = {
            key: jmespath.compile(value)
            for key, value in {
                "title": "title",
                "city": "where.city",
                "tags": "tags",
            }.items()
        }
        item = map_item("test", expressions, {"title": "Only title"})
        self.assertIsNone(item.city)
        self.assertEqual(item.tags, [])
        for raw in (
            {"secret": "do-not-print"},
            {"title": 3},
            {"title": "Valid", "tags": ["ok", False]},
        ):
            with self.assertRaises(SourceValidationError) as error:
                map_item("test", expressions, raw)
            self.assertIn("test", str(error.exception))
            self.assertNotIn("do-not-print", str(error.exception))
        with self.assertRaises(SourceMappingError) as error:
            map_item(
                "test",
                {"title": jmespath.compile("sort(title)")},
                {"title": "secret-value"},
            )
        self.assertIn("title", str(error.exception))
        self.assertNotIn("secret-value", str(error.exception))

    def test_valid_yaml_and_jmespath_compilation(self):
        definition = self.definition(
            "name: test\nadapter: json\nendpoint: https://example.org/events\nroot: data.items\nfields:\n  title: event.headline\n"
        )
        self.assertEqual(definition.root.search({"data": {"items": [1]}}), [1])
        self.assertEqual(
            definition.fields["title"].search({"event": {"headline": "Title"}}), "Title"
        )

    def test_malformed_yaml_duplicate_keys_and_invalid_settings(self):
        good = "name: test\nadapter: json\nendpoint: https://example.org/events\nroot: events\nfields:\n  title: title\n"
        cases = [
            "[broken",
            "name: x\nname: y",
            good.replace("adapter: json", "adapter: arbitrary"),
            good.replace("name: test", "name: ../../secret"),
            good.replace("root: events", 'root: "["'),
            good.replace("  title: title", '  title: "["'),
            good.replace("  title: title", "  headline: title"),
            good.replace("root: events\n", ""),
            good.replace(
                "https://example.org/events", "https://user:secret@example.org/events"
            ),
            good.replace("https://example.org/events", "file:///secret"),
            good.replace("  title: title", "  title: 42"),
        ]
        for code in cases:
            with (
                self.subTest(code=code),
                self.assertRaises(SourceConfigurationError) as error,
            ):
                self.definition(code)
            self.assertNotIn("secret", str(error.exception))

    def test_duplicate_source_name_and_unknown_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("one", "two"):
                (root / f"{name}.yaml").write_text(
                    "name: kulturbytes\nadapter: kulturbytes\n"
                )
            with self.assertRaises(SourceConfigurationError):
                definitions([root])
        for name in ("unknown", "../outside"):
            with self.assertRaises(SourceNotFound):
                load_source(name)

    def fetch(self, payload, *, root="events", target=None):
        definition = self.definition(
            f'name: test\nadapter: json\nendpoint: https://example.org/events\nroot: "{root}"\nfields:\n  id: id\n  title: name\n'
        )
        calls = []

        def handle(request):
            calls.append(request)
            self.assertEqual(request.method, "GET")
            self.assertNotIn("Authorization", request.headers)
            self.assertNotIn("Cookie", request.headers)
            return httpx.Response(200, json=payload)

        with (
            HTTPXClient(
                headers={"Authorization": "Bearer social-secret"},
                cookies={"private": "social-secret"},
            ) as parent,
            patch(
                "kulturbytes_common.sources.generic.httpx.Client",
                side_effect=lambda **kw: HTTPXClient(
                    transport=httpx.MockTransport(handle), **kw
                ),
            ) as factory,
        ):
            items = JsonSourceAdapter(definition).list_items(parent, target=target)
            self.assertIs(factory.call_args.kwargs["trust_env"], False)
            self.assertFalse(factory.call_args.kwargs["follow_redirects"])
        return items, calls

    def test_collection_roots_and_stable_namespaced_identity(self):
        for root, payload in [
            ("events", {"events": [{"id": "1", "name": "Title"}]}),
            ("places", {"places": [{"id": "1", "name": "Title"}]}),
            ("data.items", {"data": {"items": [{"id": "1", "name": "Title"}]}}),
            ("@", [{"id": "1", "name": "Title"}]),
        ]:
            items, calls = self.fetch(payload, root=root, target="1")
            self.assertEqual(items[0]._origin.key, "test:1")
            self.assertEqual(len(calls), 1)

    def test_invalid_root_missing_target_and_duplicate_ids_fail_closed(self):
        for payload in ({}, {"events": {}}, {"events": None}):
            with self.assertRaises(SourceMappingError):
                self.fetch(payload)
        with self.assertRaises(SourceNotFound):
            self.fetch({"events": []}, target="absent")
        with self.assertRaises(SourceValidationError):
            self.fetch({"events": [{"id": "1", "name": "A"}, {"id": "1", "name": "B"}]})

    def test_source_http_errors_redact_response_and_exception(self):
        definition = self.definition(
            "name: test\nadapter: json\nendpoint: https://example.org/events?key=private-key\nroot: events\nfields:\n  title: name\n"
        )
        for outcome in ("invalid-json", "503", "timeout", "redirect"):
            calls = []

            def handle(request):
                calls.append(request)
                if outcome == "timeout":
                    raise httpx.ReadTimeout("private-key")
                return httpx.Response(
                    200
                    if outcome == "invalid-json"
                    else 302
                    if outcome == "redirect"
                    else 503,
                    content=b"private-key",
                    headers={"Location": "https://other.test/private-key"},
                )

            with (
                patch(
                    "kulturbytes_common.sources.generic.source_client",
                    side_effect=lambda: HTTPXClient(
                        transport=httpx.MockTransport(handle)
                    ),
                ),
                self.assertRaises(SourceMappingError) as error,
            ):
                JsonSourceAdapter(definition).list_items(None)
            self.assertNotIn("private-key", str(error.exception))
            self.assertEqual(len(calls), 3 if outcome in ("503", "timeout") else 1)
