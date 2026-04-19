"""
LAB 04: Сравнение FOR UPDATE (ЛР2) и Idempotency-Key (ЛР4).

Связь с ЛР2:
- Во 2-й лабе тесты `test_concurrent_payment_*` показывают гонку при двух *параллельных*
  вызовах сервиса оплаты и её снятие через REPEATABLE READ + FOR UPDATE.
- Здесь сравниваются те же идеи на уровне HTTP: повтор *одного и того же* запроса
  vs защита на уровне БД при повторе *без* идемпотентности.
"""

import os
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.middleware.idempotency_middleware import REPLAY_HEADER
from app.tests.db_seed import seed_order_in_created_status


def _print_comparison_table() -> None:
    """Наглядное сравнение для консоли (-s) и для отчёта ЛР4 / п.5 README."""
    print(
        """
╔══════════════════════════════════╦════════════════════════════════════════════╗
║ ЛР2: FOR UPDATE + изоляция в БД  ║ ЛР4: Idempotency-Key + middleware          ║
╠══════════════════════════════════╬════════════════════════════════════════════╣
║ Уровень: транзакция / строка     ║ Уровень: HTTP-контракт (заголовок + тело)  ║
║ Угроза: параллельные сессии      ║ Угроза: повтор того же запроса (retry)     ║
║ Повтор другого HTTP без ключа    ║ Повтор с тем же ключом и телом             ║
║   → вторая транзакция «отказ»   ║   → кэш ответа, хендлер оплаты не зовётся   ║
║   (уже оплачен), см. for_update  ║   (заголовок X-Idempotency-Replayed: true)  ║
╚══════════════════════════════════╩════════════════════════════════════════════╝
"""
    )


@pytest.mark.asyncio
async def test_compare_for_update_and_idempotency_behaviour():
    """
    Показывает различия постановки README п.5:

    A) mode=for_update (как безопасная оплата ЛР2): два последовательных POST без
       Idempotency-Key — вторая попытка не оплачивает снова (success=false), в
       order_status_history одна запись paid.

    B) mode=unsafe + Idempotency-Key: два идентичных POST — вторая из кэша,
       снова одна запись paid (без повторного списания в БД).
    """
    _print_comparison_table()

    if "postgresql" in os.environ.get("DATABASE_URL", ""):
        order_for = await seed_order_in_created_status()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            p1 = await client.post(
                "/api/payments/retry-demo",
                json={"order_id": str(order_for), "mode": "for_update"},
            )
            assert p1.status_code == 200
            assert p1.json().get("success") is True

            p2 = await client.post(
                "/api/payments/retry-demo",
                json={"order_id": str(order_for), "mode": "for_update"},
            )
            assert p2.status_code == 200
            assert p2.json().get("success") is False

            hist = await client.get(f"/api/payments/history/{order_for}")
            paid = [x for x in hist.json()["payments"] if x.get("status") == "paid"]
            assert len(paid) == 1, (
                "ЛР2 (for_update): повтор запроса не должен добавить вторую paid в историю"
            )

        print(
            "[ЛР2 / FOR UPDATE] Два POST retry-demo (for_update), без Idempotency-Key: "
            "первая оплата OK, вторая success=false, paid в истории ровно одна."
        )
    else:
        print(
            "[ЛР2 / FOR UPDATE] Сценарий на SQLite пропущен (нет FOR UPDATE как в PostgreSQL). "
            "Полный сравнительный прогон: PostgreSQL, см. docker compose run …"
        )

    order_idem = await seed_order_in_created_status()
    key = f"compare-{uuid.uuid4()}"
    headers = {"Idempotency-Key": key}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        a = await client.post(
            "/api/payments/retry-demo",
            json={"order_id": str(order_idem), "mode": "unsafe"},
            headers=headers,
        )
        b = await client.post(
            "/api/payments/retry-demo",
            json={"order_id": str(order_idem), "mode": "unsafe"},
            headers=headers,
        )
        assert a.status_code == 200 and a.json().get("success") is True
        assert b.status_code == 200 and b.json() == a.json()
        assert (b.headers.get("x-idempotency-replayed") or b.headers.get(REPLAY_HEADER)) == "true"
        hist = await client.get(f"/api/payments/history/{order_idem}")
        paid = [x for x in hist.json()["payments"] if x.get("status") == "paid"]
        assert len(paid) == 1, (
            "ЛР4 (idempotency): при unsafe повтор не должен добавить вторую paid"
        )

    print(
        "[ЛР4 / Idempotency-Key] Два POST retry-demo (unsafe) с одним ключом: "
        "вторая — кэш (replay), paid в истории ровно одна."
    )
    print(
        "\nИтог для отчёта: FOR UPDATE закрывает конкуренцию в БД (см. параллельные тесты ЛР2); "
        "ключ идемпотентности — повтор одного HTTP-запроса без повторной бизнес-операции."
    )
