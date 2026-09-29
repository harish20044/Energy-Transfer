"""add a calendar date to the simulation clock

Revision ID: a3c9e1f27b40
Revises: 48110d56fe6f
Create Date: 2026-09-29 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3c9e1f27b40'
down_revision: Union[str, Sequence[str], None] = '48110d56fe6f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # server_default so the existing singleton row gets a date too.
    op.add_column(
        'simulation_state',
        sa.Column('sim_date', sa.Date(), nullable=False, server_default='2026-05-15'),
    )
    # The old curve-based "clear" default becomes the climatology-driven one.
    op.execute("UPDATE simulation_state SET scenario = 'auto' WHERE scenario = 'clear'")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        "UPDATE simulation_state SET scenario = 'clear' WHERE scenario IN ('auto', 'rainy')"
    )
    op.drop_column('simulation_state', 'sim_date')
