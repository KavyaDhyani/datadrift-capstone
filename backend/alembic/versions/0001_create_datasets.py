"""create datasets table

Revision ID: 0001_create_datasets
Revises:
Create Date: 2026-10-14
"""

import sqlalchemy as sa

from alembic import op

revision = "0001_create_datasets"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "datasets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("dataset_name", sa.String(length=120), nullable=False),
        sa.Column("version_tag", sa.String(length=60), nullable=False),
        sa.Column("record_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("missing_pct", sa.Float(), nullable=False, server_default="0"),
        sa.Column("drift_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="VERIFIED"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("dataset_name", "version_tag", name="uq_dataset_version"),
        sa.CheckConstraint("drift_score >= 0 AND drift_score <= 1", name="ck_drift_score_range"),
        sa.CheckConstraint("status IN ('VERIFIED', 'DRIFT_DETECTED', 'ARCHIVED')", name="ck_status_values"),
    )
    op.create_index("ix_datasets_dataset_name", "datasets", ["dataset_name"])


def downgrade():
    op.drop_index("ix_datasets_dataset_name", table_name="datasets")
    op.drop_table("datasets")
