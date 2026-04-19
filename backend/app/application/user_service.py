"""Сервис для работы с пользователями."""

import uuid
from typing import List, Optional

from sqlalchemy.exc import IntegrityError

from app.domain.user import User
from app.domain.exceptions import EmailAlreadyExistsError, UserNotFoundError


class UserService:
    """Сервис для операций с пользователями."""

    def __init__(self, repo):
        self.repo = repo

    async def register(self, email: str, name: str = "") -> User:
        existing = await self.repo.find_by_email(email)
        if existing is not None:
            raise EmailAlreadyExistsError(email)
        user = User(email=email, name=name or "")
        try:
            await self.repo.save(user)
        except IntegrityError as exc:
            raise EmailAlreadyExistsError(email) from exc
        return user

    async def get_by_id(self, user_id: uuid.UUID) -> User:
        user = await self.repo.find_by_id(user_id)
        if user is None:
            raise UserNotFoundError(user_id)
        return user

    async def get_by_email(self, email: str) -> Optional[User]:
        return await self.repo.find_by_email(email)

    async def list_users(self) -> List[User]:
        return await self.repo.find_all()
