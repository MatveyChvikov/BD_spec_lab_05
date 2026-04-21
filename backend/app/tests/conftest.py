"""Pytest configuration and fixtures."""

import os

# Локальный прогон без Docker: in-memory SQLite
if "DATABASE_URL" not in os.environ:
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

# In-memory Redis в тестах с SQLite; в CI/Postgres — настоящий Redis (см. env)
if "sqlite" in os.environ.get("DATABASE_URL", ""):
    os.environ["PYTEST_USE_FAKEREDIS"] = "1"
else:
    os.environ.pop("PYTEST_USE_FAKEREDIS", None)

import inspect

import pytest
import pytest_asyncio
import uuid
from pathlib import Path
from sqlalchemy import text


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """
    Все async-тесты на одном session event loop.

    Иначе маркер asyncio по умолчанию использует loop_scope=function, а пул asyncpg
    из module-level engine привязан к циклу session-фикстур — RuntimeError «Future
    attached to a different loop».
    """
    config._domain_only_pytest_session = bool(items) and all(
        "test_domain.py" in item.nodeid for item in items
    )

    for item in items:
        fn = getattr(item, "obj", None)
        if fn is None or not inspect.iscoroutinefunction(fn):
            continue
        item.own_markers[:] = [m for m in item.own_markers if m.name != "asyncio"]
        item.add_marker(pytest.mark.asyncio(loop_scope="session"))


def _strip_sql_line_comments(sql: str) -> str:
    lines = []
    for line in sql.splitlines():
        stripped = line.strip()
        if stripped.startswith("--"):
            continue
        lines.append(line)
    return "\n".join(lines)


def _split_postgres_statements(script: str) -> list[str]:
    """Делит SQL по ';' вне тела $$ ... $$ (для миграций с plpgsql)."""
    s = _strip_sql_line_comments(script)
    parts: list[str] = []
    buf: list[str] = []
    in_dollar = False
    i = 0
    while i < len(s):
        if s.startswith("$$", i):
            in_dollar = not in_dollar
            buf.append("$$")
            i += 2
            continue
        ch = s[i]
        if ch == ";" and not in_dollar:
            stmt = "".join(buf).strip()
            if stmt:
                parts.append(stmt)
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        parts.append(tail)
    return parts


_SQLITE_DDL = [
    "PRAGMA foreign_keys=ON",
    """
            CREATE TABLE IF NOT EXISTS order_statuses (
                status TEXT PRIMARY KEY,
                description TEXT NOT NULL
            )
            """,
    """
            INSERT OR IGNORE INTO order_statuses (status, description) VALUES
                ('created', 'created'),
                ('paid', 'paid'),
                ('cancelled', 'cancelled'),
                ('shipped', 'shipped'),
                ('completed', 'completed')
            """,
    """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL
            )
            """,
    """
            CREATE TABLE IF NOT EXISTS orders (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                status TEXT NOT NULL REFERENCES order_statuses(status),
                total_amount REAL NOT NULL,
                created_at TIMESTAMP NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
            """,
    """
            CREATE TABLE IF NOT EXISTS order_items (
                id TEXT PRIMARY KEY,
                order_id TEXT NOT NULL,
                product_name TEXT NOT NULL,
                price REAL NOT NULL,
                quantity INTEGER NOT NULL,
                subtotal REAL NOT NULL,
                FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE
            )
            """,
    """
            CREATE TABLE IF NOT EXISTS order_status_history (
                id TEXT PRIMARY KEY,
                order_id TEXT NOT NULL,
                status TEXT NOT NULL REFERENCES order_statuses(status),
                changed_at TIMESTAMP NOT NULL,
                FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE
            )
            """,
    """
            CREATE TABLE IF NOT EXISTS idempotency_keys (
                id TEXT PRIMARY KEY,
                idempotency_key TEXT NOT NULL,
                request_method TEXT NOT NULL,
                request_path TEXT NOT NULL,
                request_hash TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'processing',
                status_code INTEGER,
                response_body TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                UNIQUE (idempotency_key, request_method, request_path)
            )
            """,
    "CREATE INDEX IF NOT EXISTS idx_idempotency_keys_expires_at ON idempotency_keys (expires_at)",
]


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _ensure_schema(request: pytest.FixtureRequest):
    """
    Схема для SQLite и догон миграции idempotency_keys для PostgreSQL.
    Выполняется на том же event loop, что и async-тесты (см. pytest.ini).

    Для прогона только test_domain.py не поднимаем SQLite/aiosqlite — домен БД не трогает.
    """
    if getattr(request.config, "_domain_only_pytest_session", False):
        return

    from app.infrastructure import db

    url = os.environ.get("DATABASE_URL", "")
    if "sqlite" in url:
        async with db.engine.begin() as conn:
            for stmt in _SQLITE_DDL:
                await conn.execute(text(stmt))
        return

    if "postgresql" not in url:
        return

    async with db.engine.begin() as conn:
        reg = await conn.scalar(text("SELECT to_regclass('public.idempotency_keys')"))
        if reg:
            return
        mig = Path(__file__).resolve().parents[2] / "migrations" / "002_idempotency_keys.sql"
        if not mig.is_file():
            pytest.fail(f"Не найден файл миграции: {mig}")
        raw = mig.read_text(encoding="utf-8")
        for stmt in _split_postgres_statements(raw):
            await conn.execute(text(stmt))


@pytest.fixture
def sample_user_id():
    """Create a sample user ID."""
    return uuid.uuid4()


from app.tests.db_seed import seed_order_in_created_status


@pytest_asyncio.fixture
async def created_order_id():
    """Заказ в статусе created для платёжных сценариев."""
    return await seed_order_in_created_status()


@pytest_asyncio.fixture(autouse=True)
async def _reset_redis_client_between_tests(request: pytest.FixtureRequest):
    """
    Новый in-memory Redis на каждый тест (fakeredis привязан к event loop).

    Сбрасываем singleton, чтобы не было RuntimeError «different event loop».

    Для реального Redis очищаем ключи rate limit перед тестом: иначе все POST без
    X-Forwarded-For попадают в subject «unknown», счётчик переживает тесты и даёт 429.
    """
    if getattr(request.config, "_domain_only_pytest_session", False):
        yield
        return

    import app.infrastructure.redis_client as redis_client_mod

    redis_client_mod._client = None
    if os.environ.get("PYTEST_USE_FAKEREDIS") != "1":
        try:
            client = redis_client_mod.get_redis()
            async for key in client.scan_iter(match="rate_limit:pay:*"):
                await client.delete(key)
        except Exception:
            pass
    yield
    redis_client_mod._client = None
