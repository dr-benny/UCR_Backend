"""Initial schema: survey_routes, street_analyses, jobs

Revision ID: 0001
Revises:
Create Date: 2026-05-25

NOTE: If you are running this against an existing database that was created
with Base.metadata.create_all(), stamp it instead of running it:
    alembic stamp 0001
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
import geoalchemy2

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "survey_routes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_survey_routes_id", "survey_routes", ["id"], unique=False)

    op.create_table(
        "street_analyses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("route_id", sa.Integer(), nullable=True),
        sa.Column("order_index", sa.Integer(), nullable=True),
        sa.Column(
            "geom",
            geoalchemy2.types.Geometry(geometry_type="POINT", srid=4326),
            nullable=False,
        ),
        sa.Column("heading", sa.Float(), nullable=True),
        sa.Column("pitch", sa.Float(), nullable=True),
        sa.Column("fov", sa.Float(), nullable=True),
        sa.Column("streetview_image_url", sa.Text(), nullable=True),
        sa.Column("image_path", sa.Text(), nullable=True),
        sa.Column("urban_morphology", postgresql.JSONB(), nullable=True),
        sa.Column("vegetation", postgresql.JSONB(), nullable=True),
        sa.Column("surface_and_flood", postgresql.JSONB(), nullable=True),
        sa.Column("health_livability", postgresql.JSONB(), nullable=True),
        sa.Column("scene_description", sa.Text(), nullable=True),
        sa.Column("observed_features", postgresql.JSONB(), nullable=True),
        sa.Column("reference_objects", postgresql.JSONB(), nullable=True),
        sa.Column("evidence", postgresql.JSONB(), nullable=True),
        sa.Column("confidence_scores", postgresql.JSONB(), nullable=True),
        sa.Column("raw_ai_response", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["route_id"], ["survey_routes.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_street_analyses_id", "street_analyses", ["id"], unique=False)
    op.create_index(
        "ix_street_analyses_route_id", "street_analyses", ["route_id"], unique=False
    )

    op.create_table(
        "jobs",
        sa.Column("id", sa.String(32), nullable=False),
        sa.Column("job_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("request_data", postgresql.JSONB(), nullable=False),
        sa.Column("result_data", postgresql.JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("progress_current", sa.Integer(), nullable=False),
        sa.Column("progress_total", sa.Integer(), nullable=False),
        sa.Column("route_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["route_id"], ["survey_routes.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_jobs_job_type", "jobs", ["job_type"], unique=False)
    op.create_index("ix_jobs_status", "jobs", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_jobs_status", table_name="jobs")
    op.drop_index("ix_jobs_job_type", table_name="jobs")
    op.drop_table("jobs")

    op.drop_index("ix_street_analyses_route_id", table_name="street_analyses")
    op.drop_index("ix_street_analyses_id", table_name="street_analyses")
    op.drop_table("street_analyses")

    op.drop_index("ix_survey_routes_id", table_name="survey_routes")
    op.drop_table("survey_routes")
