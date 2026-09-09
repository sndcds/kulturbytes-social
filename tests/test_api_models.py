from copy import deepcopy
import click
from dotenv_support import IsolatedEnvironmentTestCase
from unittest.mock import patch
import httpx
from dotenv_support import HTTPXClient
from kulturbytes_common.sources.loader import load_source


def validate_list(payload, *, target=None):
    adapter = load_source("kulturbytes")
    with patch("kulturbytes_common.sources.fetching.source_client", side_effect=lambda: HTTPXClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    )):
        items = adapter.list_items(None, target=target)
    return [adapter._records[id(item)].raw_list for item in items]


def validate_detail(payload):
    adapter = load_source("kulturbytes")
    raw = payload.get("data") if isinstance(payload, dict) else None
    adapter.validate(adapter.definition.detail, raw)
    return raw
from test_publishers import EVENT, SUMMARY


class APIModelTests(IsolatedEnvironmentTestCase):
    def test_envelope_and_sibling_resilience(self):
        for payload in ({}, {'data': {}}, {'data': {'events': {}}}, []):
            with self.assertRaises(click.ClickException):
                validate_list(payload)
        for patch in ({'uuid': '..'}, {'uuid': None}, {'date_uuid': ''}, {'start_date': '2026-02-30'}, {'start_time': 9}, {'venue_city': []}):
            invalid = {**SUMMARY, **patch}
            valid = validate_list({'data': {'events': [SUMMARY, invalid, SUMMARY]}})
            self.assertEqual(len(valid), 2)
        for key in ('uuid', 'date_uuid'):
            bad = {name: value for name, value in SUMMARY.items() if name != key}
            self.assertEqual(validate_list({'data': {'events': [bad, SUMMARY]}}), [SUMMARY])
        self.assertIsNone(validate_list({'data': {'events': [{**SUMMARY, 'venue_city': None}]}})[0]['venue_city'])

    def test_direct_invalid_match_cannot_be_hidden_by_valid_sibling(self):
        bad = {**SUMMARY, 'start_date': 'invalid'}
        with self.assertRaises(click.ClickException):
            validate_list({'data': {'events': [SUMMARY, bad]}}, target=(SUMMARY['uuid'], SUMMARY['date_uuid']))

    def test_detail_fields_and_opaque_ids(self):
        self.assertEqual(validate_detail({'data': EVENT})['uuid'], 'event-1')
        for update in ({'tags': 'not-list'}, {'tags': [1]}, {'images': []}, {'images': {'main': []}},
                       {'images': {'main': {'url': 'file:///etc/passwd'}}}, {'date': {}}, {'date': None}):
            with self.subTest(update=update), self.assertRaises(click.ClickException):
                validate_detail({'data': {**EVENT, **update}})
        for key, value in [('uuid', ''), ('start_date', 'yesterday'), ('min_price', '10'), ('venue_name', {})]:
            bad = deepcopy(EVENT)
            bad['date'][key] = value
            with self.assertRaises(click.ClickException):
                validate_detail({'data': bad})
