import os
import sqlite3
import tempfile
import unittest
from dotenv_support import IsolatedEnvironmentTestCase
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import httpx
from click.testing import CliRunner
from kulturbytes_social.cli import cli

from test_publishers import EVENT, SUMMARY, FACEBOOK, MASTODON, ENV as PUBLISHER_ENV
from test_instagram import ENV, instagram

PLATFORMS = [FACEBOOK, MASTODON, instagram]
DIRECT = ['--event-uuid', 'event-1', '--date-identifier', 'date-1']


class DateIdentityTests(IsolatedEnvironmentTestCase):
    def records(self, database: Path) -> list[tuple]:
        with sqlite3.connect(database) as conn:
            return conn.execute('SELECT * FROM published_events ORDER BY date_uuid').fetchall()

    def run_cli(self, module, database, details, args, user_input):
        requests = []

        def respond(request):
            requests.append(request)
            self.assertEqual(request.method, 'GET')
            self.assertEqual(request.url.host, 'api.kulturbytes.de')
            if request.url.path == '/api/events':
                return httpx.Response(200, json={'data': {'events': [SUMMARY] * len(details)}})
            self.assertEqual(request.url.path, '/api/event/event-1/date/209901011830')
            return httpx.Response(200, json={'data': details[len(requests) - 2]})

        client = httpx.Client(transport=httpx.MockTransport(respond))
        with patch.object(instagram, 'authenticate', side_effect=instagram.load_config), patch.object(FACEBOOK, 'authenticate', side_effect=FACEBOOK.load_config), patch.object(MASTODON, 'get_status_limit', return_value=500), patch.dict(os.environ, {**PUBLISHER_ENV, **ENV, 'META_SYSTEM_USER_ACCESS_TOKEN': ''}, clear=True), patch.object(module, 'DATABASE_PATH', database), patch(
            'kulturbytes_common.workflow.httpx.Client', return_value=client,
        ), patch.object(module, 'publish_event', return_value=True) as publish:
            result = CliRunner().invoke(cli, [module.__name__.split('.')[0].removeprefix('kulturbytes_')] + args, input=user_input)
        return result, requests, publish

    def test_invalid_detail_identity_blocks_all_publishers(self):
        invalid_dates = [dict(EVENT['date'], uuid='date-2'),
                         {k: v for k, v in EVENT['date'].items() if k != 'uuid'},
                         dict(EVENT['date'], uuid=None), dict(EVENT['date'], uuid=''),
                         None, 'invalid', {}]
        for module in PLATFORMS:
            for invalid_date in invalid_dates:
                for direct in [False, True]:
                    for dry_run in [False, True]:
                        for existing in [False, True]:
                            with self.subTest(platform=module.__name__, date=invalid_date,
                                              direct=direct, dry_run=dry_run, existing=existing), tempfile.TemporaryDirectory() as directory:
                                database = Path(directory) / 'posts.sqlite3'
                                with patch.object(module, 'DATABASE_PATH', database):
                                    conn = module.init_database()
                                    try:
                                        if existing:
                                            # Seed both the selected date and the mismatching date.
                                            for date_uuid in ['date-1', 'date-2']:
                                                event = deepcopy(EVENT)
                                                event['date']['uuid'] = date_uuid
                                                extra = ['https://example.test/old'] if module is MASTODON else []
                                                module.remember_post(conn, event, 'old-id', *extra)
                                            conn.execute("UPDATE published_events SET published_at = '2000-01-01 00:00:00'")
                                            conn.commit()
                                    finally:
                                        conn.close()
                                before = self.records(database)
                                event = deepcopy(EVENT)
                                if invalid_date == {}:
                                    event.pop('date')
                                else:
                                    event['date'] = invalid_date
                                original = deepcopy(event)
                                args = (DIRECT if direct else []) + ['--dry-run' if dry_run else '--publish']
                                user_input = '' if direct else '1\n'
                                if existing:
                                    args += ['--include-published']
                                    user_input += 'y\n'
                                result, requests, publish = self.run_cli(module, database, [event], args, user_input)
                                self.assertEqual(result.exit_code, 1 if direct else 0, result.output)
                                publish.assert_not_called()
                                self.assertEqual(len(requests), 2)
                                self.assertEqual(self.records(database), before)
                                self.assertEqual(event, original)
                                for context in ['Quelle kulturbytes', 'Identitätsprüfung 2', 'list.date_uuid',
                                                'detail.date.uuid', 'abgebrochen']:
                                    self.assertIn(context, result.output)

    def test_interactive_failure_continues_with_next_matching_event(self):
        for module in PLATFORMS:
            with self.subTest(platform=module.__name__), tempfile.TemporaryDirectory() as directory:
                invalid = deepcopy(EVENT)
                invalid['date']['uuid'] = 'date-2'
                result, requests, publish = self.run_cli(
                    module, Path(directory) / 'posts.sqlite3', [invalid, EVENT], ['--publish'], 'all\n',
                )
                self.assertEqual(result.exit_code, 0, result.output)
                self.assertIn('Identitätsprüfung 2', result.output)
                self.assertEqual(len(requests), 3)
                publish.assert_called_once()
                self.assertEqual(publish.call_args.args[2].id, 'date-1')
                self.assertFalse(publish.call_args.kwargs['dry_run'])

    def test_parent_and_revision_mismatches_block_remote_mutation(self):
        for module in PLATFORMS:
            for field, check in (("parent", 1), ("revision", 3)):
                with self.subTest(platform=module.__name__, field=field), tempfile.TemporaryDirectory() as directory:
                    event = deepcopy(EVENT)
                    if field == "parent":
                        event["uuid"] = "other-parent"
                    else:
                        event["date"]["slug"] = "other-revision"
                    result, requests, publish = self.run_cli(
                        module, Path(directory) / "posts.sqlite3", [event],
                        DIRECT + ["--publish"], "y\n",
                    )
                    self.assertEqual(result.exit_code, 1, result.output)
                    self.assertIn(f"Identitätsprüfung {check}", result.output)
                    self.assertEqual(len(requests), 2)
                    publish.assert_not_called()

    def test_matching_identity_reaches_platform_in_direct_mode(self):
        for module in PLATFORMS:
            for dry_run in [False, True]:
                with self.subTest(platform=module.__name__, dry_run=dry_run), tempfile.TemporaryDirectory() as directory:
                    result, _, publish = self.run_cli(
                        module, Path(directory) / 'posts.sqlite3', [EVENT],
                        DIRECT + ['--dry-run' if dry_run else '--publish'], '',
                    )
                    self.assertEqual(result.exit_code, 0, result.output)
                    publish.assert_called_once()
                    self.assertEqual(publish.call_args.args[2].id, EVENT['date']['uuid'])
                    self.assertEqual(publish.call_args.args[2].date, EVENT['date']['start_date'])
                    self.assertEqual(publish.call_args.args[2].location, EVENT['date']['venue_name'])
                    self.assertEqual(publish.call_args.kwargs['dry_run'], dry_run)


if __name__ == '__main__':
    unittest.main()
