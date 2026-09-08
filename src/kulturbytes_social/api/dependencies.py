import secrets
from collections.abc import Iterator
import httpx
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from kulturbytes_common.environment import get_config
from kulturbytes_common.errors import DomainError
from kulturbytes_social.db.session import database_engine, session_factory
from kulturbytes_social.db.repositories.publications import PublicationRepository
from kulturbytes_social.db.repositories.jobs import JobRepository
from kulturbytes_social.services.platforms import PlatformService
from kulturbytes_social.services.publications import PublicationService
from kulturbytes_social.services.jobs import JobService


class Unauthorized(DomainError):
    code = 'unauthorized'
    message = 'API-Zugang verweigert.'


bearer = HTTPBearer(auto_error=False, description='Shared service token from KULTURBYTES_SOCIAL_API_TOKEN.')


def authorize(credential: HTTPAuthorizationCredentials | None = Depends(bearer)) -> None:
    expected = get_config('KULTURBYTES_SOCIAL_API_TOKEN')
    supplied = credential.credentials if credential else ''
    if not expected or not secrets.compare_digest(supplied.encode(), expected.encode()):
        raise Unauthorized()


def repository(request: Request) -> PublicationRepository:
    if not hasattr(request.app.state, 'repository'):
        with request.app.state.database_lock:
            if not hasattr(request.app.state, 'repository'):
                engine = database_engine()
                request.app.state.engine = engine
                request.app.state.repository = PublicationRepository(session_factory(engine))
    return request.app.state.repository


def platform_service(request: Request) -> PlatformService:
    return request.app.state.platforms


def http_client() -> Iterator[httpx.Client]:
    with httpx.Client(timeout=httpx.Timeout(connect=10, read=60, write=60, pool=10),
                      follow_redirects=False, headers={'User-Agent': 'Kulturbytes-Social-Backend/1.0'}) as client:
        yield client


def publications(repo=Depends(repository), platforms=Depends(platform_service), client=Depends(http_client)) -> PublicationService:
    return PublicationService(repo, platforms, client)


def jobs(service=Depends(publications), repo=Depends(repository)) -> JobService:
    return JobService(JobRepository(repo.factory), service)
