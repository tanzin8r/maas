# Copyright 2026 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

import asyncio
from datetime import datetime, timedelta, timezone

import structlog
from temporalio import workflow
from temporalio.common import RetryPolicy

from maascommon.workflows.switch_ztp import (
    VERIFY_SWITCH_ZTP_WORKFLOW_NAME,
    VerifySwitchZtpParam,
)
from maasservicelayer.builders.switches import SwitchBuilder
from maasservicelayer.models.secrets import SwitchZtpCredentialsSecret
from maastemporalworker.workflow.activity import ActivityBase
from maastemporalworker.workflow.utils import (
    activity_defn_with_context,
    workflow_run_with_context,
)

logger = structlog.getLogger()

VERIFY_SWITCH_ZTP_SSH_ACTIVITY_NAME = "verify-switch-ztp-ssh"
POLL_INTERVAL = timedelta(seconds=30)
MAX_POLL_ATTEMPTS = 20
SSH_ACTIVITY_TIMEOUT = timedelta(seconds=90)


def _try_ssh_password(host: str, username: str, password: str) -> bool:
    import paramiko

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            hostname=host,
            username=username,
            password=password,
            timeout=20,
            banner_timeout=20,
            auth_timeout=20,
            allow_agent=False,
            look_for_keys=False,
        )
        client.close()
        return True
    except Exception:
        return False


@workflow.defn(name=VERIFY_SWITCH_ZTP_WORKFLOW_NAME, sandboxed=False)
class VerifySwitchZtpWorkflow:
    """Poll SSH until switch accepts admin credentials or attempts exhaust."""

    @workflow_run_with_context
    async def run(self, param: VerifySwitchZtpParam) -> bool:
        for attempt in range(MAX_POLL_ATTEMPTS):
            ok = await workflow.execute_activity(
                VERIFY_SWITCH_ZTP_SSH_ACTIVITY_NAME,
                arg=param,
                start_to_close_timeout=SSH_ACTIVITY_TIMEOUT,
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
            if ok:
                logger.info(
                    "switch ZTP SSH verification succeeded",
                    switch_id=param.switch_id,
                    attempt=attempt + 1,
                )
                return True
            await workflow.sleep(POLL_INTERVAL)
        logger.warning(
            "switch ZTP SSH verification timed out",
            switch_id=param.switch_id,
            attempts=MAX_POLL_ATTEMPTS,
        )
        return False


class SwitchZtpActivity(ActivityBase):
    @activity_defn_with_context(name=VERIFY_SWITCH_ZTP_SSH_ACTIVITY_NAME)
    async def verify_switch_ztp_ssh(self, param: VerifySwitchZtpParam) -> bool:
        async with self.start_transaction() as services:
            switch = await services.switches.get_by_id(param.switch_id)
            if not switch:
                return False
            if switch.ztp_completed_at:
                return True

            model = SwitchZtpCredentialsSecret(id=param.switch_id)
            secret = await services.secrets.get_composite_secret(
                model, default={}
            )

            host = secret.get("provisioning_ssh_host")
            user = secret.get("admin_user")
            password = secret.get("admin_password")
            if not host or not user or not password:
                return False

            ok = await asyncio.to_thread(
                _try_ssh_password, str(host), str(user), str(password)
            )
            if ok:
                now = datetime.now(timezone.utc)
                await services.switches.update_by_id(
                    param.switch_id,
                    SwitchBuilder(ztp_completed_at=now),
                )
            return ok
