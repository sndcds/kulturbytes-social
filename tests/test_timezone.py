from datetime import datetime, timedelta
from unittest.mock import patch
from dotenv_support import IsolatedEnvironmentTestCase
from kulturbytes_common.timezone import application_today
from unittest.mock import Mock
import sqlite3
from kulturbytes_common.sources.models import ContentItem
from kulturbytes_common.workflow import run_publisher


class TimezoneTests(IsolatedEnvironmentTestCase):
    def test_summer_and_winter_midnight(self):
        for instant, expected in [('2026-07-01T22:30:00+00:00', '2026-07-02'),
                                  ('2026-01-01T22:30:00+00:00', '2026-01-01'),
                                  ('2026-01-01T23:30:00+00:00', '2026-01-02'),
                                  ('2026-07-02T00:30:00+00:00', '2026-07-02')]:
            today = application_today(datetime.fromisoformat(instant))
            self.assertEqual(today.isoformat(), expected)
            for delta in (-1, 0, 1):
                item = ContentItem(title="Calendar", date=(today + timedelta(days=delta)).isoformat())
                adapter = Mock(name="source")
                adapter.name = "calendar"
                adapter.behavior.skip_past = True
                adapter.list_items.return_value = [item]
                adapter.get_item.return_value = item
                publish = Mock()
                with patch("kulturbytes_common.workflow.application_today", return_value=today):
                    run_publisher(sqlite3.connect(":memory:"), publish, "test", dry_run=True,
                                  limit=0, include_published=False, city=None, adapter=adapter,
                                  target="today" if delta >= 0 else None)
                self.assertEqual(publish.called, delta >= 0)
