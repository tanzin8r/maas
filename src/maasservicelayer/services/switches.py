# Copyright 2026 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from datetime import datetime, timezone
import secrets
from typing import Any, cast, Mapping, Optional

from maascommon.workflows.dhcp import (
    CONFIGURE_DHCP_WORKFLOW_NAME,
    ConfigureDHCPParam,
    merge_configure_dhcp_param,
)
from maascommon.workflows.switch_ztp import (
    VERIFY_SWITCH_ZTP_WORKFLOW_NAME,
    VerifySwitchZtpParam,
)
from maasservicelayer.builders.switches import SwitchBuilder
from maasservicelayer.context import Context
from maasservicelayer.db.filters import QuerySpec
from maasservicelayer.db.repositories.filestorage import (
    FileStorageClauseFactory,
)
from maasservicelayer.db.repositories.interfaces import (
    InterfaceClauseFactory,
    InterfaceRepository,
)
from maasservicelayer.db.repositories.nodes import NodeClauseFactory
from maasservicelayer.db.repositories.switches import (
    SwitchClauseFactory,
    SwitchesRepository,
)
from maasservicelayer.exceptions.catalog import NotFoundException
from maasservicelayer.models.base import UNSET
from maasservicelayer.models.secrets import SwitchZtpCredentialsSecret
from maasservicelayer.models.switches import Switch
from maasservicelayer.services.base import BaseService
from maasservicelayer.services.filestorage import FileStorageService
from maasservicelayer.services.interfaces import InterfacesService
from maasservicelayer.services.nodes import NodesService
from maasservicelayer.services.secrets import SecretNotFound, SecretsService
from maasservicelayer.services.temporal import TemporalService
from maasservicelayer.utils.ztp_script_template import (
    render_ztp_script_template,
)


class SwitchesService(BaseService[Switch, SwitchesRepository, SwitchBuilder]):
    resource_logging_name = "switch"

    def __init__(
        self,
        context: Context,
        temporal_service: TemporalService,
        nodes_service: NodesService,
        switches_repository: SwitchesRepository,
        interfaces_repository: InterfaceRepository,
        interfaces_service: InterfacesService,
        secrets_service: SecretsService,
        filestorage_service: FileStorageService,
    ):
        super().__init__(context, switches_repository)
        self.temporal_service = temporal_service
        self.nodes_service = nodes_service
        self.interfaces_repository = interfaces_repository
        self.interfaces_service = interfaces_service
        self.secrets_service = secrets_service
        self.filestorage_service = filestorage_service

    async def pre_create_hook(self, builder: SwitchBuilder) -> None:
        if builder.nos_install_callback_token is UNSET:
            builder.nos_install_callback_token = secrets.token_urlsafe(32)
        if builder.ztp_script_token is UNSET:
            builder.ztp_script_token = secrets.token_urlsafe(32)

    async def _schedule_dhcp_reload_for_rack_controllers(self) -> None:
        rack_nodes = await self.nodes_service.get_many(
            QuerySpec(where=NodeClauseFactory.with_rack_controller_types())
        )
        system_ids = [node.system_id for node in rack_nodes]
        if not system_ids:
            return
        self.temporal_service.register_or_update_workflow_call(
            CONFIGURE_DHCP_WORKFLOW_NAME,
            ConfigureDHCPParam(system_ids=system_ids),
            parameter_merge_func=merge_configure_dhcp_param,
            wait=False,
        )

    async def create_new_switch_and_interface(
        self,
        builder: SwitchBuilder,
        mac_address: str,
    ) -> Switch:
        switch = await self.create(builder)
        await self.interfaces_repository.create_switch_interface(
            switch_id=switch.id, mac=mac_address
        )
        mgmt_mac = builder.mgmt_mac_address
        if (
            mgmt_mac is not UNSET
            and mgmt_mac is not None
            and mgmt_mac != mac_address
        ):
            await self.interfaces_repository.create_switch_interface(
                switch_id=switch.id,
                mac=cast(str, mgmt_mac),
                name="mgmt1",
            )
        return switch

    async def create_switch_and_link_interface(
        self,
        builder: SwitchBuilder,
        interface_id: int,
    ) -> Switch:
        switch = await self.create(builder)
        await self.interfaces_service.link_interface_to_switch(
            interface_id=interface_id, switch_id=switch.id
        )
        return switch

    async def get_switch_by_mac_address(
        self, mac_address: str
    ) -> Optional[Switch]:
        interface = await self.interfaces_repository.get_one(
            query=QuerySpec(
                where=InterfaceClauseFactory.with_mac_address(mac_address)
            )
        )
        if not interface or not interface.switch_id:
            return None
        return await self.repository.get_by_id(id=interface.switch_id)

    async def check_installer_for_switch(
        self, mac_address: str
    ) -> Optional[tuple[Switch, int]]:
        """Look up a switch by MAC; mark NOS installing; return (switch, image_id)."""
        switch = await self.get_switch_by_mac_address(mac_address)
        if not switch or not switch.target_image_id:
            return None
        now = datetime.now(timezone.utc)
        await self.repository.update_by_id(
            switch.id,
            SwitchBuilder(
                installer_requested_at=now,
                nos_install_status="installing",
            ),
        )
        return switch, switch.target_image_id

    async def get_switch_by_ztp_token(self, token: str) -> Optional[Switch]:
        return await self.repository.get_one(
            query=QuerySpec(
                where=SwitchClauseFactory.with_ztp_script_token(token)
            )
        )

    async def record_ztp_started(self, switch: Switch) -> Switch:
        """Mark ZTP started and infer NOS installed on first fetch."""
        now = datetime.now(timezone.utc)
        builder = SwitchBuilder(ztp_started_at=now)
        if switch.nos_install_status in (None, "installing"):
            builder.nos_install_status = "installed"
        return await self.repository.update_by_id(switch.id, builder)

    async def pre_update_instance(
        self, existing_resource: Switch, builder: SwitchBuilder
    ) -> None:
        if builder.ztp_enabled is UNSET:
            return
        if existing_resource.ztp_enabled and builder.ztp_enabled is False:
            await self.delete_ztp_credentials(existing_resource.id)

    async def delete_ztp_credentials(self, switch_id: int) -> None:
        model = SwitchZtpCredentialsSecret(id=switch_id)
        try:
            await self.secrets_service.delete(model)
        except SecretNotFound:
            pass

    async def merge_switch_ztp_credentials(
        self, switch_id: int, updates: Mapping[str, str]
    ) -> None:
        if not updates:
            return
        model = SwitchZtpCredentialsSecret(id=switch_id)
        existing: dict[str, Any] = (
            await self.secrets_service.get_composite_secret(
                model, default={}
            )
        )
        existing.update(updates)
        await self.secrets_service.set_composite_secret(model, existing)

    async def render_ztp_script_bytes(
        self, switch: Switch, template_bytes: bytes
    ) -> bytes:
        model = SwitchZtpCredentialsSecret(id=switch.id)
        secret = await self.secrets_service.get_composite_secret(
            model, default={}
        )
        str_vals = {
            k: v if isinstance(v, str) else str(v) for k, v in secret.items()
        }
        rendered = render_ztp_script_template(
            template_bytes.decode("utf-8"), str_vals
        )
        return rendered.encode("utf-8")

    async def serve_ztp_script(self, token: str) -> tuple[bytes, Switch]:
        """Look up switch by ZTP token, record first fetch, render template.

        Returns the rendered script bytes and the switch.
        Raises NotFoundException when the token or script key is invalid.
        """
        switch = await self.get_switch_by_ztp_token(token)
        if not switch or not switch.ztp_script_key:
            raise NotFoundException()

        first_fetch = switch.ztp_started_at is None
        if first_fetch:
            switch = await self.record_ztp_started(switch)

        if first_fetch and switch.ztp_enabled:
            self.temporal_service.register_or_update_workflow_call(
                VERIFY_SWITCH_ZTP_WORKFLOW_NAME,
                VerifySwitchZtpParam(switch_id=switch.id),
                workflow_id=f"verify-switch-ztp-{switch.id}",
                wait=False,
            )

        file = await self.filestorage_service.get_one(
            query=QuerySpec(
                where=FileStorageClauseFactory.with_key(
                    switch.ztp_script_key
                )
            )
        )
        if not file:
            raise NotFoundException()

        body = await self.render_ztp_script_bytes(switch, file.content)
        return body, switch

    async def post_create_hook(self, resource: Switch) -> None:
        await self._schedule_dhcp_reload_for_rack_controllers()

    async def post_update_hook(
        self, old_resource: Switch, updated_resource: Switch
    ) -> None:
        await self._schedule_dhcp_reload_for_rack_controllers()

    async def post_delete_hook(self, resource: Switch) -> None:
        await self.delete_ztp_credentials(resource.id)
        await self._schedule_dhcp_reload_for_rack_controllers()
