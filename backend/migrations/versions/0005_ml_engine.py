"""Add model metadata and forecast uncertainty/provenance."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005_ml_engine"
down_revision: Union[str, None] = "0004_complete_inventory"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_forecast_business_target_period",
        "forecasts",
        ["business_id", "target_type", "target_id", "period_start"],
    )
    op.create_index("ix_anomaly_business_created", "anomalies", ["business_id", "created_at"])
    with op.batch_alter_table("forecasts") as batch:
        batch.add_column(sa.Column("lower_value", sa.Numeric(14, 3), nullable=True))
        batch.add_column(sa.Column("upper_value", sa.Numeric(14, 3), nullable=True))
        batch.add_column(
            sa.Column(
                "generated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            )
        )

    with op.batch_alter_table("anomalies") as batch:
        batch.add_column(
            sa.Column(
                "model_version", sa.String(100), nullable=False, server_default="robust_mad_v1"
            )
        )
        batch.add_column(sa.Column("provenance", sa.JSON(), nullable=True))

    op.create_table(
        "model_versions",
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("model_type", sa.String(60), nullable=False),
        sa.Column("version", sa.String(100), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("dataset_kind", sa.String(32), nullable=False),
        sa.Column("training_rows", sa.Integer(), nullable=False),
        sa.Column("feature_names", sa.JSON(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("artifact_uri", sa.String(500), nullable=True),
        sa.Column(
            "trained_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_model_versions_business_id", "model_versions", ["business_id"])
    op.create_index(
        "uq_model_version_business_type_version",
        "model_versions",
        ["business_id", "model_type", "version"],
        unique=True,
    )
    op.create_index(
        "ix_model_version_business_type_created",
        "model_versions",
        ["business_id", "model_type", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("model_versions")
    op.drop_index("ix_anomaly_business_created", table_name="anomalies")
    op.drop_index("ix_forecast_business_target_period", table_name="forecasts")
    with op.batch_alter_table("anomalies") as batch:
        batch.drop_column("provenance")
        batch.drop_column("model_version")
    with op.batch_alter_table("forecasts") as batch:
        batch.drop_column("generated_at")
        batch.drop_column("upper_value")
        batch.drop_column("lower_value")
