"""Domain failures; transports and repositories never expose raw secrets."""
class DomainError(Exception):
    code = 'operation_failed'
    message = 'Vorgang fehlgeschlagen.'

    def __init__(self, message: str | None = None, **context: str) -> None:
        super().__init__(message or self.message)
        self.context = context


class DatabaseUnavailable(DomainError):
    code = 'database_unavailable'
    message = 'PostgreSQL ist nicht verfügbar oder das Schema fehlt. Alembic-Migration prüfen.'


class PublicationConflict(DomainError):
    code = 'publication_conflict'
    message = 'Für diesen Termin besteht ein aktiver oder ungeklärter Veröffentlichungsversuch.'


class AlreadyPublished(PublicationConflict):
    code = 'already_published'
    message = 'Dieser Termin wurde bereits veröffentlicht; ausdrückliche Wiederholung erforderlich.'


class NotFound(DomainError):
    code = 'not_found'
    message = 'Eintrag nicht gefunden.'


class InvalidEvent(DomainError):
    code = 'invalid_event'
    message = 'Ungültiger, nicht eindeutiger oder nicht veröffentlichbarer Termin.'


class PlatformAuthenticationError(DomainError):
    code = 'platform_auth_failed'
    message = 'Plattform-Zugang konnte nicht validiert werden. Server-Konfiguration prüfen.'


class RemotePublishError(DomainError):
    code = 'remote_publish_failed'
    message = 'Die Plattform hat die Veröffentlichung abgelehnt.'


class RemoteResultUncertain(DomainError):
    code = 'remote_result_uncertain'
    message = 'Remote-Ergebnis ungeklärt; Versuch bleibt gesperrt. Plattform manuell prüfen.'


class RemoteSucceededLocalFailed(DomainError):
    code = 'remote_succeeded_local_failed'
    message = 'Remote-Veröffentlichung erfolgreich; lokale Finalisierung fehlgeschlagen. Nicht erneut posten.'


class RemoteRejected(Exception):
    """Definitive rejection of a mutation, not an uncertain transport outcome."""
