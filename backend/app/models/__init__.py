"""SQLAlchemy ORM models.

Kept separate from `app.schemas` (the Pydantic wire contracts) so the shape of
the database can evolve independently of the API's shape.
"""

from app.models.user import User

__all__ = ["User"]
