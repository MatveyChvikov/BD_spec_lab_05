"""Idempotency middleware for LAB 04."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable

from fastapi import Request, Response
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.infrastructure.db import SessionLocal, engine

IDEMPOTENCY_HEADER = "idempotency-key"
REPLAY_HEADER = "X-Idempotency-Replayed"

_IDEMPOTENCY_PATHS: frozenset[str] = frozenset({"/api/payments/retry-demo"})


def _dialect_name() -> str:
    return engine.dialect.name


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """
    Middleware для идемпотентности POST-запросов оплаты.

    - Клиент передаёт `Idempotency-Key` в заголовке.
    - Повтор с тем же ключом, методом, путём и телом возвращает кэшированный ответ.
    - Повтор с тем же ключом и другим телом — 409 Conflict.
    """

    def __init__(self, app, ttl_seconds: int = 24 * 60 * 60):
        super().__init__(app)
        self.ttl_seconds = ttl_seconds

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        if request.method.upper() != "POST" or request.url.path not in _IDEMPOTENCY_PATHS:
            return await call_next(request)

        raw_key = request.headers.get(IDEMPOTENCY_HEADER) or request.headers.get("Idempotency-Key")
        if not raw_key or not raw_key.strip():
            return await call_next(request)

        idempotency_key = raw_key.strip()
        body = await request.body()

        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        new_request = Request(dict(request.scope), receive)

        request_hash = self.build_request_hash(body)
        method = request.method.upper()
        path = request.url.path
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=self.ttl_seconds)

        row = await self._wait_for_completed_or_acquire(
            idempotency_key, method, path, request_hash, expires_at
        )

        if row["_action"] == "timeout":
            return JSONResponse(
                status_code=504,
                content={"detail": "Idempotency processing timed out waiting for in-flight request."},
            )

        if row["_action"] == "conflict":
            return JSONResponse(
                status_code=409,
                content={
                    "detail": "Idempotency-Key reuse with different request body is not allowed.",
                },
            )

        if row["_action"] == "replay":
            return self._build_cached_response(row)

        # owner
        try:
            response = await call_next(new_request)
        except Exception:
            await self._mark_failed(idempotency_key, method, path, request_hash)
            raise

        body_bytes, status_code, media_type = await self._read_response_body(response)
        await self._persist_completed(
            idempotency_key,
            method,
            path,
            request_hash,
            status_code,
            body_bytes,
            media_type,
        )

        headers = {
            k: v
            for k, v in response.headers.items()
            if k.lower() not in ("content-length", "transfer-encoding")
        }
        return Response(
            content=body_bytes,
            status_code=status_code,
            media_type=media_type,
            headers=headers,
        )

    async def _wait_for_completed_or_acquire(
        self,
        idempotency_key: str,
        method: str,
        path: str,
        request_hash: str,
        expires_at: datetime,
    ) -> dict:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + 10.0

        while loop.time() < deadline:
            async with SessionLocal() as session:
                existing = await self._select_row(session, idempotency_key, method, path)
                if existing:
                    if existing["request_hash"] != request_hash:
                        return {"_action": "conflict"}
                    if existing["status"] == "completed" and existing["status_code"] is not None:
                        merged = {"_action": "replay"}
                        merged.update(existing)
                        return merged
                    await asyncio.sleep(0.02)
                    continue

                try:
                    await self._insert_processing(
                        session, idempotency_key, method, path, request_hash, expires_at
                    )
                    await session.commit()
                    return {"_action": "owner"}
                except IntegrityError:
                    await session.rollback()
                    await asyncio.sleep(0.02)
                    continue

        return {"_action": "timeout"}

    async def _select_row(self, session, idempotency_key: str, method: str, path: str):
        result = await session.execute(
            text(
                """
                SELECT id, idempotency_key, request_method, request_path, request_hash,
                       status, status_code, response_body
                FROM idempotency_keys
                WHERE idempotency_key = :ik
                  AND request_method = :m
                  AND request_path = :p
                """
            ),
            {"ik": idempotency_key, "m": method, "p": path},
        )
        row = result.mappings().first()
        return dict(row) if row else None

    async def _insert_processing(
        self,
        session,
        idempotency_key: str,
        method: str,
        path: str,
        request_hash: str,
        expires_at: datetime,
    ) -> None:
        if _dialect_name() == "postgresql":
            await session.execute(
                text(
                    """
                    INSERT INTO idempotency_keys (
                        idempotency_key, request_method, request_path, request_hash,
                        status, expires_at
                    ) VALUES (
                        :ik, :m, :p, :h, 'processing', :ex
                    )
                    """
                ),
                {
                    "ik": idempotency_key,
                    "m": method,
                    "p": path,
                    "h": request_hash,
                    "ex": expires_at,
                },
            )
        else:
            await session.execute(
                text(
                    """
                    INSERT INTO idempotency_keys (
                        id, idempotency_key, request_method, request_path, request_hash,
                        status, expires_at
                    ) VALUES (
                        :id, :ik, :m, :p, :h, 'processing', :ex
                    )
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "ik": idempotency_key,
                    "m": method,
                    "p": path,
                    "h": request_hash,
                    "ex": expires_at,
                },
            )

    async def _persist_completed(
        self,
        idempotency_key: str,
        method: str,
        path: str,
        request_hash: str,
        status_code: int,
        body_bytes: bytes,
        media_type: str | None,
    ) -> None:
        payload = {
            "body_b64": base64.b64encode(body_bytes).decode("ascii"),
            "media_type": media_type or "application/json",
        }
        async with SessionLocal() as session:
            if _dialect_name() == "postgresql":
                await session.execute(
                    text(
                        """
                        UPDATE idempotency_keys
                        SET status = 'completed',
                            status_code = :sc,
                            response_body = CAST(:rb AS jsonb),
                            updated_at = NOW()
                        WHERE idempotency_key = :ik
                          AND request_method = :m
                          AND request_path = :p
                          AND request_hash = :h
                        """
                    ),
                    {
                        "sc": status_code,
                        "rb": json.dumps(payload, ensure_ascii=False),
                        "ik": idempotency_key,
                        "m": method,
                        "p": path,
                        "h": request_hash,
                    },
                )
            else:
                await session.execute(
                    text(
                        """
                        UPDATE idempotency_keys
                        SET status = 'completed',
                            status_code = :sc,
                            response_body = :rb,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE idempotency_key = :ik
                          AND request_method = :m
                          AND request_path = :p
                          AND request_hash = :h
                        """
                    ),
                    {
                        "sc": status_code,
                        "rb": json.dumps(payload, ensure_ascii=False),
                        "ik": idempotency_key,
                        "m": method,
                        "p": path,
                        "h": request_hash,
                    },
                )
            await session.commit()

    async def _mark_failed(self, idempotency_key: str, method: str, path: str, request_hash: str) -> None:
        """Удаляем «processing»-запись, чтобы клиент мог повторить тот же ключ после ошибки."""
        async with SessionLocal() as session:
            await session.execute(
                text(
                    """
                    DELETE FROM idempotency_keys
                    WHERE idempotency_key = :ik
                      AND request_method = :m
                      AND request_path = :p
                      AND request_hash = :h
                    """
                ),
                {"ik": idempotency_key, "m": method, "p": path, "h": request_hash},
            )
            await session.commit()

    def _build_cached_response(self, row: dict) -> Response:
        raw = row.get("response_body")
        if raw is None:
            return JSONResponse(status_code=500, content={"detail": "Missing idempotent response cache."})
        if isinstance(raw, (dict, list)):
            data = raw
        else:
            data = json.loads(str(raw))
        body_bytes = base64.b64decode(data["body_b64"])
        media_type = data.get("media_type") or "application/json"
        headers = {REPLAY_HEADER: "true"}
        return Response(
            content=body_bytes,
            status_code=int(row["status_code"]),
            media_type=media_type,
            headers=headers,
        )

    @staticmethod
    async def _read_response_body(response: Response) -> tuple[bytes, int, str | None]:
        parts: list[bytes] = []
        async for chunk in response.body_iterator:
            parts.append(chunk)
        body_bytes = b"".join(parts)
        return body_bytes, response.status_code, response.media_type

    @staticmethod
    def build_request_hash(raw_body: bytes) -> str:
        return hashlib.sha256(raw_body).hexdigest()

    @staticmethod
    def encode_response_payload(body_obj) -> str:
        return json.dumps(body_obj, ensure_ascii=False)
