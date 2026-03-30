# Copyright 2026 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from typing import Optional, Self

from pydantic import BaseModel

from maasapiserver.v3.api.public.models.responses.base import (
    BaseHal,
    BaseHref,
    HalResponse,
    PaginatedResponse,
)
from maasservicelayer.models.switches import Switch


class SwitchResponse(HalResponse[BaseHal]):
    kind = "Switch"

    id: int
    target_image_id: Optional[int] = None
    ztp_enabled: bool = False
    ztp_script_key: Optional[str] = None
    ztp_option_code: Optional[int] = None
    mgmt_mac_address: Optional[str] = None
    nos_install_status: Optional[str] = None
    ztp_started_at: Optional[str] = None
    ztp_completed_at: Optional[str] = None

    @classmethod
    async def from_model(
        cls, switch: Switch, self_base_hyperlink: str
    ) -> Self:
        return cls(
            id=switch.id,
            target_image_id=switch.target_image_id,
            ztp_enabled=switch.ztp_enabled,
            ztp_script_key=switch.ztp_script_key,
            ztp_option_code=switch.ztp_option_code,
            mgmt_mac_address=switch.mgmt_mac_address,
            nos_install_status=switch.nos_install_status,
            ztp_started_at=(
                switch.ztp_started_at.isoformat()
                if switch.ztp_started_at
                else None
            ),
            ztp_completed_at=(
                switch.ztp_completed_at.isoformat()
                if switch.ztp_completed_at
                else None
            ),
            hal_links=BaseHal(
                self=BaseHref(
                    href=f"{self_base_hyperlink.rstrip('/')}/{switch.id}"
                )
            ),
        )


class SwitchListResponse(PaginatedResponse):
    kind = "SwitchList"
    items: list[SwitchResponse]
