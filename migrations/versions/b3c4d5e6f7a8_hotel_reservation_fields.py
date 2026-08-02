"""add hotel reservation fields

Revision ID: b3c4d5e6f7a8
Revises: a6a0998b6842
Create Date: 2026-08-02 00:00:00.000000

Adds hotel_email, original_check_in_date, original_check_out_date,
notification_status, and notified_at to hotel_bookings.
Backfills original dates from existing check_in/check_out values.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b3c4d5e6f7a8'
down_revision: Union[str, Sequence[str], None] = 'a6a0998b6842'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('hotel_bookings', sa.Column('hotel_email', sa.String(), nullable=True))
    op.add_column('hotel_bookings', sa.Column('original_check_in_date', sa.DateTime(), nullable=True))
    op.add_column('hotel_bookings', sa.Column('original_check_out_date', sa.DateTime(), nullable=True))
    op.add_column('hotel_bookings', sa.Column('notification_status', sa.String(), nullable=True, server_default='PENDING'))
    op.add_column('hotel_bookings', sa.Column('notified_at', sa.DateTime(), nullable=True))

    # Backfill original dates from current dates on existing rows
    op.execute("UPDATE hotel_bookings SET original_check_in_date = check_in_date WHERE original_check_in_date IS NULL")
    op.execute("UPDATE hotel_bookings SET original_check_out_date = check_out_date WHERE original_check_out_date IS NULL")
    op.execute("UPDATE hotel_bookings SET notification_status = 'PENDING' WHERE notification_status IS NULL")

    # Backfill hotel_email for known demo hotel
    op.execute("UPDATE hotel_bookings SET hotel_email = 'reservations@strandpalace.demo' WHERE property_name = 'The Strand Palace Hotel'")
    op.execute("UPDATE hotel_bookings SET hotel_email = 'reservations@hotel.demo' WHERE hotel_email IS NULL")


def downgrade() -> None:
    op.drop_column('hotel_bookings', 'notified_at')
    op.drop_column('hotel_bookings', 'notification_status')
    op.drop_column('hotel_bookings', 'original_check_out_date')
    op.drop_column('hotel_bookings', 'original_check_in_date')
    op.drop_column('hotel_bookings', 'hotel_email')
