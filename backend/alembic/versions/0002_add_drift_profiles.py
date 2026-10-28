"""add column profiles and computed drift

Revision ID: 0002_add_drift_profiles
Revises: 0001_create_datasets
Create Date: 2026-10-28
"""

import sqlalchemy as sa

from alembic import op

revision = "0002_add_drift_profiles"
down_revision = "0001_create_datasets"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("datasets") as batch:
        batch.add_column(sa.Column("drift_method", sa.String(length=20), nullable=False, server_default="provided"))
        batch.add_column(sa.Column("profile", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("column_drift", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("baseline_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_datasets_baseline", "datasets", ["baseline_id"], ["id"], ondelete="SET NULL")
        batch.create_check_constraint(
            "ck_drift_method_values", "drift_method IN ('provided', 'computed', 'baseline', 'unscored')"
        )


def downgrade():
    with op.batch_alter_table("datasets") as batch:
        batch.drop_constraint("ck_drift_method_values", type_="check")
        batch.drop_constraint("fk_datasets_baseline", type_="foreignkey")
        batch.drop_column("baseline_id")
        batch.drop_column("column_drift")
        batch.drop_column("profile")
        batch.drop_column("drift_method")
