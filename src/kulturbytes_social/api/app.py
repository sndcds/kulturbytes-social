"""Versioned HTTP API. Import never opens a database connection."""
from contextlib import asynccontextmanager
import logging
import threading
from uuid import uuid4
from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from kulturbytes_common.errors import DomainError, DatabaseUnavailable
from kulturbytes_social.api.dependencies import authorize, repository
from kulturbytes_social.api.routes import events, publications, attempts, platforms, jobs
from kulturbytes_social.services.platforms import PlatformService

STATUS = {'unauthorized': 401, 'not_found': 404, 'invalid_event': 422,
          'publication_conflict': 409, 'already_published': 409, 'database_unavailable': 503,
          'platform_auth_failed': 502, 'remote_publish_failed': 502, 'remote_result_uncertain': 502,
          'remote_succeeded_local_failed': 503}
logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app):
        yield
        if hasattr(app.state, 'engine'):
            app.state.engine.dispose()

    app = FastAPI(title='Kulturbytes Social API', version='1.0', lifespan=lifespan)
    app.state.database_lock = threading.Lock()
    app.state.platforms = PlatformService()

    @app.middleware('http')
    async def request_id(request: Request, call_next):
        # Generate server IDs: do not reflect user-controlled strings that could contain tokens.
        identifier = str(uuid4())
        request.state.request_id = identifier
        try:
            response = await call_next(request)
        except Exception:
            logger.error("Unexpected request failure request_id=%s", identifier)
            response = JSONResponse(status_code=500, content={"detail": {"code": "operation_failed", "message": "Vorgang fehlgeschlagen."}})
        response.headers['X-Request-ID'] = identifier
        return response

    @app.exception_handler(DomainError)
    async def domain_error(request, exc):
        logger.warning('Request failed code=%s request_id=%s', exc.code, request.state.request_id)
        return JSONResponse(status_code=STATUS.get(exc.code, 500),
                            content={'detail': {'code': exc.code, 'message': str(exc), **exc.context}})

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        # Pydantic errors can contain the entire input, including unexpected token fields.
        return JSONResponse(status_code=422, content={'detail': {'code': 'invalid_request', 'message': 'Ungültige Anfrage.'}})

    @app.exception_handler(Exception)
    async def unexpected(request, exc):
        logger.error('Unexpected request failure request_id=%s', getattr(request.state, 'request_id', 'unknown'))
        return JSONResponse(status_code=500, content={'detail': {'code': 'operation_failed', 'message': 'Vorgang fehlgeschlagen.'}})

    @app.get('/health')
    def liveness():
        return {'status': 'ok'}

    @app.get('/api/v1/health')
    def readiness(repo=Depends(repository)):
        repo.readiness()
        return {'status': 'ok', 'database': 'ok'}

    router = APIRouter(prefix='/api/v1', dependencies=[Depends(authorize)])
    for module in (events, publications, attempts, platforms, jobs):
        router.include_router(module.router)
    app.include_router(router)
    return app


app = create_app()
