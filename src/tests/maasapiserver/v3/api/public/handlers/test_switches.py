# Copyright 2026 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from typing import Callable
from unittest.mock import AsyncMock, Mock

from httpx import AsyncClient
import pytest

from maasapiserver.v3.api.public.models.responses.switches import (
    SwitchListResponse,
    SwitchResponse,
)
from maasapiserver.v3.constants import V3_API_PREFIX
from maascommon.openfga.base import MAASResourceEntitlement
from maasservicelayer.exceptions.catalog import NotFoundException
from maasservicelayer.models.base import ListResult
from maasservicelayer.models.switches import Switch
from maasservicelayer.services import ServiceCollectionV3
from maasservicelayer.services.switches import SwitchesService
from maasservicelayer.utils.date import utcnow
from tests.maasapiserver.v3.api.public.handlers.base import (
    ApiCommonTests,
    Endpoint,
)

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


class TestSwitchesApi(ApiCommonTests):
    BASE_PATH = f"{V3_API_PREFIX}/switches"

    @pytest.fixture
    def endpoints_with_authorization(self) -> list[Endpoint]:
        return [
            Endpoint(
                method="GET",
                path=self.BASE_PATH,
                permission=MAASResourceEntitlement.CAN_VIEW_GLOBAL_ENTITIES,
            ),
            Endpoint(
                method="GET",
                path=f"{self.BASE_PATH}/1",
                permission=MAASResourceEntitlement.CAN_VIEW_GLOBAL_ENTITIES,
            ),
            Endpoint(
                method="POST",
                path=self.BASE_PATH,
                permission=MAASResourceEntitlement.CAN_EDIT_GLOBAL_ENTITIES,
            ),
            Endpoint(
                method="PATCH",
                path=f"{self.BASE_PATH}/1",
                permission=MAASResourceEntitlement.CAN_EDIT_GLOBAL_ENTITIES,
            ),
            Endpoint(
                method="DELETE",
                path=f"{self.BASE_PATH}/1",
                permission=MAASResourceEntitlement.CAN_EDIT_GLOBAL_ENTITIES,
            ),
        ]

    async def test_list(
        self,
        services_mock: ServiceCollectionV3,
        mocked_api_client_user_with_permissions: Callable[..., AsyncClient],
    ) -> None:
        client = mocked_api_client_user_with_permissions(
            MAASResourceEntitlement.CAN_VIEW_GLOBAL_ENTITIES,
        )
        services_mock.switches = Mock(SwitchesService)
        services_mock.switches.list.return_value = ListResult[Switch](
            items=[TEST_SWITCH], total=1
        )
        response = await client.get(self.BASE_PATH)
        assert response.status_code == 200
        body = SwitchListResponse(**response.json())
        assert len(body.items) == 1
        assert body.total == 1
        assert body.next is None

    async def test_list_pagination(
        self,
        services_mock: ServiceCollectionV3,
        mocked_api_client_user_with_permissions: Callable[..., AsyncClient],
    ) -> None:
        client = mocked_api_client_user_with_permissions(
            MAASResourceEntitlement.CAN_VIEW_GLOBAL_ENTITIES,
        )
        services_mock.switches = Mock(SwitchesService)
        services_mock.switches.list.return_value = ListResult[Switch](
            items=[TEST_SWITCH], total=2
        )
        response = await client.get(f"{self.BASE_PATH}?size=1")
        assert response.status_code == 200
        body = SwitchListResponse(**response.json())
        assert body.next == f"{self.BASE_PATH}?page=2&size=1"

    async def test_get(
        self,
        services_mock: ServiceCollectionV3,
        mocked_api_client_user_with_permissions: Callable[..., AsyncClient],
    ) -> None:
        client = mocked_api_client_user_with_permissions(
            MAASResourceEntitlement.CAN_VIEW_GLOBAL_ENTITIES,
        )
        services_mock.switches = Mock(SwitchesService)
        services_mock.switches.get_by_id.return_value = TEST_SWITCH
        response = await client.get(f"{self.BASE_PATH}/{TEST_SWITCH.id}")
        assert response.status_code == 200
        assert len(response.headers["ETag"]) > 0
        switch_response = SwitchResponse(**response.json())
        assert switch_response.id == TEST_SWITCH.id

    async def test_get_404(
        self,
        services_mock: ServiceCollectionV3,
        mocked_api_client_user_with_permissions: Callable[..., AsyncClient],
    ) -> None:
        client = mocked_api_client_user_with_permissions(
            MAASResourceEntitlement.CAN_VIEW_GLOBAL_ENTITIES,
        )
        services_mock.switches = Mock(SwitchesService)
        services_mock.switches.get_by_id.return_value = None
        response = await client.get(f"{self.BASE_PATH}/999")
        assert response.status_code == 404

    async def test_delete(
        self,
        services_mock: ServiceCollectionV3,
        mocked_api_client_user_with_permissions: Callable[..., AsyncClient],
    ) -> None:
        client = mocked_api_client_user_with_permissions(
            MAASResourceEntitlement.CAN_EDIT_GLOBAL_ENTITIES,
        )
        services_mock.switches = Mock(SwitchesService)
        services_mock.switches.delete_by_id.return_value = None
        response = await client.delete(f"{self.BASE_PATH}/1")
        assert response.status_code == 204

    async def test_create(
        self,
        services_mock: ServiceCollectionV3,
        mocked_api_client_user_with_permissions: Callable[
            ..., AsyncClient
        ],
    ) -> None:
        client = mocked_api_client_user_with_permissions(
            MAASResourceEntitlement.CAN_EDIT_GLOBAL_ENTITIES,
        )
        services_mock.switches = Mock(SwitchesService)
        services_mock.switches.create_new_switch_and_interface = (
            AsyncMock(return_value=TEST_SWITCH)
        )
        services_mock.interfaces = Mock()
        services_mock.interfaces.get_interfaces_for_mac = (
            AsyncMock(return_value=[])
        )

        response = await client.post(
            self.BASE_PATH,
            json={
                "mac_address": "00:11:22:33:44:55",
                "ztp_enabled": True,
            },
        )
        assert response.status_code == 201
        body = SwitchResponse(**response.json())
        assert body.id == TEST_SWITCH.id

    async def test_create_conflict(
        self,
        services_mock: ServiceCollectionV3,
        mocked_api_client_user_with_permissions: Callable[
            ..., AsyncClient
        ],
    ) -> None:
        client = mocked_api_client_user_with_permissions(
            MAASResourceEntitlement.CAN_EDIT_GLOBAL_ENTITIES,
        )
        existing_iface = Mock(switch_id=99)
        services_mock.interfaces = Mock()
        services_mock.interfaces.get_interfaces_for_mac = (
            AsyncMock(return_value=[existing_iface])
        )

        response = await client.post(
            self.BASE_PATH,
            json={"mac_address": "00:11:22:33:44:55"},
        )
        assert response.status_code == 409

    async def test_update(
        self,
        services_mock: ServiceCollectionV3,
        mocked_api_client_user_with_permissions: Callable[
            ..., AsyncClient
        ],
    ) -> None:
        client = mocked_api_client_user_with_permissions(
            MAASResourceEntitlement.CAN_EDIT_GLOBAL_ENTITIES,
        )
        services_mock.switches = Mock(SwitchesService)
        services_mock.switches.update_by_id = AsyncMock(
            return_value=TEST_SWITCH
        )

        response = await client.patch(
            f"{self.BASE_PATH}/{TEST_SWITCH.id}",
            json={"ztp_enabled": False},
        )
        assert response.status_code == 200
        body = SwitchResponse(**response.json())
        assert body.id == TEST_SWITCH.id

    async def test_serve_ztp_script(
        self,
        services_mock: ServiceCollectionV3,
        mocked_api_client_user_with_permissions: Callable[..., AsyncClient],
    ) -> None:
        client = mocked_api_client_user_with_permissions(
            MAASResourceEntitlement.CAN_VIEW_GLOBAL_ENTITIES,
        )
        services_mock.switches = Mock(SwitchesService)
        services_mock.switches.serve_ztp_script = AsyncMock(
            return_value=(b"#!/bin/sh\necho ok", TEST_SWITCH)
        )
        response = await client.get(
            f"{self.BASE_PATH}/ztp-script?token=ztp-tok"
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith(
            "text/x-shellscript"
        )
        assert b"echo ok" in response.content

    async def test_serve_ztp_script_not_found(
        self,
        services_mock: ServiceCollectionV3,
        mocked_api_client_user_with_permissions: Callable[..., AsyncClient],
    ) -> None:
        client = mocked_api_client_user_with_permissions(
            MAASResourceEntitlement.CAN_VIEW_GLOBAL_ENTITIES,
        )
        services_mock.switches = Mock(SwitchesService)
        services_mock.switches.serve_ztp_script = AsyncMock(
            side_effect=NotFoundException()
        )
        response = await client.get(
            f"{self.BASE_PATH}/ztp-script?token=bad"
        )
        assert response.status_code == 404

    async def test_serve_ztp_script_bad_template(
        self,
        services_mock: ServiceCollectionV3,
        mocked_api_client_user_with_permissions: Callable[..., AsyncClient],
    ) -> None:
        client = mocked_api_client_user_with_permissions(
            MAASResourceEntitlement.CAN_VIEW_GLOBAL_ENTITIES,
        )
        services_mock.switches = Mock(SwitchesService)
        services_mock.switches.serve_ztp_script = AsyncMock(
            side_effect=ValueError("Template render failed: ...")
        )
        response = await client.get(
            f"{self.BASE_PATH}/ztp-script?token=tok"
        )
        assert response.status_code == 400
