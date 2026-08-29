"""SQLAlchemy declarative base shared by all models."""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Common base class for all ORM models."""
