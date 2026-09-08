"""One publication workflow for API clients, with durable steps around remote I/O."""
import httpx
import logging
import re
from uuid import UUID
from kulturbytes_common.auth import remote_url
from kulturbytes_common.errors import (InvalidEvent, RemoteRejected,
    RemotePublishError, RemoteResultUncertain, RemoteSucceededLocalFailed, PublicationConflict)
from kulturbytes_common.publications import mutation_recorder, content_fingerprint, validate_target_ref
from kulturbytes_social.db.repositories.publications import PublicationRepository
from kulturbytes_social.services.platforms import PlatformService
from kulturbytes_social.services.events import EventService

logger = logging.getLogger(__name__)


class PublicationService:
    def __init__(self, repository: PublicationRepository, platforms: PlatformService, client: httpx.Client) -> None:
        self.repository, self.platforms, self.client = repository, platforms, client
        self.events = EventService(repository, client)

    def preview(self, *, platform: str, event_uuid: str, date_identifier: str,
                force_repeat: bool = False, city: str | None = None) -> dict:
        event, summary = self.events.detail(event_uuid, date_identifier, platform=platform,
                                           include_published=force_repeat, city=city)
        prepared = self.platforms.prepare(platform, self.client, event)
        return {'text': prepared.text, 'image_url': prepared.image_url, 'event': event,
                'published': summary['published'],
                'content_sha256': content_fingerprint(platform, event, prepared.text)}

    def publish(self, *, platform: str, event_uuid: str, date_identifier: str,
                force_repeat: bool = False, city: str | None = None, expected_content_sha256: str | None = None) -> dict:
        event, _ = self.events.detail(event_uuid, date_identifier, platform=platform,
                                     include_published=force_repeat, city=city)
        config = self.platforms.authenticate(platform)
        prepared = self.platforms.prepare(platform, self.client, event, config=config)
        fingerprint = content_fingerprint(platform, event, prepared.text)
        if expected_content_sha256 and fingerprint != expected_content_sha256:
            raise PublicationConflict('Die Vorschau hat sich geändert. Vor Veröffentlichung erneut prüfen.')
        adapter = self.platforms.registry[platform]
        target = validate_target_ref(platform, adapter.target(config))
        attempt = self.repository.reserve(platform=platform, event=event, target_ref=target,
                                          fingerprint=fingerprint, force_repeat=force_repeat)
        attempt_id = attempt['id']
        mutation_started = False

        def stage(value: str) -> None:
            nonlocal mutation_started
            if not value.startswith(platform + '_'):
                raise InvalidEvent('Ungültige Veröffentlichungsphase.')
            self.repository.transition(attempt_id, 'publishing', ('reserved', 'publishing'), mutation_stage=value)
            mutation_started = True

        try:
            with mutation_recorder(stage):
                remote_id, url = adapter.publish(self.client, config, event, prepared)
        except Exception as exc:
            if not mutation_started or isinstance(exc, RemoteRejected):
                self.repository.transition(attempt_id, 'failed', ('reserved', 'publishing'),
                                           error_class=type(exc).__name__, error_message=RemotePublishError.message)
                raise RemotePublishError(attempt_id=str(attempt_id)) from None
            self.repository.transition(attempt_id, 'publishing', ('publishing',),
                                       error_class=type(exc).__name__, error_message=RemoteResultUncertain.message)
            raise RemoteResultUncertain(attempt_id=str(attempt_id)) from None
        try:
            # Adapters validate remote references using their actual token before returning them.
            self.repository.transition(attempt_id, 'remote_succeeded', ('reserved', 'publishing'),
                                       remote_id=remote_id, remote_url=url)
            publication = self.repository.finalize(attempt_id)
        except Exception:
            raise RemoteSucceededLocalFailed(attempt_id=str(attempt_id), remote_id=remote_id) from None
        logger.info('Publication completed platform=%s attempt_id=%s date_uuid=%s', platform, attempt_id, event['date']['uuid'])
        return {'attempt_id': str(attempt_id), 'publication_id': str(publication['id']), 'state': 'published',
                'remote_id': remote_id, 'remote_url': url}

    def resolve(self, attempt_id: UUID, *, outcome: str, remote_id: str | None = None, remote_url_value: str | None = None) -> dict:
        attempt = self.repository.attempt(attempt_id)
        if outcome in ('failed', 'cancelled'):
            previous = ('reserved',) if outcome == 'cancelled' else ('reserved', 'publishing')
            return self.repository.transition(attempt_id, outcome, previous, error_class='OperatorConfirmed')
        if not attempt['remote_id']:
            pattern = r'[0-9]{1,100}(?:_[0-9]{1,100})?' if attempt['platform'] == 'facebook' else r'[0-9]{1,100}'
            if not remote_id or not re.fullmatch(pattern, remote_id):
                raise PublicationConflict('Numerische Remote-ID für die Wiederherstellung erforderlich.')
        if remote_url_value and remote_url(remote_url_value, '') != remote_url_value:
            raise PublicationConflict('Ungültige Remote-URL.')
        return self.repository.finalize(attempt_id, resolve_id=remote_id, resolve_url=remote_url_value)
