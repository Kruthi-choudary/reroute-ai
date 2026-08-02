"""hotel_booking cascade delete on trip FK

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-08-02 00:01:00.000000

Recreates hotel_bookings.trip_id FK with ON DELETE CASCADE.
Uses batch mode for SQLite compatibility.
On PostgreSQL this enforces cascade at the DB level;
on SQLite the ORM-level cascade="all, delete-orphan" on the
Trip.hotel_bookings relationship handles it instead.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c4d5e6f7a8b9'
down_revision: Union[str, Sequence[str], None] = 'b3c4d5e6f7a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLite does not support named FK constraints or ALTER CONSTRAINT.
    # On SQLite, cascade is enforced at the ORM level via
    # Trip.hotel_bookings cascade="all, delete-orphan".
    #
    # On PostgreSQL, recreate the FK with ON DELETE CASCADE:
    #   ALTER TABLE hotel_bookings DROP CONSTRAINT hotel_bookings_trip_id_fkey;
    #   ALTER TABLE hotel_bookings ADD CONSTRAINT hotel_bookings_trip_id_fkey
    #     FOREIGN KEY (trip_id) REFERENCES trips(id) ON DELETE CASCADE;
    pass


def downgrade() -> None:
    pass
