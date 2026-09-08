import click
import os
import tempfile
import unittest
from dotenv_support import IsolatedEnvironmentTestCase
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs
import httpx
from click.testing import CliRunner
from kulturbytes_social.cli import cli
from kulturbytes_common.events import get_event_url
from kulturbytes_common.formatting import strip_markdown
from kulturbytes_instagram import publisher as instagram
EVENT = {'uuid': 'event-1', 'title': '**Kulturabend**', 'description': 'Detailbeschreibung.', 'summary': 'Diese Detail-Summary darf nicht verwendet werden.', 'tags': ['Musik', 'musik', 'Open Data', 'Kunst', 'Kultur', 'Lesung'], 'images': {'main': {'url': 'https://api.kulturbytes.de/api/image/image-1'}}, 'date': {'uuid': 'date-1', 'slug': '209901011830', 'start_date': '2099-01-01', 'start_time': '18:30', 'venue_name': 'Kulturhaus', 'venue_city': 'Flensburg'}}
SUMMARY = {'uuid': 'event-1', 'date_uuid': 'date-1', 'date_slug': '209901011830', 'release_status': 'released', 'start_date': '2099-01-01', 'start_time': '18:30', 'title': 'Kulturabend', 'venue_city': 'Flensburg', 'summary': 'Zusammenfassung aus der Liste.'}
ENV = {'INSTAGRAM_USER_ID': '123', 'INSTAGRAM_ACCESS_TOKEN': 'secret-token', 'INSTAGRAM_LOGIN_TYPE': 'instagram', 'INSTAGRAM_GRAPH_API_VERSION': 'v26.0'}
DIRECT = ['--event-uuid', 'event-1', '--date-identifier', 'date-1']

class InstagramTests(IsolatedEnvironmentTestCase):

    def test_caption_limit_preserves_url_and_required_hashtags(self):
        event = deepcopy(EVENT)
        event['summary'] = '**Langer Text** ' * 1000
        caption = instagram.build_instagram_caption(event)
        self.assertLessEqual(len(caption), 2200)
        self.assertIn(get_event_url(event), caption)
        self.assertNotIn('**', caption)
        hashtags = caption.splitlines()[-1].split()
        self.assertEqual(len(hashtags), 5)
        self.assertIn('#Kulturbytes', hashtags)
        self.assertIn('#Flensburg', hashtags)
        event['title'] = 'A' * 2300
        with self.assertRaises(click.ClickException):
            instagram.build_instagram_caption(event)

    def test_shared_markdown_normalization(self):
        self.assertEqual(strip_markdown(r'**Text** 7\. September [Website](https://example.org)'),
                         'Text 7. September Website: https://example.org')
