# Copyright 2026 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from unittest.mock import AsyncMock, Mock

import pytest

from maasservicelayer.builders.switches import SwitchBuilder
from maasservicelayer.context import Context
from maasservicelayer.db.repositories.interfaces import InterfaceRepository
from maasservicelayer.db.repositories.switches import SwitchesRepository
from maasservicelayer.models.base import MaasBaseModel, UNSET
from maasservicelayer.models.switches import Switch
from maasservicelayer.services import (
    InterfacesService,
    NodesService,
    SwitchesService,
)
from maasservicelayer.services.base import BaseService
from maasservicelayer.services.filestorage import FileStorageService
from maasservicelayer.services.secrets import SecretsService
from maasservicelayer.services.temporal import TemporalService
from maasservicelayer.utils.date import utcnow
from tests.maasservicelayer.services.base import ServiceCommonTests

TEST_SWITCH = Switch(
    id=10,
    target_image_id=None,
    ztp_enabled=True,
    ztp_script_key="my-key",
    ztp_option_code=239,
    mgmt_mac_address=None,
    installer_requested_at=None,
    nos_install_status=None,
    nos_install_callback_token="cb-tok",
    ztp_started_at=None,
    ztp_completed_at=None,
    ztp_script_token="ztp-tok",
    created=utcnow(),
    updated=utcnow(),
)


def _build_service(
    switches_repo=None,
    interfaces_repo=None,
    interfaces_service=None,
    nodes_service=None,
    temporal_service=None,
    secrets_service=None,
    filestorage_service=None,
) -> SwitchesService:
    return SwitchesService(
        context=Context(),
        temporal_service=temporal_service or Mock(TemporalService),
        nodes_service=nodes_service or Mock(NodesService),
        switches_repository=switches_repo or Mock(SwitchesRepository),
        interfaces_repository=interfaces_repo or Mock(InterfaceRepository),
        interfaces_service=interfaces_service or Mock(InterfacesService),
        secrets_service=secrets_service or Mock(SecretsService),
        filestorage_service=filestorage_service or Mock(FileStorageService),
    )


@pytest.mark.asyncio
class TestCommonSwitchesService(ServiceCommonTests):
    @pytest.fixture
    def service_instance(self) -> BaseService:
        return _build_service()

    @pytest.fixture
    def test_instance(self) -> MaasBaseModel:
        return TEST_SWITCH


@pytest.mark.asyncio
class TestSwitchesService:
    async def test_pre_create_hook_generates_tokens(self) -> None:
        svc = _build_service()
        builder = SwitchBuilder(ztp_enabled=True)
        assert builder.nos_install_callback_token is UNSET
        assert builder.ztp_script_token is UNSET

        await svc.pre_create_hook(builder)

        assert builder.nos_install_callback_token is not UNSET
        assert isinstance(builder.nos_install_callback_token, str)
        assert builder.ztp_script_token is not UNSET
        assert isinstance(builder.ztp_script_token, str)

    async def test_pre_create_hook_preserves_existing_tokens(self) -> None:
        svc = _build_service()
        builder = SwitchBuilder(
            nos_install_callback_token="keep-me",
            ztp_script_token="keep-too",
        )
        await svc.pre_create_hook(builder)
        assert builder.nos_install_callback_token == "keep-me"
        assert builder.ztp_script_token == "keep-too"

    async def test_get_switch_by_ztp_token(self) -> None:
        repo = Mock(SwitchesRepository)
        repo.get_one.return_value = TEST_SWITCH
        svc = _build_service(switches_repo=repo)

        result = await svc.get_switch_by_ztp_token("ztp-tok")
        assert result == TEST_SWITCH

    async def test_record_ztp_started_sets_fields(self) -> None:
        repo = Mock(SwitchesRepository)
        updated = TEST_SWITCH.copy(
            update={"ztp_started_at": utcnow(), "nos_install_status": "installed"}
        )
        repo.update_by_id.return_value = updated
        svc = _build_service(switches_repo=repo)

        result = await svc.record_ztp_started(TEST_SWITCH)

        assert result.nos_install_status == "installed"
        assert result.ztp_started_at is not None
        call_args = repo.update_by_id.call_args
        builder = call_args.args[1]
        assert builder.ztp_started_at is not UNSET
        assert builder.nos_install_status == "installed"

    async def test_record_ztp_started_skips_nos_if_already_installed(
        self,
    ) -> None:
        repo = Mock(SwitchesRepository)
        switch = TEST_SWITCH.copy(update={"nos_install_status": "installed"})
        repo.update_by_id.return_value = switch
        svc = _build_service(switches_repo=repo)

        await svc.record_ztp_started(switch)

        call_args = repo.update_by_id.call_args
        builder = call_args.args[1]
        assert builder.nos_install_status is UNSET

    async def test_check_installer_for_switch_returns_none_no_image(
        self,
    ) -> None:
        iface_repo = Mock(InterfaceRepository)
        iface_repo.get_one.return_value = Mock(switch_id=1)
        repo = Mock(SwitchesRepository)
        repo.get_by_id.return_value = TEST_SWITCH.copy(
            update={"target_image_id": None}
        )
        svc = _build_service(
            switches_repo=repo, interfaces_repo=iface_repo
        )

        result = await svc.check_installer_for_switch("00:11:22:33:44:55")
        assert result is None

    async def test_check_installer_for_switch_returns_switch_and_image(
        self,
    ) -> None:
        switch = TEST_SWITCH.copy(update={"target_image_id": 42})
        iface_repo = Mock(InterfaceRepository)
        iface_repo.get_one.return_value = Mock(switch_id=switch.id)
        repo = Mock(SwitchesRepository)
        repo.get_by_id.return_value = switch
        repo.update_by_id.return_value = switch
        svc = _build_service(
            switches_repo=repo, interfaces_repo=iface_repo
        )

        result = await svc.check_installer_for_switch("00:11:22:33:44:55")
        assert result is not None
        returned_switch, image_id = result
        assert returned_switch.id == switch.id
        assert image_id == 42

    async def test_pre_update_instance_deletes_creds_on_ztp_disable(
        self,
    ) -> None:
        secrets = Mock(SecretsService)
        svc = _build_service(secrets_service=secrets)
        existing = TEST_SWITCH.copy(update={"ztp_enabled": True})
        builder = SwitchBuilder(ztp_enabled=False)

        await svc.pre_update_instance(existing, builder)
        secrets.delete.assert_called_once()

    async def test_pre_update_instance_noop_when_not_changing_ztp(
        self,
    ) -> None:
        secrets = Mock(SecretsService)
        svc = _build_service(secrets_service=secrets)
        builder = SwitchBuilder()

        await svc.pre_update_instance(TEST_SWITCH, builder)
        secrets.delete.assert_not_called()

    async def test_merge_switch_ztp_credentials(self) -> None:
        secrets = Mock(SecretsService)
        secrets.get_composite_secret = AsyncMock(
            return_value={"admin_user": "old"}
        )
        svc = _build_service(secrets_service=secrets)

        await svc.merge_switch_ztp_credentials(
            1, {"admin_user": "new", "ntp_address": "1.2.3.4"}
        )

        secrets.set_composite_secret.assert_called_once()
        stored = secrets.set_composite_secret.call_args.args[1]
        assert stored["admin_user"] == "new"
        assert stored["ntp_address"] == "1.2.3.4"

    async def test_merge_switch_ztp_credentials_noop_empty(self) -> None:
        secrets = Mock(SecretsService)
        svc = _build_service(secrets_service=secrets)
        await svc.merge_switch_ztp_credentials(1, {})
        secrets.get_composite_secret.assert_not_called()

    async def test_render_ztp_script_bytes(self) -> None:
        secrets = Mock(SecretsService)
        secrets.get_composite_secret = AsyncMock(
            return_value={"admin_user": "admin", "admin_password": "pw"}
        )
        svc = _build_service(secrets_service=secrets)

        template = b"user={{ admin_user }} pass={{ admin_password }}"
        result = await svc.render_ztp_script_bytes(TEST_SWITCH, template)
        assert result == b"user=admin pass=pw"

    async def test_serve_ztp_script_first_fetch(self) -> None:
        repo = Mock(SwitchesRepository)
        repo.get_one.return_value = TEST_SWITCH
        updated = TEST_SWITCH.copy(
            update={
                "ztp_started_at": utcnow(),
                "nos_install_status": "installed",
            }
        )
        repo.update_by_id.return_value = updated

        secrets = Mock(SecretsService)
        secrets.get_composite_secret = AsyncMock(return_value={"x": "1"})

        file_mock = Mock(content=b"val={{ x }}")
        fs = Mock(FileStorageService)
        fs.get_one = AsyncMock(return_value=file_mock)

        temporal = Mock(TemporalService)

        svc = _build_service(
            switches_repo=repo,
            secrets_service=secrets,
            filestorage_service=fs,
            temporal_service=temporal,
        )

        body, switch = await svc.serve_ztp_script("ztp-tok")
        assert body == b"val=1"
        temporal.register_or_update_workflow_call.assert_called_once()

    async def test_serve_ztp_script_subsequent_fetch_no_workflow(
        self,
    ) -> None:
        already_started = TEST_SWITCH.copy(
            update={
                "ztp_started_at": utcnow(),
                "nos_install_status": "installed",
            }
        )
        repo = Mock(SwitchesRepository)
        repo.get_one.return_value = already_started

        secrets = Mock(SecretsService)
        secrets.get_composite_secret = AsyncMock(return_value={})

        file_mock = Mock(content=b"plain text")
        fs = Mock(FileStorageService)
        fs.get_one = AsyncMock(return_value=file_mock)

        temporal = Mock(TemporalService)

        svc = _build_service(
            switches_repo=repo,
            secrets_service=secrets,
            filestorage_service=fs,
            temporal_service=temporal,
        )

        body, _switch = await svc.serve_ztp_script("ztp-tok")
        assert body == b"plain text"
        temporal.register_or_update_workflow_call.assert_not_called()

    async def test_post_delete_hook_cleans_credentials(self) -> None:
        secrets = Mock(SecretsService)
        nodes = Mock(NodesService)
        nodes.get_many = AsyncMock(return_value=[])
        svc = _build_service(secrets_service=secrets, nodes_service=nodes)

        await svc.post_delete_hook(TEST_SWITCH)
        secrets.delete.assert_called_once()
