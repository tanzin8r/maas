# Copyright 2026 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

import aiofiles
from fastapi import Depends, Query, Request, Response
from fastapi.responses import StreamingResponse

from maasapiserver.common.api.base import Handler, handler
from maasapiserver.common.api.models.responses.errors import (
    NotFoundBodyResponse,
)
from maasapiserver.v3.api import services
from maascommon.enums.boot_resources import BootResourceFileType
from maascommon.fields import normalise_macaddress
from maasservicelayer.db.filters import QuerySpec
from maasservicelayer.db.repositories.bootresourcefiles import (
    BootResourceFileClauseFactory,
)
from maasservicelayer.exceptions.catalog import NotFoundException
from maasservicelayer.models.bootresourcefiles import BootResourceFile
from maasservicelayer.services import ServiceCollectionV3
from maasservicelayer.utils.image_local_files import AsyncLocalBootResourceFile

TAGS = ["NOS"]

_CHUNK = 4 * 1024 * 1024

_INSTALLER_FILE_TYPES = (
    BootResourceFileType.SELF_EXTRACTING,
    BootResourceFileType.ROOT_TXZ,
    BootResourceFileType.ROOT_TGZ,
    BootResourceFileType.ROOT_TBZ,
    BootResourceFileType.ROOT_DD,
)


def _maas_public_base(request: Request) -> str:
    host = request.headers.get(
        "x-forwarded-host", request.headers.get("host", "localhost:5248")
    )
    scheme = request.headers.get("x-forwarded-proto", "http")
    return f"{scheme}://{host}/MAAS"


def _v3_base(maas_base: str) -> str:
    return f"{maas_base}/a/v3"


async def _pick_installer_file(
    services: ServiceCollectionV3, boot_resource_id: int
) -> BootResourceFile:
    rset = await services.boot_resource_sets.get_latest_complete_set_for_boot_resource(
        boot_resource_id
    )
    if rset is None:
        raise NotFoundException()

    files = await services.boot_resource_files.get_many(
        query=QuerySpec(
            where=BootResourceFileClauseFactory.with_resource_set_id(
                rset.id
            )
        )
    )
    for ft in _INSTALLER_FILE_TYPES:
        for f in files:
            if f.filetype == ft:
                return f
    if not files:
        raise NotFoundException()
    return files[0]


async def _stream_boot_file(file: BootResourceFile):
    lfile = AsyncLocalBootResourceFile(
        sha256=file.sha256,
        filename_on_disk=file.filename_on_disk,
        total_size=file.size,
    )
    if not await lfile.complete():
        raise NotFoundException()

    async with aiofiles.open(lfile.path, "rb") as stream:
        while chunk := await stream.read(_CHUNK):
            yield chunk


class NosHandler(Handler):
    @handler(
        path="/nos-installer",
        methods=["GET"],
        tags=TAGS,
        responses={200: {}, 404: {"model": NotFoundBodyResponse}},
        status_code=200,
    )
    async def get_nos_installer(
        self,
        request: Request,
        mac: str = Query(..., description="ONIE discovery MAC of the switch."),
        services: ServiceCollectionV3 = Depends(services),  # noqa: B008
    ) -> Response:
        mac_norm = normalise_macaddress(mac)
        result = await services.switches.check_installer_for_switch(mac_norm)
        if result is None:
            raise NotFoundException()

        switch, _image_id = result
        if not switch.nos_install_callback_token:
            raise NotFoundException()

        maas_base = _maas_public_base(request)
        api = _v3_base(maas_base)
        token = switch.nos_install_callback_token
        script = f"""#!/bin/sh
MAAS_BASE="{maas_base}"
API="{api}"
TOKEN="{token}"
MAC="{mac_norm}"

wget -q -O /tmp/nos-installer "${{API}}/nos-installer-binary?mac=$MAC&token=$TOKEN"
chmod +x /tmp/nos-installer
exec /tmp/nos-installer
"""
        return Response(
            content=script.encode("utf-8"),
            media_type="text/x-shellscript",
        )

    @handler(
        path="/nos-installer-binary",
        methods=["GET"],
        tags=TAGS,
        responses={200: {}, 404: {"model": NotFoundBodyResponse}},
        status_code=200,
    )
    async def get_nos_installer_binary(
        self,
        mac: str = Query(...),
        token: str = Query(...),
        services: ServiceCollectionV3 = Depends(services),  # noqa: B008
    ) -> StreamingResponse:
        mac_norm = normalise_macaddress(mac)
        switch = await services.switches.get_switch_by_mac_address(mac_norm)
        if (
            switch is None
            or switch.nos_install_callback_token != token
            or not switch.target_image_id
        ):
            raise NotFoundException()

        bfile = await _pick_installer_file(services, switch.target_image_id)

        async def body():
            async for chunk in _stream_boot_file(bfile):
                yield chunk

        return StreamingResponse(
            body(),
            media_type="application/octet-stream",
            headers={"Content-Length": str(bfile.size)},
        )
