# Copyright 2026 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from __future__ import annotations

from typing import Any, Mapping

from jinja2 import StrictUndefined
from jinja2.sandbox import SandboxedEnvironment


def render_ztp_script_template(
    template: str, values: Mapping[str, Any]
) -> str:
    """Render an operator-uploaded Jinja template with *values* from secrets.

    Uses a sandboxed environment and undefined variables raise on render.
    """
    env = SandboxedEnvironment(
        undefined=StrictUndefined,
        autoescape=False,
    )
    try:
        jinja_template = env.from_string(template)
    except Exception as e:
        raise ValueError(f"Invalid Jinja template: {e}") from e
    try:
        return jinja_template.render(**dict(values))
    except Exception as e:
        raise ValueError(f"Template render failed: {e}") from e
