# Copyright 2026 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from dataclasses import dataclass

VERIFY_SWITCH_ZTP_WORKFLOW_NAME = "verify-switch-ztp"


@dataclass(frozen=True)
class VerifySwitchZtpParam:
    switch_id: int
