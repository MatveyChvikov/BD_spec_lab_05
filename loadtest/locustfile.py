"""
Locust для LAB 05: сравнение RPS с кэшем и без.

Запуск:
  cd loadtest && pip install -r requirements.txt
  locust -f locustfile.py --host=http://localhost:8082

Переменные окружения:
  LAB05_ORDER_ID — UUID заказа для GET card (если не задан, создаётся один раз через API).
"""

import os
import uuid

from locust import HttpUser, between, task


class CacheUser(HttpUser):
    wait_time = between(0.05, 0.2)
    order_id = None

    def on_start(self):
        preset = os.environ.get("LAB05_ORDER_ID")
        if preset:
            self.order_id = preset
            return
        email = f"locust_{uuid.uuid4().hex}@example.com"
        r = self.client.post("/api/users", json={"email": email, "name": "Locust"})
        if r.status_code != 201:
            return
        uid = r.json()["id"]
        ro = self.client.post("/api/orders", json={"user_id": uid})
        if ro.status_code != 201:
            return
        self.order_id = ro.json()["id"]

    @task(3)
    def get_catalog_cached(self):
        self.client.get("/api/cache-demo/catalog?use_cache=true", name="/catalog [cache on]")

    @task(3)
    def get_catalog_uncached(self):
        self.client.get("/api/cache-demo/catalog?use_cache=false", name="/catalog [cache off]")

    @task(2)
    def get_order_card_cached(self):
        if not self.order_id:
            return
        self.client.get(
            f"/api/cache-demo/orders/{self.order_id}/card?use_cache=true",
            name="/order card [cache on]",
        )

    @task(2)
    def get_order_card_uncached(self):
        if not self.order_id:
            return
        self.client.get(
            f"/api/cache-demo/orders/{self.order_id}/card?use_cache=false",
            name="/order card [cache off]",
        )
