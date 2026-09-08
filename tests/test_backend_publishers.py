"""Real adapters and HTTP sequences with a committed PostgreSQL journal at each POST."""
from copy import deepcopy
import os
from urllib.parse import parse_qs
from unittest.mock import patch
import httpx
from kulturbytes_common.errors import RemotePublishError, RemoteResultUncertain, InvalidEvent
from kulturbytes_common.publications import content_fingerprint
from kulturbytes_social.services.platforms import PlatformService
from kulturbytes_social.services.publications import PublicationService
from postgres_support import PostgreSQLTestCase
from test_publishers import EVENT, SUMMARY, FACEBOOK, MASTODON
from test_instagram import instagram

SECRET = 'social-secret'
ENV = {'META_SYSTEM_USER_ACCESS_TOKEN': '', 'FACEBOOK_PAGE_ID': '123', 'FACEBOOK_PAGE_ACCESS_TOKEN': SECRET,
       'INSTAGRAM_USER_ID': '123', 'INSTAGRAM_ACCESS_TOKEN': SECRET, 'INSTAGRAM_LOGIN_TYPE': 'instagram',
       'MASTODON_BASE_URL': 'https://norden.social', 'MASTODON_ACCESS_TOKEN': SECRET}


class AdapterIntegrationTests(PostgreSQLTestCase):
    def run_publisher(self, platform, *, with_image=False, outcome='success', status='FINISHED', jpeg=True):
        detail = deepcopy(EVENT)
        detail['description'] = 'Fallback description'
        detail['summary'] = 'Ignored detail summary'
        if with_image:
            detail['images'] = {'main': {'url': 'https://api.kulturbytes.de/api/image/image-1', 'alt': 'Alt text'}}
        merged = {**detail, 'summary': 'List summary'}
        stages, bodies, requests = [], [], []
        def handle(request):
            requests.append(request)
            path = request.url.path
            if path == '/api/events':
                return httpx.Response(200, json={'data': {'events': [{**SUMMARY, 'summary': 'List summary'}]}})
            if path.startswith('/api/event/'):
                return httpx.Response(200, json={'data': detail})
            if path == '/api/image/image-1':
                self.assertNotIn('Authorization', request.headers)
                return httpx.Response(200, content=b'\xff\xd8\xffJPEG' if jpeg else b'PNG', headers={'Content-Type': 'image/jpeg'})
            if path == '/api/v2/instance':
                return httpx.Response(200, json={'configuration': {'statuses': {'max_characters': 500}}})
            self.assertEqual(request.headers['Authorization'], 'Bearer ' + SECRET)
            self.assertNotIn('access_token', request.url.params)
            if request.method == 'GET':
                if platform == 'instagram':
                    return httpx.Response(200, json={'status_code': status})
                return httpx.Response(200, json={'id': '777', 'url': 'https://norden.social/media/777'})
            expected = {'/v26.0/123/feed': 'facebook_feed', '/v26.0/123/photos': 'facebook_photo',
                        '/api/v2/media': 'mastodon_media', '/api/v1/statuses': 'mastodon_status',
                        '/v26.0/123/media': 'instagram_container', '/v26.0/123/media_publish': 'instagram_publish'}[path]
            # A separate connection observes the durable stage BEFORE the mocked remote mutation.
            row = self.repo.attempts(active=True)[0]
            self.assertEqual((row['state'], row['mutation_stage']), ('publishing', expected))
            stages.append(expected); bodies.append(request.content)
            formatter = {'facebook': FACEBOOK.build_message, 'instagram': instagram.build_instagram_caption,
                         'mastodon': MASTODON.build_mastodon_message}[platform]
            self.assertEqual(row['content_sha256'], content_fingerprint(platform, merged, formatter(merged)))
            if outcome == 'timeout': raise httpx.ReadTimeout(SECRET)
            if outcome == 'rejected': return httpx.Response(401, json={'error': {'message': SECRET}})
            if outcome == 'invalid': return httpx.Response(200, json={})
            return httpx.Response(200, json={'id': '777', 'url': 'https://norden.social/@user/777'})
        platforms = PlatformService()
        module = {'facebook': FACEBOOK, 'instagram': instagram, 'mastodon': MASTODON}[platform]
        with patch.dict(os.environ, ENV, clear=True), patch('kulturbytes_common.credentials.get_secret', return_value=None), \
             patch.object(platforms.registry[platform], 'authenticate', side_effect=module.load_config), \
             patch.object(instagram.time, 'sleep'), httpx.Client(transport=httpx.MockTransport(handle)) as client:
            service = PublicationService(self.repo, platforms, client)
            expected_error = None
            if platform == 'instagram' and (not with_image or not jpeg): expected_error = InvalidEvent
            elif outcome == 'rejected': expected_error = RemotePublishError
            elif outcome in ('timeout', 'invalid') or status != 'FINISHED': expected_error = RemoteResultUncertain
            if expected_error:
                with self.assertRaises(expected_error) as error:
                    service.publish(platform=platform, event_uuid='event-1', date_identifier='date-1')
                self.assertNotIn(SECRET, str(error.exception))
            else:
                result = service.publish(platform=platform, event_uuid='event-1', date_identifier='date-1')
                self.assertEqual(result['state'], 'published')
        return stages, bodies, requests

    def test_all_six_stages_and_actual_text_are_durable(self):
        for platform, image, expected in [('facebook', False, ['facebook_feed']), ('facebook', True, ['facebook_photo']),
            ('mastodon', False, ['mastodon_status']), ('mastodon', True, ['mastodon_media', 'mastodon_status']),
            ('instagram', True, ['instagram_container', 'instagram_publish'])]:
            with self.subTest(platform=platform, image=image):
                self.setUp()
                stages, bodies, requests = self.run_publisher(platform, with_image=image)
                self.assertEqual(stages, expected)
                self.assertEqual(len(self.repo.publications()), 1)
                text_request = next(r for r in requests if r.method == 'POST' and r.url.path.endswith(('feed', 'photos', 'statuses', '/media')) and not r.url.path.endswith('/api/v2/media'))
                self.assertIn(b'List', text_request.content)

    def test_platform_post_failures_are_not_retried_or_recorded_as_success(self):
        for platform in ('facebook', 'instagram', 'mastodon'):
            for outcome in ('timeout', 'rejected', 'invalid'):
                with self.subTest(platform=platform, outcome=outcome):
                    self.setUp()
                    stages, _, _ = self.run_publisher(platform, with_image=platform == 'instagram', outcome=outcome)
                    self.assertEqual(len(stages), 1)
                    self.assertEqual(self.repo.publications(), [])
                    row = self.repo.attempts()[0]
                    self.assertEqual(row['state'], 'failed' if outcome == 'rejected' else 'publishing')
                    self.assertNotIn(SECRET, str(row))

    def test_instagram_requires_jpeg_and_finished_container(self):
        for image, jpeg in ((False, True), (True, False)):
            self.setUp()
            stages, _, _ = self.run_publisher('instagram', with_image=image, jpeg=jpeg)
            self.assertEqual(stages, []); self.assertEqual(self.repo.attempts(), [])
        for status in ('ERROR', 'EXPIRED', 'unexpected', 'IN_PROGRESS'):
            self.setUp()
            stages, _, requests = self.run_publisher('instagram', with_image=True, status=status)
            self.assertEqual(stages, ['instagram_container'])
            polls = [r for r in requests if r.url.path == '/v26.0/777']
            self.assertEqual(len(polls), 5 if status == 'IN_PROGRESS' else 1)
            self.assertEqual(self.repo.publications(), [])
