# Copyright 2026 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from typing import Optional, Union

from pydantic import BaseModel, Field

from maasservicelayer.builders.switches import SwitchBuilder
from maasservicelayer.db.filters import QuerySpec
from maasservicelayer.db.repositories.bootresources import (
    BootResourceClauseFactory,
)
from maasservicelayer.exceptions.catalog import ValidationException
from maasservicelayer.models.base import UNSET, Unset
from maasservicelayer.models.fields import MacAddress
from maasservicelayer.services import ServiceCollectionV3


async def resolve_image_id(
    image: Optional[str], services: ServiceCollectionV3
) -> Union[int, None, Unset]:
    if image is None:
        return UNSET

    name = image
    if "/" not in image:
        name = f"onie/{image}"

    boot_resource = await services.boot_resources.get_one(
        query=QuerySpec(
            where=BootResourceClauseFactory.with_name(name),
        )
    )
    if not boot_resource:
        raise ValidationException.build_for_field(
            field="image",
            message=(
                f"Boot resource '{image}' not found. "
                "Use full format 'onie/vendor-version' or short format "
                "'vendor-version' for ONIE images. "
                "Use 'boot_resources' endpoint to list available images."
            ),
        )

    return boot_resource.id


def _or_unset(val: Optional[object]) -> object:
    """Return *val* when explicitly provided, UNSET otherwise."""
    return val if val is not None else UNSET


class ZtpCredentialsRequest(BaseModel):
    """Optional ZTP template credentials stored in the secrets service."""

    admin_user: Optional[str] = None
    admin_password: Optional[str] = None
    ntp_address: Optional[str] = None
    dns_address: Optional[str] = None
    ssh_keys: Optional[dict[str, str]] = Field(
        default=None,
        description=(
            "Map of UNIX username to public key material; exposed to the ZTP "
            "script as ssh_key_<username> template variables."
        ),
    )
    provisioning_ssh_host: Optional[str] = Field(
        default=None,
        description=(
            "Management IP or hostname MAAS uses for SSH verification after "
            "ZTP starts (same credentials as admin_user / admin_password)."
        ),
    )

    def to_secret_updates(self) -> dict[str, str]:
        out: dict[str, str] = {}
        if self.admin_user is not None:
            out["admin_user"] = self.admin_user
        if self.admin_password is not None:
            out["admin_password"] = self.admin_password
        if self.ntp_address is not None:
            out["ntp_address"] = self.ntp_address
        if self.dns_address is not None:
            out["dns_address"] = self.dns_address
        if self.provisioning_ssh_host is not None:
            out["provisioning_ssh_host"] = self.provisioning_ssh_host
        if self.ssh_keys:
            for username, key in self.ssh_keys.items():
                out[f"ssh_key_{username}"] = key
        return out


class SwitchRequest(BaseModel):
    name: Optional[str] = None
    mac_address: MacAddress
    image: Optional[str] = Field(
        default=None,
        description=(
            "Supports full format (e.g., 'onie/mellanox-3.8.0') or short "
            "format for ONIE images (e.g., 'mellanox-3.8.0')."
        ),
    )
    ztp_enabled: Optional[bool] = Field(default=None)
    ztp_script_key: Optional[str] = Field(default=None)
    ztp_option_code: Optional[int] = Field(default=None)
    mgmt_mac_address: Optional[MacAddress] = Field(
        default=None,
        description=(
            "Optional management MAC used by the NOS after installation. "
            "When set, MAAS creates a second interface so both MACs receive "
            "the ZTP option."
        ),
    )
    ztp_credentials: Optional[ZtpCredentialsRequest] = Field(
        default=None,
        description=(
            "When ZTP is enabled, optional values substituted into the uploaded "
            "ZTP script ({{ admin_user }}, {{ admin_password }}, etc.)."
        ),
    )

    async def to_switch_builder(
        self, services: ServiceCollectionV3
    ) -> SwitchBuilder:
        return SwitchBuilder(
            target_image_id=await resolve_image_id(self.image, services),
            ztp_enabled=_or_unset(self.ztp_enabled),
            ztp_script_key=_or_unset(self.ztp_script_key),
            ztp_option_code=_or_unset(self.ztp_option_code),
            mgmt_mac_address=_or_unset(self.mgmt_mac_address),
        )


class SwitchUpdateRequest(BaseModel):
    image: Optional[str] = Field(
        default=None,
        description=(
            "Supports full format (e.g., 'onie/mellanox-3.8.0') or short "
            "format for ONIE images (e.g., 'mellanox-3.8.0')."
        ),
    )
    ztp_enabled: Optional[bool] = Field(default=None)
    ztp_script_key: Optional[str] = Field(default=None)
    ztp_option_code: Optional[int] = Field(default=None)
    mgmt_mac_address: Optional[MacAddress] = Field(
        default=None,
        description=(
            "Optional management MAC used by the NOS after installation. "
            "When set, MAAS updates the secondary interface MAC used for ZTP."
        ),
    )
    ztp_credentials: Optional[ZtpCredentialsRequest] = Field(
        default=None,
        description="Partial update of ZTP template credentials in the secret store.",
    )

    async def to_switch_builder(
        self, services: ServiceCollectionV3
    ) -> SwitchBuilder:
        return SwitchBuilder(
            target_image_id=await resolve_image_id(self.image, services),
            ztp_enabled=_or_unset(self.ztp_enabled),
            ztp_script_key=_or_unset(self.ztp_script_key),
            ztp_option_code=_or_unset(self.ztp_option_code),
            mgmt_mac_address=_or_unset(self.mgmt_mac_address),
        )
