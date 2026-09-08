from alembic import context
from kulturbytes_social.db.models import Base
from kulturbytes_social.db.session import database_engine


def migrate(connection) -> None:
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations() -> None:
    # Integration tests supply their guarded, isolated connection explicitly.
    connection = context.config.attributes.get('connection')
    if connection is not None:
        migrate(connection)
        return
    engine = database_engine()
    try:
        with engine.connect() as connection:
            migrate(connection)
    except Exception:
        raise RuntimeError('PostgreSQL-Migration fehlgeschlagen; Verbindung und Schema prüfen.') from None
    finally:
        engine.dispose()


run_migrations()
