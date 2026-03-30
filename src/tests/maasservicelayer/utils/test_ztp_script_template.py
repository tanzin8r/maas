# Copyright 2026 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

import pytest

from maasservicelayer.utils.ztp_script_template import render_ztp_script_template


def test_render_substitutes_jinja_variables():
    out = render_ztp_script_template(
        "u={{ admin_user }} k={{ ssh_key_root }}",
        {"admin_user": "a", "ssh_key_root": "ssh-rsa AAAA"},
    )
    assert out == "u=a k=ssh-rsa AAAA"


def test_render_unknown_jinja_variable_raises():
    with pytest.raises(ValueError, match="Template render failed"):
        render_ztp_script_template("{{ not_defined }}", {})


def test_render_missing_key_raises():
    with pytest.raises(ValueError, match="Template render failed"):
        render_ztp_script_template("x={{ admin_user }}", {})


def test_render_invalid_syntax_raises():
    with pytest.raises(ValueError, match="Invalid Jinja template"):
        render_ztp_script_template("{% unclosed", {})
