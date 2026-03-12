"""
Attora — Pagination Pydantic Schemas

Generic paginated response wrapper for list endpoints.
"""

from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response wrapper."""

    items: list[T]
    total: int
    page: int
    page_size: int
