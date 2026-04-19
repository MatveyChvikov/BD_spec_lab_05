"""Cache key builders for LAB 05."""

# TTL по умолчанию для каталога и карточки заказа (секунды).
DEFAULT_CACHE_TTL_SECONDS = 300


def catalog_key() -> str:
    """Ключ кэша каталога товаров."""
    return "catalog:v1"


def order_card_key(order_id: str) -> str:
    """Ключ кэша карточки заказа."""
    return f"order_card:v1:{order_id}"


def payment_rate_limit_key(subject: str) -> str:
    """
    Ключ rate limiting для оплаты.

    subject может быть:
    - user_id
    - ip
    - комбинация user_id + endpoint
    """
    return f"rate_limit:pay:{subject}"
