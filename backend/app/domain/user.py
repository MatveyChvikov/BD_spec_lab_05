"""Доменная сущность пользователя."""

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .exceptions import InvalidEmailError

_EMAIL_RE = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9._-]+$")


@dataclass
class User:
    """Пользователь маркетплейса."""

    email: str
    name: str = ""
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        normalized = self.email.strip()
        if not normalized:
            raise InvalidEmailError(self.email)
        if not _EMAIL_RE.match(normalized):
            raise InvalidEmailError(self.email)
        self.email = normalized
