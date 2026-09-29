"""add household agents and planning sessions

Revision ID: c7d2f84a1e93
Revises: a3c9e1f27b40
Create Date: 2026-09-29 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7d2f84a1e93'
down_revision: Union[str, Sequence[str], None] = 'a3c9e1f27b40'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'agent_memory',
        sa.Column('household_id', sa.String(length=20), nullable=False),
        sa.Column('sell_margin', sa.Float(), nullable=False),
        sa.Column('buy_margin', sa.Float(), nullable=False),
        sa.Column('price_by_hour', sa.JSON(), nullable=False),
        sa.Column('trades', sa.Integer(), nullable=False),
        sa.Column('kwh_sold', sa.Float(), nullable=False),
        sa.Column('kwh_bought', sa.Float(), nullable=False),
        sa.Column('savings_inr', sa.Float(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['household_id'], ['households.id']),
        sa.PrimaryKeyConstraint('household_id'),
    )
    op.create_table(
        'agent_decisions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('slot', sa.Integer(), nullable=False),
        sa.Column('household_id', sa.String(length=20), nullable=False),
        sa.Column('hour_of_day', sa.Integer(), nullable=False),
        sa.Column('strategy', sa.String(length=20), nullable=False),
        sa.Column('side', sa.String(length=4), nullable=False),
        sa.Column('firm', sa.Boolean(), nullable=False),
        sa.Column('quantity_kwh', sa.Float(), nullable=False),
        sa.Column('limit_price', sa.Float(), nullable=True),
        sa.Column('opening_price', sa.Float(), nullable=True),
        sa.Column('risk_quantile', sa.Float(), nullable=True),
        sa.Column('expected_price', sa.Float(), nullable=False),
        sa.Column('spill_kwh', sa.Float(), nullable=False),
        sa.Column('short_kwh', sa.Float(), nullable=False),
        sa.Column('stored_kwh', sa.Float(), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('outcome', sa.Text(), nullable=False),
        sa.Column('reasons', sa.JSON(), nullable=False),
        sa.Column(
            'created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False
        ),
        sa.ForeignKeyConstraint(['household_id'], ['households.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_agent_decisions_household_id'), 'agent_decisions', ['household_id'])
    op.create_index(op.f('ix_agent_decisions_slot'), 'agent_decisions', ['slot'])

    op.create_table(
        'session_households',
        sa.Column('household_id', sa.String(length=20), nullable=False),
        sa.Column('start_soc', sa.Float(), nullable=False),
        sa.Column('guests', sa.Integer(), nullable=False),
        sa.Column('away_from', sa.Float(), nullable=True),
        sa.Column('away_to', sa.Float(), nullable=True),
        sa.Column('work_from_home', sa.Boolean(), nullable=False),
        sa.Column('panel_derate', sa.Float(), nullable=False),
        sa.Column('battery_capacity_kwh', sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(['household_id'], ['households.id']),
        sa.PrimaryKeyConstraint('household_id'),
    )
    op.create_table(
        'session_forecasts',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('slot', sa.Integer(), nullable=False),
        sa.Column('household_id', sa.String(length=20), nullable=False),
        sa.Column('day', sa.Date(), nullable=False),
        sa.Column('hour_of_day', sa.Integer(), nullable=False),
        sa.Column('consumption_p10', sa.Float(), nullable=False),
        sa.Column('consumption_p50', sa.Float(), nullable=False),
        sa.Column('consumption_p90', sa.Float(), nullable=False),
        sa.Column('generation_p10', sa.Float(), nullable=False),
        sa.Column('generation_p50', sa.Float(), nullable=False),
        sa.Column('generation_p90', sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(['household_id'], ['households.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_session_forecasts_household_id'), 'session_forecasts', ['household_id'])
    op.create_index(op.f('ix_session_forecasts_slot'), 'session_forecasts', ['slot'])
    op.create_table(
        'session_positions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('slot', sa.Integer(), nullable=False),
        sa.Column('household_id', sa.String(length=20), nullable=False),
        sa.Column('p2p_sold_kwh', sa.Float(), nullable=False),
        sa.Column('p2p_bought_kwh', sa.Float(), nullable=False),
        sa.Column('eb_bought_kwh', sa.Float(), nullable=False),
        sa.Column('eb_sold_kwh', sa.Float(), nullable=False),
        sa.Column('unserved_kwh', sa.Float(), nullable=False),
        sa.Column('retail_tariff', sa.Float(), nullable=False),
        sa.Column('feed_in_tariff', sa.Float(), nullable=False),
        sa.Column('eb_available', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['household_id'], ['households.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_session_positions_household_id'), 'session_positions', ['household_id'])
    op.create_index(op.f('ix_session_positions_slot'), 'session_positions', ['slot'])

    # The free-running clock is gone: sessions are stepped explicitly.
    op.drop_column('simulation_state', 'running')
    op.drop_column('simulation_state', 'seconds_per_tick')
    op.add_column('simulation_state', sa.Column('start_hour', sa.Integer(), nullable=False, server_default='14'))
    op.add_column('simulation_state', sa.Column('horizon_hours', sa.Integer(), nullable=False, server_default='12'))
    op.add_column('simulation_state', sa.Column('status', sa.String(length=10), nullable=False, server_default='setup'))
    op.add_column('simulation_state', sa.Column('what_ifs', sa.JSON(), nullable=False, server_default='{}'))

    for column in ('contracted_kwh', 'unserved_kwh', 'curtailed_kwh'):
        op.add_column('meter_readings', sa.Column(column, sa.Float(), nullable=False, server_default='0'))


def downgrade() -> None:
    """Downgrade schema."""
    for column in ('curtailed_kwh', 'unserved_kwh', 'contracted_kwh'):
        op.drop_column('meter_readings', column)
    for column in ('what_ifs', 'status', 'horizon_hours', 'start_hour'):
        op.drop_column('simulation_state', column)
    op.add_column(
        'simulation_state',
        sa.Column('seconds_per_tick', sa.Float(), nullable=False, server_default='2.0'),
    )
    op.add_column(
        'simulation_state',
        sa.Column('running', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.drop_index(op.f('ix_session_positions_slot'), table_name='session_positions')
    op.drop_index(op.f('ix_session_positions_household_id'), table_name='session_positions')
    op.drop_table('session_positions')
    op.drop_index(op.f('ix_session_forecasts_slot'), table_name='session_forecasts')
    op.drop_index(op.f('ix_session_forecasts_household_id'), table_name='session_forecasts')
    op.drop_table('session_forecasts')
    op.drop_table('session_households')
    op.drop_index(op.f('ix_agent_decisions_slot'), table_name='agent_decisions')
    op.drop_index(op.f('ix_agent_decisions_household_id'), table_name='agent_decisions')
    op.drop_table('agent_decisions')
    op.drop_table('agent_memory')
