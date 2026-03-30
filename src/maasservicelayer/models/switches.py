# Copyright 2026 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from datetime import datetime
from typing import Optional

from maasservicelayer.models.base import MaasTimestampedBaseModel


class Switch(MaasTimestampedBaseModel):
    """Model representing a network switch.

    A switch is a network device provisioned by MAAS.
    """

    target_image_id: Optional[int] = None
    ztp_enabled: bool = False
    ztp_script_key: Optional[str] = None
    ztp_option_code: Optional[int] = None
    mgmt_mac_address: Optional[str] = None
    installer_requested_at: Optional[datetime] = None
    nos_install_status: Optional[str] = None
    nos_install_callback_token: Optional[str] = None
    ztp_started_at: Optional[datetime] = None
    ztp_completed_at: Optional[datetime] = None
    ztp_script_token: Optional[str] = None
