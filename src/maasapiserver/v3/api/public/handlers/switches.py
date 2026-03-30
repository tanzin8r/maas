# Copyright 2026 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from typing import Union

from fastapi import Depends, Query, Response
from fastapi.responses import StreamingResponse
from starlette import status

from maasapiserver.common.api.base import Handler, handler
from maasapiserver.common.api.models.responses.errors import (
    BadRequestBodyResponse,
    ConflictBodyResponse,
    NotFoundBodyResponse,
)
from maasapiserver.v3.api import services
from maasapiserver.v3.api.public.models.requests.query import PaginationParams
from maasapiserver.v3.api.public.models.requests.switches import (
    SwitchRequest,
    SwitchUpdateRequest,
)
from maasapiserver.v3.api.public.models.responses.base import (
    OPENAPI_ETAG_HEADER,
)
from maasapiserver.v3.api.public.models.responses.switches import (
    SwitchListResponse,
    SwitchResponse,
)
from maasapiserver.v3.auth.base import check_permissions
from maasapiserver.v3.constants import V3_API_PREFIX
from maascommon.openfga.base import MAASResourceEntitlement
from maasservicelayer.exceptions.catalog import (
    BadRequestException,
    BaseExceptionDetail,
    ConflictException,
    NotFoundException,
)
from maasservicelayer.exceptions.constants import (
    INVALID_ARGUMENT_VIOLATION_TYPE,
)
from maasservicelayer.services import ServiceCollectionV3

TAGS = ["Switches"]


class SwitchesHandler(Handler):
    """Switches API handler."""

    @handler(
        path="/switches",
        methods=["GET"],
        tags=TAGS,
        responses={200: {"model": SwitchListResponse}},
        response_model_exclude_none=True,
        status_code=200,
        dependencies=[
            Depends(
                check_permissions(
                    openfga_permission=MAASResourceEntitlement.CAN_VIEW_GLOBAL_ENTITIES
                )
            )
        ],
    )
    async def list_switches(
        self,
        pagination_params: PaginationParams = Depends(),  # noqa: B008
        services: ServiceCollectionV3 = Depends(services),  # noqa: B008
    ) -> SwitchListResponse:
        switches = await services.switches.list(
            page=pagination_params.page,
            size=pagination_params.size,
        )
        return SwitchListResponse(
            items=[
                await SwitchResponse.from_model(
                    switch=s,
                    self_base_hyperlink=f"{V3_API_PREFIX}/switches",
                )
                for s in switches.items
            ],
            total=switches.total,
            next=(
                f"{V3_API_PREFIX}/switches?"
                f"{pagination_params.to_next_href_format()}"
                if switches.has_next(
                    pagination_params.page, pagination_params.size
                )
                else None
            ),
        )

    @handler(
        path="/switches/{switch_id}",
        methods=["GET"],
        tags=TAGS,
        responses={
            200: {
                "model": SwitchResponse,
                "headers": {"ETag": OPENAPI_ETAG_HEADER},
            },
            404: {"model": NotFoundBodyResponse},
        },
        response_model_exclude_none=True,
        status_code=200,
        dependencies=[
            Depends(
                check_permissions(
                    openfga_permission=MAASResourceEntitlement.CAN_VIEW_GLOBAL_ENTITIES
                )
            )
        ],
    )
    async def get_switch(
        self,
        switch_id: int,
        response: Response,
        services: ServiceCollectionV3 = Depends(services),  # noqa: B008
    ) -> SwitchResponse:
        switch = await services.switches.get_by_id(switch_id)
        if not switch:
            raise NotFoundException()
        response.headers["ETag"] = switch.etag()
        return await SwitchResponse.from_model(
            switch=switch,
            self_base_hyperlink=f"{V3_API_PREFIX}/switches",
        )

    @handler(
        path="/switches",
        methods=["POST"],
        tags=TAGS,
        responses={
            201: {"model": SwitchResponse},
            400: {"model": BadRequestBodyResponse},
            409: {"model": ConflictBodyResponse},
        },
        response_model_exclude_none=True,
        status_code=201,
        dependencies=[
            Depends(
                check_permissions(
                    openfga_permission=MAASResourceEntitlement.CAN_EDIT_GLOBAL_ENTITIES
                )
            )
        ],
    )
    async def create_switch(
        self,
        switch_request: SwitchRequest,
        response: Response,
        services: ServiceCollectionV3 = Depends(services),  # noqa: B008
    ) -> SwitchResponse:
        existing = await services.interfaces.get_interfaces_for_mac(
            str(switch_request.mac_address)
        )
        if existing and any(iface.switch_id for iface in existing):
            raise ConflictException(
                details=[
                    BaseExceptionDetail(
                        type="InterfaceAlreadyAssigned",
                        message=(
                            f"An interface with MAC address "
                            f"'{switch_request.mac_address}' is already "
                            "assigned to another entity."
                        ),
                    )
                ]
            )

        switch = await services.switches.create_new_switch_and_interface(
            await switch_request.to_switch_builder(services),
            switch_request.mac_address,
        )
        if switch_request.ztp_credentials and switch.ztp_enabled:
            updates = switch_request.ztp_credentials.to_secret_updates()
            if updates:
                await services.switches.merge_switch_ztp_credentials(
                    switch.id, updates
                )
        response.headers["Location"] = f"{V3_API_PREFIX}/switches/{switch.id}"
        return await SwitchResponse.from_model(
            switch=switch,
            self_base_hyperlink=f"{V3_API_PREFIX}/switches",
        )

    @handler(
        path="/switches/{switch_id}",
        methods=["PATCH"],
        tags=TAGS,
        responses={
            200: {"model": SwitchResponse},
            404: {"model": NotFoundBodyResponse},
        },
        response_model_exclude_none=True,
        status_code=200,
        dependencies=[
            Depends(
                check_permissions(
                    openfga_permission=MAASResourceEntitlement.CAN_EDIT_GLOBAL_ENTITIES
                )
            )
        ],
    )
    async def update_switch(
        self,
        switch_id: int,
        switch_request: SwitchUpdateRequest,
        response: Response,
        services: ServiceCollectionV3 = Depends(services),  # noqa: B008
    ) -> SwitchResponse:
        switch = await services.switches.update_by_id(
            switch_id, await switch_request.to_switch_builder(services)
        )
        if switch_request.ztp_credentials is not None and switch.ztp_enabled:
            updates = switch_request.ztp_credentials.to_secret_updates()
            if updates:
                await services.switches.merge_switch_ztp_credentials(
                    switch.id, updates
                )
        return await SwitchResponse.from_model(
            switch=switch,
            self_base_hyperlink=f"{V3_API_PREFIX}/switches",
        )

    @handler(
        path="/switches/{switch_id}",
        methods=["DELETE"],
        tags=TAGS,
        responses={
            204: {},
            404: {"model": NotFoundBodyResponse},
        },
        status_code=204,
        dependencies=[
            Depends(
                check_permissions(
                    openfga_permission=MAASResourceEntitlement.CAN_EDIT_GLOBAL_ENTITIES
                )
            )
        ],
    )
    async def delete_switch(
        self,
        switch_id: int,
        etag_if_match: Union[str, None] = None,
        services: ServiceCollectionV3 = Depends(services),  # noqa: B008
    ) -> Response:
        await services.switches.delete_by_id(
            id=switch_id, etag_if_match=etag_if_match
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    # --- ZTP script serving (unauthenticated, token-validated) ---

    @handler(
        path="/switches/ztp-script",
        methods=["GET"],
        tags=TAGS,
        responses={
            200: {},
            400: {"model": BadRequestBodyResponse},
            404: {"model": NotFoundBodyResponse},
        },
        status_code=200,
    )
    async def serve_ztp_script(
        self,
        token: str = Query(...),
        services: ServiceCollectionV3 = Depends(services),  # noqa: B008
    ) -> Response:
        try:
            body, _switch = await services.switches.serve_ztp_script(token)
        except ValueError as e:
            raise BadRequestException(
                details=[
                    BaseExceptionDetail(
                        type=INVALID_ARGUMENT_VIOLATION_TYPE,
                        message=str(e),
                    )
                ]
            ) from e

        return StreamingResponse(
            iter([body]),
            media_type="text/x-shellscript",
            headers={"Content-Length": str(len(body))},
        )
