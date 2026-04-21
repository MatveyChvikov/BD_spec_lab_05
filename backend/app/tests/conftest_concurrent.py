"""Фикстуры и маркеры только для concurrent-платежных тестов (PostgreSQL).

Вынесено из корневого conftest, чтобы при прогоне только test_domain.py не
подтягивались лишние async-хуки и общая конфигурация оставалась проще.
"""

import os

import pytest

requires_postgres = pytest.mark.skipif(
    "postgresql" not in os.environ.get("DATABASE_URL", ""),
    reason="Гонки и FOR UPDATE проверяются на PostgreSQL",
)
