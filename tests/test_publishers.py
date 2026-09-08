import importlib
import os
import tempfile
import unittest
from dotenv_support import IsolatedEnvironmentTestCase
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import click
import httpx
from click.testing import CliRunner
from kulturbytes_social.cli import cli
from kulturbytes_common.events import build_address, build_hashtags, format_price
from kulturbytes_common.media import download_image
from kulturbytes_common.selection import parse_selection
ENV = {'FACEBOOK_PAGE_ID': '123', 'FACEBOOK_PAGE_ACCESS_TOKEN': 'test-facebook-token', 'MASTODON_ACCESS_TOKEN': 'test-mastodon-token'}
FACEBOOK = importlib.import_module('kulturbytes_facebook.publisher')
MASTODON = importlib.import_module('kulturbytes_mastodon.publisher')
EVENT = {'uuid': 'event-1', 'title': 'Kulturabend', 'summary': 'Musik und Kultur.', 'tags': ['Kultur', 'kultur', 'Schleswig-Holstein'], 'date': {'uuid': 'date-1', 'slug': '209901011830', 'start_date': '2099-01-01', 'start_time': '18:30', 'venue_name': 'Kulturhaus', 'venue_city': 'Flensburg', 'venue_street': 'Hauptstraße', 'venue_house_number': '1', 'venue_postal_code': '24937', 'price_type': 'free'}}
SUMMARY = {'uuid': 'event-1', 'date_uuid': 'date-1', 'date_slug': '209901011830', 'release_status': 'released', 'start_date': '2099-01-01', 'start_time': '18:30', 'title': 'Kulturabend', 'venue_city': 'Flensburg'}

class SharedFunctionsTests(IsolatedEnvironmentTestCase):

    def test_selection(self):
        self.assertEqual(parse_selection('1,3-5,3', 5), [0, 2, 3, 4])
        self.assertEqual(parse_selection('alle', 3), [0, 1, 2])
        self.assertEqual(parse_selection('', 3), [])
        for value in ['0', '4', '2-1', 'abc']:
            with self.subTest(value=value), self.assertRaises(click.ClickException):
                parse_selection(value, 3)

    def test_formatting(self):
        self.assertEqual(build_address(EVENT), 'Hauptstraße 1, 24937 Flensburg')
        self.assertEqual(build_hashtags(EVENT), '#Kultur #SchleswigHolstein #Kulturbytes #Flensburg')
        self.assertEqual(format_price(EVENT), 'Eintritt frei')

    def test_image_download(self):
        event = deepcopy(EVENT)
        event['images'] = {'main': {'url': 'https://api.kulturbytes.de/image', 'uuid': 'image-1'}}
        with httpx.Client(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=b'image', headers={'Content-Type': 'image/png; charset=binary'})
        )) as client:
            self.assertEqual(download_image(client, event), (b'image', 'image/png', 'image-1.png'))
            with self.assertRaises(ValueError):
                download_image(client, EVENT)
