"""
Regression guard: DM URL query tokens must not be hand-assembled outside ``dm_links``.

Uses AST so Hyros prefix tuples and keyword args like ``attora_sub=...`` in model
constructors are not confused with URL string construction.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_APP_DIR = _BACKEND_ROOT / "app"

_ALLOW_UTM_MEDIUM_DM_FILES = frozenset(
    {
        _APP_DIR / "utils" / "dm_links.py",
    }
)


def _py_files() -> list[Path]:
    return [p for p in _APP_DIR.rglob("*.py") if p.is_file()]


def _string_constants(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            out.append(node.value)
        # Python 3.7 compatibility not required; skip JoinedStr pieces handled via Constant children
    return out


@pytest.mark.parametrize("path", _py_files(), ids=lambda p: str(p.relative_to(_BACKEND_ROOT)))
def test_no_handrolled_utm_medium_dm_string_outside_dm_links(path: Path) -> None:
    if path in _ALLOW_UTM_MEDIUM_DM_FILES:
        return
    joined = "".join(_string_constants(path))
    assert "utm_medium=dm" not in joined, (
        f"{path.relative_to(_BACKEND_ROOT)} embeds literal utm_medium=dm; use app.utils.dm_links.build_dm_link"
    )