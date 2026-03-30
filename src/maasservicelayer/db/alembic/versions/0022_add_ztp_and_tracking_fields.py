# Copyright 2026 Canonical Ltd. This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""add_ztp_and_tracking_fields

Add ZTP configuration and provisioning-tracking columns to
maasserver_switch.

Revision ID: 0022
Revises: 0021
Create Date: 2026-03-23 12:00:00.000000+00:00

"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "maasserver_switch",
        sa.Column(
            "ztp_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    op.add_column(
        "maasserver_switch",
        sa.Column(
            "ztp_script_key",
            sa.String(length=36),
            nullable=True,
        ),
    )
    op.add_column(
        "maasserver_switch",
        sa.Column(
            "ztp_option_code",
            sa.Integer(),
            nullable=True,
        ),
    )
    op.add_column(
        "maasserver_switch",
        sa.Column(
            "mgmt_mac_address",
            sa.String(length=17),
            nullable=True,
        ),
    )
    op.add_column(
        "maasserver_switch",
        sa.Column(
            "installer_requested_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "maasserver_switch",
        sa.Column(
            "nos_install_status",
            sa.String(length=20),
            nullable=True,
        ),
    )
    op.add_column(
        "maasserver_switch",
        sa.Column(
            "nos_install_callback_token",
            sa.String(length=64),
            nullable=True,
        ),
    )
    op.add_column(
        "maasserver_switch",
        sa.Column(
            "ztp_started_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "maasserver_switch",
        sa.Column(
            "ztp_completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "maasserver_switch",
        sa.Column(
            "ztp_script_token",
            sa.String(length=64),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("maasserver_switch", "ztp_script_token")
    op.drop_column("maasserver_switch", "ztp_completed_at")
    op.drop_column("maasserver_switch", "ztp_started_at")
    op.drop_column(
        "maasserver_switch", "nos_install_callback_token"
    )
    op.drop_column("maasserver_switch", "nos_install_status")
    op.drop_column(
        "maasserver_switch", "installer_requested_at"
    )
    op.drop_column("maasserver_switch", "mgmt_mac_address")
    op.drop_column("maasserver_switch", "ztp_option_code")
    op.drop_column("maasserver_switch", "ztp_script_key")
    op.drop_column("maasserver_switch", "ztp_enabled")
