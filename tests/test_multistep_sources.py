"""Generic two-stage configuration, hostile placeholders and historical identity."""

from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import httpx
import test_generic_core
from dotenv_support import IsolatedEnvironmentTestCase
from test_publishers import EVENT, SUMMARY

from kulturbytes_common.rendering import TemplateRenderer
from kulturbytes_common.sources.errors import (
    SourceConfigurationError,
    SourceValidationError,
)
from kulturbytes_common.sources.generic import JsonSourceAdapter
from kulturbytes_common.sources.loader import load_source
from kulturbytes_common.sources.models import PublicationIdentity


class MultistepTests(IsolatedEnvironmentTestCase):
    definition = test_generic_core.RequestTests.definition
    fetcher = test_generic_core.RequestTests.fetcher

    def synthetic(self, **overrides):
        return self.definition(
            list={
                "url": "https://content.example.org/records",
                "root": "records",
                "fields": {"id": "record_id", "title": "headline"},
            },
            detail={
                "url": "https://content.example.org/records/{record}/{slug}",
                "root": "item",
                "placeholders": {"record": "list.record_id", "slug": "list.slug"},
                "identity_checks": [
                    {"left": "list.record_id", "right": "detail.identifier"}
                ],
            },
            fields={
                "id": "list.record_id",
                "title": "detail.headline",
                "text": "list.summary || detail.body",
            },
            **overrides,
        )

    def test_synthetic_list_detail_mapping_and_direct_lookup(self):
        for direct in (False, True):
            adapter = JsonSourceAdapter(self.synthetic())
            calls = []

            def handle(request):
                calls.append(request)
                return httpx.Response(
                    200,
                    json={
                        "records": [
                            {
                                "record_id": "123",
                                "slug": "blue/red ?#%",
                                "headline": "Preview",
                            }
                        ]
                    }
                    if len(calls) == 1
                    else {
                        "item": {
                            "identifier": "123",
                            "headline": "Final",
                            "body": "Text",
                        }
                    },
                )

            with self.fetcher(handle):
                preview = adapter.list_items(None, target="123" if direct else None)[0]
                self.assertEqual(preview.title, "Preview")
                item = adapter.get_item(None, preview)
            self.assertEqual(item.title, "Final")
            self.assertEqual(item.text, "Text")
            self.assertEqual(
                item._source_context.identity.publication_key, "museum:123"
            )
            self.assertEqual(
                calls[1].url.raw_path, b"/records/123/blue%2Fred%20%3F%23%25"
            )
            self.assertEqual(
                set(item.model_dump())
                & {"list", "detail", "raw_list", "_source_context"},
                set(),
            )
            self.assertEqual(
                TemplateRenderer().render(item, "facebook").text, "Final\n\nText"
            )

    def test_placeholder_declarations_and_origins_fail_at_load(self):
        for url, placeholders in [
            (
                "https://{record}.example.org/items/{slug}",
                {"record": "list.id", "slug": "list.slug"},
            ),
            (
                "https://example.org:{port}/items/{record}",
                {"port": "list.port", "record": "list.id"},
            ),
            (
                "{scheme}://example.org/items/{record}",
                {"scheme": "list.scheme", "record": "list.id"},
            ),
            (
                "https://example.org/{record}?q={slug}",
                {"record": "list.id", "slug": "list.slug"},
            ),
            (
                "https://example.org/{record}#{slug}",
                {"record": "list.id", "slug": "list.slug"},
            ),
            ("https://example.org/{record}/{record}", {"record": "list.id"}),
            (
                "https://example.org/{record}",
                {"record": "list.id", "unused": "list.other"},
            ),
            ("https://example.org/{unknown}", {"record": "list.id"}),
            ("https://example.org/{bad-name}", {"bad-name": "list.id"}),
            ("https://example.org/{record}", {"record": "["}),
            ("https://example.org/{record}", {"record": 123}),
        ]:
            with self.subTest(url=url), self.assertRaises(SourceConfigurationError):
                self.definition(
                    detail={"url": url, "root": "item", "placeholders": placeholders}
                )

    def test_placeholder_values_fail_before_http(self):
        request = self.synthetic().detail
        for value in (None, "", "  ", ".", "..", [], ["one"], {}, 42, True):
            with self.subTest(value=value), self.assertRaises(SourceConfigurationError):
                request.item_url(context={"list": {"record_id": value, "slug": "blue"}})

    def test_identity_checks_reject_missing_nonscalar_and_type_changes(self):
        adapter = JsonSourceAdapter(self.synthetic())
        for left, right in [
            (None, None),
            ("123", None),
            ("123", "456"),
            (1, True),
            ([], []),
            ({}, {}),
            ("", ""),
            ("\n", "\n"),
        ]:
            with (
                self.subTest(left=left, right=right),
                self.assertRaises(SourceValidationError),
            ):
                adapter.map_detail(
                    {"identifier": right, "headline": "Final"},
                    listed={"record_id": left},
                )

    def test_kulturbytes_runtime_and_historical_keys(self):
        adapter = load_source("kulturbytes")
        self.assertIs(type(adapter), JsonSourceAdapter)
        item = adapter.map_detail(EVENT, listed=SUMMARY)
        self.assertEqual(item.id, "date-1")
        self.assertEqual(
            item._source_context.identity,
            PublicationIdentity("date-1", "event-1", "209901011830"),
        )
        self.assertEqual(
            item.media_policy.allowed_hosts, frozenset({"api.kulturbytes.de"})
        )
        self.assertEqual(item.tags, EVENT["tags"])
        self.assertFalse(list(Path("common/src").rglob("kulturbytes.py")))

    def test_each_kulturbytes_relationship_and_summary_priority(self):
        adapter = load_source("kulturbytes")
        for index, mutate in enumerate(
            (
                lambda row: row.update(uuid="other"),
                lambda row: row["date"].update(uuid="other"),
                lambda row: row["date"].update(slug="other"),
            ),
            1,
        ):
            row = deepcopy(EVENT)
            mutate(row)
            with self.assertRaisesRegex(
                SourceValidationError, f"Identitätsprüfung {index}"
            ):
                adapter.map_detail(row, listed=SUMMARY)
        detail = {**EVENT, "summary": "NEVER", "description": "Fallback"}
        for summary, expected in (
            (" List ", "List"),
            ("", "Fallback"),
            (" \t\n", "Fallback"),
            (None, "Fallback"),
        ):
            self.assertEqual(
                adapter.map_detail(detail, listed={**SUMMARY, "summary": summary}).text,
                expected,
            )

    def test_kulturbytes_item_id_and_release_filter(self):
        for target in (None, "date-1", ("event-1", "date-1")):
            for release in ("released", "draft"):
                calls = []

                def handle(request):
                    calls.append(request.url.path)
                    return httpx.Response(
                        200,
                        json={
                            "data": {"events": [{**SUMMARY, "release_status": release}]}
                        }
                        if len(calls) == 1
                        else {"data": EVENT},
                    )

                adapter = load_source("kulturbytes")
                with self.fetcher(handle):
                    items = adapter.list_items(None, target=target)
                    self.assertEqual(len(items), int(release == "released"))
                    if items:
                        adapter.get_item(None, items[0])
                self.assertEqual(calls[0], "/api/events")

    def test_invalid_direct_sibling_and_optional_assertions(self):
        for target in ("date-1", ("event-1", "date-1")):
            with self.fetcher(
                lambda request: httpx.Response(
                    200,
                    json={"data": {"events": [SUMMARY, {**SUMMARY, "summary": []}]}},
                )
            ):
                with self.assertRaises(SourceValidationError):
                    load_source("kulturbytes").list_items(None, target=target)
        for update in (
            {"images": []},
            {"images": {"main": []}},
            {"tags": [True]},
            {"description": 123},
        ):
            with self.assertRaises(SourceValidationError):
                load_source("kulturbytes").map_detail(
                    {**EVENT, **update}, listed=SUMMARY
                )

    def test_publication_identity_cannot_change_after_preview(self):
        definition = self.synthetic(
            identity={
                "publication_key": "detail.identifier || list.record_id",
                "content_key": "list.record_id",
                "revision": "list.slug",
            }
        )
        adapter = JsonSourceAdapter(definition)
        with self.fetcher(
            lambda request: httpx.Response(
                200,
                json={
                    "records": [
                        {"record_id": "123", "slug": "blue", "headline": "Preview"}
                    ]
                },
            )
        ):
            preview = adapter.list_items(None)[0]
        # Even without a configured equality check, reservation identity cannot drift.
        adapter.definition = replace(
            definition, detail=replace(definition.detail, identity_checks=())
        )
        with self.fetcher(
            lambda request: httpx.Response(
                200, json={"item": {"identifier": "456", "headline": "Final"}}
            )
        ):
            with self.assertRaisesRegex(SourceValidationError, "Publikationsidentität"):
                adapter.get_item(None, preview)

    def test_skip_invalid_preserves_duplicate_policy_and_rejects_bad_envelopes(self):
        for payload in ({"data": {"events": [None, 17, SUMMARY]}},):
            with self.fetcher(lambda request: httpx.Response(200, json=payload)):
                self.assertEqual(len(load_source("kulturbytes").list_items(None)), 1)
        adapter = JsonSourceAdapter(self.definition(skip_invalid=True))
        with self.fetcher(
            lambda request: httpx.Response(
                200, json={"data": {"items": [{"id": "1", "name": "A"}] * 2}}
            )
        ):
            with self.assertRaisesRegex(SourceValidationError, "doppelte id"):
                adapter.list_items(None)

    def test_invalid_rule_schemas_and_expressions(self):
        for overrides in (
            {"identity": {"publication_key": "id"}},
            {
                "identity": {
                    "publication_key": "[",
                    "content_key": "id",
                    "revision": "id",
                }
            },
            {"legacy_selectors": {"event_uuid": ["uuid"]}},
            {"filters": [{"expression": "status", "execute": "python"}]},
            {"filters": [{"expression": "status", "truthy": False}]},
            {"derived": {"link": {"template": "{{ secrets }}"}}},
            {"skip_invalid": "true"},
        ):
            with (
                self.subTest(overrides=overrides),
                self.assertRaises(SourceConfigurationError),
            ):
                self.definition(**overrides)
        for rule in (
            {
                "url": "https://example.org/{id}",
                "root": "item",
                "identity_checks": [{"left": "[", "right": "id"}],
            },
            {
                "url": "https://example.org/{id}",
                "root": "item",
                "assertions": {"id": {"type": "python"}},
            },
        ):
            with self.assertRaises(SourceConfigurationError):
                self.definition(detail=rule)

    def test_derived_values_and_optional_price_address(self):
        adapter = load_source("kulturbytes")
        for values, expected in (
            ({"price_type": "free"}, "Eintritt frei"),
            ({"min_price": 0}, "Eintritt: 0 EUR"),
            ({"min_price": 10.5, "max_price": 12}, "Eintritt: 10.5–12 EUR"),
            ({"min_price": 10, "max_price": 10}, "Eintritt: 10 EUR"),
            ({}, None),
        ):
            row = deepcopy(EVENT)
            row["date"].pop("price_type")
            row["date"].update(values)
            self.assertEqual(adapter.map_detail(row, listed=SUMMARY).price, expected)
        row = deepcopy(EVENT)
        for field in ("venue_street", "venue_postal_code", "venue_city", "start_time"):
            row["date"].pop(field)
        item = adapter.map_detail(row, listed=SUMMARY)
        self.assertEqual(item.address, "")
        self.assertEqual(item.time, "00:00")

    def test_normalized_time_preserves_legacy_snapshot(self):
        row = deepcopy(EVENT)
        row["date"]["start_time"] = "18:30:59"
        item = load_source("kulturbytes").map_detail(row, listed=SUMMARY)
        self.assertEqual(item.time, "18:30")
        row["date"].update(price_type="paid", min_price=10, currency=None)
        self.assertEqual(
            load_source("kulturbytes").map_detail(row, listed=SUMMARY).price,
            "Eintritt: 10 None",
        )
