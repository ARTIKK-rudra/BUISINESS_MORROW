from collections.abc import AsyncIterator
from itertools import count
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import models  # noqa: F401 - registers all models on shared metadata.
from app.db.base import Base
from app.db.session import get_session
from app.main import app

_test_client_sequence = count(1)


@pytest.fixture
async def client(tmp_path: Path) -> AsyncIterator[AsyncClient]:
    test_engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'test.db'}", connect_args={"timeout": 10}
    )

    @event.listens_for(test_engine.sync_engine, "connect")
    def enable_foreign_keys(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with test_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async def override_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    sequence = next(_test_client_sequence)
    address = f"127.0.{sequence // 250}.{sequence % 250 + 1}"
    transport = ASGITransport(app=app, client=(address, 12345))
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        test_client.session_factory = session_factory
        yield test_client
    app.dependency_overrides.clear()
    await test_engine.dispose()
