from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

from dormbuddy import db
from dormbuddy.config import get_settings


@pytest.fixture
def postgres(monkeypatch):
    url = make_url(get_settings().database_url)
    if url.get_backend_name() != "postgresql":
        pytest.fail("Integration tests require PostgreSQL.")
    schema = "dormbuddy_test_" + uuid4().hex
    admin = create_engine(url)
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    with admin.begin() as connection:
        connection.exec_driver_sql(f"CREATE SCHEMA {schema}")
    monkeypatch.setattr(db, "get_engine", lambda: engine)
    try:
        command.upgrade(Config("alembic.ini"), "head")
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.exec_driver_sql(f"DROP SCHEMA {schema} CASCADE")
        admin.dispose()
