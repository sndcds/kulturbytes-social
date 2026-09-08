from kulturbytes_common.errors import DomainError
from kulturbytes_social.db.repositories.jobs import JobRepository
from kulturbytes_social.services.publications import PublicationService


class JobService:
    def __init__(self, repository: JobRepository, publications: PublicationService) -> None:
        self.repository, self.publications = repository, publications

    def execute(self, payload: dict) -> dict:
        job = self.repository.create(payload)
        self.repository.update(job['id'], 'running')
        try:
            result = self.publications.publish(**payload)
        except DomainError as exc:
            # Only fixed domain messages, never raw adapter or driver errors.
            return self.repository.update(job['id'], 'failed', result={'code': exc.code, **exc.context},
                error_class=type(exc).__name__, error_message=exc.message)
        except Exception:
            return self.repository.update(job['id'], 'failed', error_class='OperationFailed',
                                          error_message='Vorgang fehlgeschlagen; Journal vor Wiederholung prüfen.')
        return self.repository.update(job['id'], 'succeeded', result=result)
