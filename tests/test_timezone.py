from datetime import datetime, timedelta
from unittest.mock import patch
from dotenv_support import IsolatedEnvironmentTestCase
from kulturbytes_common.timezone import application_today
from kulturbytes_common.sources.kulturbytes_api import should_publish


class TimezoneTests(IsolatedEnvironmentTestCase):
    def test_summer_and_winter_midnight(self):
        for instant, expected in [('2026-07-01T22:30:00+00:00', '2026-07-02'),
                                  ('2026-01-01T22:30:00+00:00', '2026-01-01'),
                                  ('2026-01-01T23:30:00+00:00', '2026-01-02'),
                                  ('2026-07-02T00:30:00+00:00', '2026-07-02')]:
            today = application_today(datetime.fromisoformat(instant))
            self.assertEqual(today.isoformat(), expected)
            with patch('kulturbytes_common.sources.kulturbytes_api.application_today', return_value=today):
                for delta in (-1, 0, 1):
                    self.assertEqual(should_publish({'release_status': 'released',
                        'start_date': (today + timedelta(days=delta)).isoformat()}), delta >= 0)
