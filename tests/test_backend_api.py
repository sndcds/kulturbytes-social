"""HTTP API + services + real PostgreSQL; every upstream request is simulated."""
from copy import deepcopy
import importlib
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import UUID, uuid4
import httpx
from fastapi.testclient import TestClient
from sqlalchemy import event as sql_event
from kulturbytes_common.errors import DatabaseUnavailable, RemoteRejected
from kulturbytes_common.publications import begin_remote_mutation, content_fingerprint
from kulturbytes_social.api.app import create_app
from kulturbytes_social.api.dependencies import http_client
from kulturbytes_social.db.models import Publication
from kulturbytes_social.services.platforms import PlatformService, Prepared
from postgres_support import PostgreSQLTestCase
from test_publishers import EVENT, SUMMARY, FACEBOOK, MASTODON
from test_instagram import instagram

BODY = {'platform': 'facebook', 'event_uuid': 'event-1', 'date_identifier': 'date-1'}
SECRET = 'private-service-token'


class FakePublisher:
    def __init__(self, platform, repository):
        self.platform, self.repo = platform, repository
        self.authenticate = Mock(return_value=SimpleNamespace(target='123' if platform != 'mastodon' else 'https://norden.social'))
        self.behavior = None
        self.count = 0

    def target(self, config):
        return config.target

    def prepare(self, client, event, *, config=None):
        if self.platform == 'instagram':
            return Prepared(instagram.build_instagram_caption(event), instagram.validate_image(client, event))
        if self.platform == 'mastodon':
            limit = MASTODON.get_status_limit(client, 'https://norden.social')
            return Prepared(MASTODON.build_mastodon_message(event, max_length=limit), None)
        return Prepared(FACEBOOK.build_message(event), None)

    def publish(self, client, config, event, prepared):
        self.count += 1
        stage = {'facebook': 'facebook_feed', 'instagram': 'instagram_publish', 'mastodon': 'mastodon_status'}[self.platform]
        begin_remote_mutation(stage)
        row = self.repo.attempts(platform=self.platform, active=True)[0]
        assert row['state'] == 'publishing' and row['mutation_stage'] == stage
        assert row['content_sha256'] == content_fingerprint(self.platform, event, prepared.text)
        if self.behavior:
            return self.behavior()
        return '456', None


class BackendAPITests(PostgreSQLTestCase):
    def setUp(self):
        super().setUp()
        self.summaries = [dict(SUMMARY, summary='**Listen-Text**')]
        self.detail = deepcopy(EVENT)
        self.detail.update(summary='UNUSED DETAIL SUMMARY', description='Beschreibung aus Details.')
        self.detail['images'] = {'main': {'url': 'https://api.kulturbytes.de/api/image/image-1'}}
        self.requests = []
        def upstream(request):
            self.requests.append(request)
            if request.method != 'GET':
                raise AssertionError('unexpected upstream mutation')
            if request.url.path == '/api/events':
                return httpx.Response(200, json={'data': {'events': self.summaries}})
            if request.url.path.startswith('/api/event/'):
                return httpx.Response(200, json={'data': self.detail})
            if request.url.path == '/api/v2/instance':
                return httpx.Response(200, json={'configuration': {'statuses': {'max_characters': 500}}})
            if request.url.path == '/api/image/image-1':
                return httpx.Response(200, content=b'\xff\xd8\xffJPEG')
            raise AssertionError(str(request.url))
        self.upstream = httpx.Client(transport=httpx.MockTransport(upstream))
        self.addCleanup(self.upstream.close)
        self.app = create_app()
        self.app.state.repository = self.repo
        self.adapters = {p: FakePublisher(p, self.repo) for p in ('facebook', 'instagram', 'mastodon')}
        self.app.state.platforms = PlatformService(self.adapters)
        self.app.dependency_overrides[http_client] = lambda: self.upstream
        config = patch('kulturbytes_social.api.dependencies.get_config', side_effect=lambda key, *args: SECRET if key == 'KULTURBYTES_SOCIAL_API_TOKEN' else None)
        config.start(); self.addCleanup(config.stop)
        self.api = TestClient(self.app, headers={'Authorization': f'Bearer {SECRET}'})
        self.addCleanup(self.api.close)

    def publish(self, **changes):
        return self.api.post('/api/v1/publications', json={**BODY, **changes})

    def test_health_and_ready_without_credentials(self):
        for path in ('/health', '/api/v1/health'):
            response = self.api.get(path, headers={'Authorization': ''})
            self.assertEqual(response.status_code, 200)
            UUID(response.headers['X-Request-ID'])
        self.assertEqual(self.requests, [])

    def test_import_has_no_database_connection(self):
        with patch('sqlalchemy.create_engine', side_effect=AssertionError('import connection')):
            importlib.reload(importlib.import_module('kulturbytes_social.api.app'))

    def test_database_unavailable_and_missing_schema_fail_closed(self):
        with patch.object(self.repo, 'readiness', side_effect=DatabaseUnavailable()):
            response = self.api.get('/api/v1/health')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['detail']['code'], 'database_unavailable')
        with patch.object(self.repo, 'known_dates', side_effect=DatabaseUnavailable()):
            self.assertEqual(self.publish().status_code, 503)
        self.assertEqual(self.adapters['facebook'].count, 0)

    def test_unexpected_exception_and_validation_do_not_echo_secrets(self):
        with patch.object(self.repo, 'readiness', side_effect=RuntimeError('DSN-PASSWORD ' + SECRET)):
            response = self.api.get('/api/v1/health')
        self.assertEqual(response.status_code, 500)
        self.assertNotIn('DSN-PASSWORD', response.text); self.assertNotIn(SECRET, response.text)
        for body in ({**BODY, 'access_token': SECRET}, {**BODY, 'force_repeat': 'true'}, {**BODY, 'platform': SECRET}):
            response = self.api.post('/api/v1/publications', json=body)
            self.assertEqual(response.status_code, 422); self.assertNotIn(SECRET, response.text)
        self.assertEqual(self.repo.attempts(), [])

    def test_authentication_covers_all_business_routes(self):
        paths = [('GET', '/events?platform=facebook'), ('POST', '/publications'), ('POST', '/publications/preview'),
                 ('GET', '/publication-attempts'), ('POST', f'/publication-attempts/{uuid4()}/resolve'),
                 ('POST', '/platforms/facebook/check-auth'), ('GET', '/jobs'), ('POST', '/jobs')]
        for method, path in paths:
            with self.subTest(path=path):
                response = self.api.request(method, '/api/v1' + path, headers={'Authorization': 'Bearer wrong'}, json=BODY)
                self.assertEqual(response.status_code, 401)
        self.assertEqual(self.requests, []); self.assertEqual(self.repo.attempts(), [])

    def test_check_auth_has_no_persistence_or_mutations(self):
        for platform in self.adapters:
            response = self.api.post(f'/api/v1/platforms/{platform}/check-auth')
            self.assertEqual(response.status_code, 200)
            self.adapters[platform].authenticate.assert_called_once()
        self.assertEqual(self.repo.attempts(), []); self.assertEqual(self.repo.publications(), [])
        self.assertEqual(self.requests, [])
        self.adapters['facebook'].authenticate.side_effect = RuntimeError(SECRET)
        response = self.api.post('/api/v1/platforms/facebook/check-auth')
        self.assertEqual(response.status_code, 502); self.assertNotIn(SECRET, response.text)

    def test_event_filters_sort_limits_and_direct_resolution(self):
        self.summaries = [dict(SUMMARY, date_uuid='late', start_date='2099-02-01'),
            dict(SUMMARY, date_uuid='past', start_date='2000-01-01'), dict(SUMMARY, release_status='draft'),
            dict(SUMMARY, date_uuid='elsewhere', venue_city='Hamburg'), dict(SUMMARY, date_uuid='malformed', start_date='not-a-date'), SUMMARY]
        response = self.api.get('/api/v1/events', params={'platform': 'facebook', 'city': 'fLeNsBuRg', 'limit': 1})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([e['date_uuid'] for e in response.json()], ['date-1'])
        self.summaries = [dict(SUMMARY, uuid='other', date_uuid='other'), SUMMARY]
        for identifier in ('date-1', SUMMARY['date_slug']):
            response = self.api.get(f'/api/v1/events/event-1/dates/{identifier}', params={'platform': 'facebook', 'limit': 1})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['event']['date']['uuid'], 'date-1')
        self.assertEqual(self.api.get('/api/v1/events/absent/dates/absent', params={'platform': 'facebook'}).status_code, 404)

    def test_preview_all_platforms_uses_list_summary_without_auth_or_state(self):
        for platform in self.adapters:
            for summary in ('**Listen-Text**', ' ', ''):
                self.summaries[0]['summary'] = summary
                response = self.api.post('/api/v1/publications/preview', json={**BODY, 'platform': platform})
                self.assertEqual(response.status_code, 200, response.text)
                text = response.json()['text']
                self.assertIn('Listen-Text' if summary.strip() else 'Beschreibung aus Details.', text)
                self.assertNotIn('UNUSED DETAIL SUMMARY', text)
                if platform != 'facebook':
                    self.assertNotIn('**', text)
                self.assertIn('https://kulturbytes.de/de/veranstaltung/event-1/209901011830', text)
                self.assertIn('#Kulturbytes', text); self.assertIn('#Flensburg', text)
                self.adapters[platform].authenticate.assert_not_called()
        self.assertEqual(self.detail['summary'], 'UNUSED DETAIL SUMMARY')
        self.assertEqual(self.repo.attempts(), []); self.assertEqual(self.repo.publications(), [])

    def test_inconsistent_detail_identity_and_ambiguous_list_rejected(self):
        for field in ('uuid', 'slug'):
            original = self.detail['date'][field]
            self.detail['date'][field] = 'mismatch'
            self.assertEqual(self.publish().status_code, 422)
            self.detail['date'][field] = original
        self.detail['uuid'] = 'mismatch'
        self.assertEqual(self.publish().status_code, 422)
        self.summaries *= 2
        self.assertEqual(self.publish().status_code, 422)
        self.assertEqual(self.repo.attempts(), [])

    def test_publication_history_list_detail_and_repeat(self):
        for platform in self.adapters:
            response = self.publish(platform=platform)
            self.assertEqual(response.status_code, 201, response.text)
            result = response.json()
            publication = self.api.get('/api/v1/publications/' + result['publication_id'])
            self.assertEqual(publication.status_code, 200)
            self.assertEqual(publication.json()['remote_id'], '456')
            self.assertEqual(self.publish(platform=platform).status_code, 409)
            self.assertEqual(self.publish(platform=platform, force_repeat=True).status_code, 201)
        self.assertEqual(len(self.api.get('/api/v1/publications').json()), 6)
        self.assertEqual(len(self.api.get('/api/v1/publications', params={'platform': 'instagram', 'limit': 1}).json()), 1)

    def test_preview_hash_blocks_changed_text(self):
        preview = self.api.post('/api/v1/publications/preview', json=BODY).json()
        self.summaries[0]['summary'] = 'Changed after confirmation'
        self.assertEqual(self.publish(expected_content_sha256=preview['content_sha256']).status_code, 409)
        self.assertEqual(self.repo.attempts(), [])
        self.adapters['facebook'].authenticate.assert_called_once()

    def test_definitive_rejection_is_failed_and_transport_is_blocked(self):
        def rejected(): raise RemoteRejected(SECRET)
        self.adapters['facebook'].behavior = rejected
        response = self.publish()
        self.assertEqual(response.status_code, 502); self.assertNotIn(SECRET, response.text)
        self.assertEqual(self.repo.attempts()[0]['state'], 'failed')
        def uncertain(): raise httpx.ReadTimeout(SECRET)
        self.adapters['facebook'].behavior = uncertain
        response = self.publish()
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()['detail']['code'], 'remote_result_uncertain')
        row = self.repo.attempts()[0]
        self.assertEqual((row['state'], row['mutation_stage']), ('publishing', 'facebook_feed'))
        self.assertEqual(self.publish(force_repeat=True).status_code, 409)
        self.assertEqual(self.adapters['facebook'].count, 2)
        self.assertEqual(self.repo.publications(), [])
        self.assertNotIn(SECRET, self.api.get('/api/v1/publication-attempts').text)

    def test_partial_remote_success_survives_database_failure_and_recovery(self):
        def fail(mapper, connection, target):
            raise RuntimeError('sensitive driver failure')
        sql_event.listen(Publication, 'after_insert', fail)
        try:
            response = self.publish()
        finally:
            sql_event.remove(Publication, 'after_insert', fail)
        self.assertEqual(response.status_code, 503)
        row = self.repo.attempts()[0]
        self.assertEqual((row['state'], row['remote_id']), ('remote_succeeded', '456'))
        self.assertEqual(self.publish(force_repeat=True).status_code, 409)
        self.assertEqual(self.repo.publications(), [])
        self.requests.clear()
        path = f"/api/v1/publication-attempts/{row['id']}/resolve"
        self.assertEqual(self.api.post(path, json={'outcome': 'published'}).status_code, 422)
        response = self.api.post(path, json={'outcome': 'published', 'confirmed': True})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.requests, [])
        self.assertEqual(self.adapters['facebook'].count, 1)
        self.assertEqual(self.repo.attempt(row['id'])['state'], 'published')

    def test_remote_id_commit_failure_keeps_prior_blocker(self):
        transition = self.repo.transition
        def fail(attempt_id, state, *args, **kwargs):
            if state == 'remote_succeeded': raise DatabaseUnavailable()
            return transition(attempt_id, state, *args, **kwargs)
        with patch.object(self.repo, 'transition', side_effect=fail):
            self.assertEqual(self.publish().status_code, 503)
        self.assertEqual(self.repo.attempts()[0]['state'], 'publishing')
        self.assertEqual(self.publish(force_repeat=True).status_code, 409)
        self.assertEqual(self.adapters['facebook'].count, 1)

    def test_attempt_listing_filters_detail_and_manual_failure(self):
        row = self.repo.reserve(platform='facebook', event=EVENT, target_ref='123', fingerprint='a'*64, force_repeat=False)
        response = self.api.get('/api/v1/publication-attempts', params={'platform': 'facebook', 'active': True, 'date_uuid': 'date-1', 'limit': 1})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]['id'], str(row['id']))
        self.assertEqual(self.api.get('/api/v1/publication-attempts/' + str(row['id'])).status_code, 200)
        self.assertEqual(self.api.post(f"/api/v1/publication-attempts/{row['id']}/resolve", json={'outcome': 'failed', 'confirmed': True}).status_code, 200)
        self.assertEqual(self.repo.attempts(active=True), [])
        self.assertEqual(self.requests, [])

    def test_jobs_success_failure_and_cancel_conflict(self):
        response = self.api.post('/api/v1/jobs', json=BODY)
        self.assertEqual(response.status_code, 201, response.text)
        job = response.json()
        self.assertEqual(job['state'], 'succeeded')
        self.assertEqual(self.api.get('/api/v1/jobs/' + job['id']).status_code, 200)
        self.assertEqual(self.api.post('/api/v1/jobs/' + job['id'] + '/cancel').status_code, 409)
        failed = self.api.post('/api/v1/jobs', json=BODY).json()
        self.assertEqual(failed['state'], 'failed')
        self.assertEqual(len(self.api.get('/api/v1/jobs').json()), 2)


    def test_two_concurrent_api_requests_send_one_remote_post(self):
        from concurrent.futures import ThreadPoolExecutor
        import threading
        barrier = threading.Barrier(2)
        def auth():
            barrier.wait(timeout=5)
            return SimpleNamespace(target='123')
        self.adapters['facebook'].authenticate.side_effect = auth
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(self.publish) for _ in range(2)]
            responses = [future.result(timeout=10) for future in futures]
        self.assertCountEqual([r.status_code for r in responses], [201, 409])
        self.assertEqual(self.adapters['facebook'].count, 1)
        self.assertEqual(len(self.repo.publications()), 1)

    def test_real_missing_table_is_unready(self):
        from sqlalchemy import text
        with self.engine.begin() as connection:
            connection.execute(text('ALTER TABLE jobs RENAME TO unavailable_jobs'))
        try:
            response = self.api.get('/api/v1/health')
            self.assertEqual(response.status_code, 503, response.text)
            self.assertNotIn('UndefinedTable', response.text)
        finally:
            with self.engine.begin() as connection:
                connection.execute(text('ALTER TABLE unavailable_jobs RENAME TO jobs'))

    def test_real_unreachable_database_and_openapi_security(self):
        from sqlalchemy.engine import make_url
        from kulturbytes_social.db.session import database_engine
        from postgres_support import TEST_URL
        unavailable = database_engine(make_url(TEST_URL).update_query_dict({'host': '/tmp/nonexistent-pg-' + str(uuid4())}).render_as_string(hide_password=False))
        self.addCleanup(unavailable.dispose)
        app = create_app()
        with patch('kulturbytes_social.api.dependencies.database_engine', return_value=unavailable), TestClient(app) as api:
            response = api.get('/api/v1/health')
            self.assertEqual(response.status_code, 503, response.text)
            self.assertNotIn('psycopg', response.text)
            self.assertEqual(api.get('/health').status_code, 200)
        schema = self.api.get('/openapi.json').json()
        self.assertIn('HTTPBearer', schema['components']['securitySchemes'])
        self.assertEqual(schema['paths']['/api/v1/publications']['post']['security'], [{'HTTPBearer': []}])
