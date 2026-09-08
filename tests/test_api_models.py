from copy import deepcopy
import click
from dotenv_support import IsolatedEnvironmentTestCase
from kulturbytes_common.models import validate_list, validate_detail
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
