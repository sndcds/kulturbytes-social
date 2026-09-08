"""Lazy PostgreSQL configuration; URLs and driver exceptions must stay private."""
from contextlib import contextmanager
from collections.abc import Iterator
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from kulturbytes_common.environment import get_config
from kulturbytes_common.errors import DatabaseUnavailable


def database_engine(value: str | None = None) -> Engine:
    try:
        url = make_url(value if value is not None else get_config('DATABASE_URL'))
        if url.drivername != 'postgresql+psycopg' or not url.database:
            raise ValueError
        return create_engine(url, hide_parameters=True, pool_pre_ping=True, pool_size=5, max_overflow=5,
                             connect_args={'connect_timeout': 5, 'options': '-c timezone=UTC -c statement_timeout=5000 -c lock_timeout=5000'})
    except Exception:
        raise DatabaseUnavailable() from None


def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)


@contextmanager
def transaction(factory: sessionmaker[Session]) -> Iterator[Session]:
    try:
        with factory.begin() as session:
            yield session
    except SQLAlchemyError:
        raise DatabaseUnavailable() from None
