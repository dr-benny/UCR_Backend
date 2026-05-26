"""add_sensor_readings_table

Revision ID: b2c082dee240
Revises: 0001
Create Date: 2026-05-26 15:58:44.715690

"""
from typing import Sequence, Union

import geoalchemy2
import sqlalchemy as sa
from alembic import op


revision: str = 'b2c082dee240'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'sensor_readings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('route_id', sa.Integer(), nullable=False),
        sa.Column('dataset_name', sa.String(length=128), nullable=False),
        sa.Column(
            'geom',
            geoalchemy2.types.Geometry(geometry_type='POINT', srid=4326),
            nullable=False,
        ),
        sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('temp_c', sa.Float(), nullable=True),
        sa.Column('humidity_pct', sa.Float(), nullable=True),
        sa.Column('lux', sa.Float(), nullable=True),
        sa.Column('uv_index', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['route_id'], ['survey_routes.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_sensor_readings_dataset_name', 'sensor_readings', ['dataset_name'])
    op.create_index('ix_sensor_readings_id', 'sensor_readings', ['id'])
    op.create_index('ix_sensor_readings_recorded_at', 'sensor_readings', ['recorded_at'])
    op.create_index('ix_sensor_readings_route_id', 'sensor_readings', ['route_id'])


def downgrade() -> None:
    op.drop_index('ix_sensor_readings_route_id', table_name='sensor_readings')
    op.drop_index('ix_sensor_readings_recorded_at', table_name='sensor_readings')
    op.drop_index('ix_sensor_readings_id', table_name='sensor_readings')
    op.drop_index('ix_sensor_readings_dataset_name', table_name='sensor_readings')
    op.drop_table('sensor_readings')
