"""Control location helpers built on pywinauto's uia backend.

Section 3 (ui_automation). Locate controls by control type, accessible
name or label, UI hierarchy and container, and relationships to
surrounding controls. Never locate by screen coordinates.

No pywinauto import here: `parent` is whatever pywinauto object (a
WindowSpecification/UIAWrapper) the caller already holds, and only its
documented `children()` method is used below. This keeps this module (and
its tests) importable on macOS/Linux, unlike ui_automation.app.
"""

from __future__ import annotations

from typing import Any

from fakturama_automation.ui_automation import waits
from fakturama_automation.ui_automation.exceptions import AmbiguousControlError, ControlNotFoundError


def find_control(
    parent: Any,
    control_type: str,
    name: str | None = None,
    timeout_seconds: float = 5.0,
) -> Any:
    """Locate a single control under parent, retrying within timeout_seconds.

    Ambiguity (more than one match) is raised as soon as it's seen, without
    waiting out the rest of the timeout: it reflects the current
    parent/context, not a timing race, so resolving it means the caller
    passing a more specific parent (see Doc/Design.md's control discovery
    section), not retrying the same search.
    """
    matches: list[Any] = []

    def _has_any_match() -> bool:
        nonlocal matches
        matches = find_all_controls(parent, control_type, name)
        return len(matches) >= 1

    if not waits.wait_until(_has_any_match, timeout_seconds=timeout_seconds):
        raise ControlNotFoundError(
            f"no {control_type} control named {name!r} found within {timeout_seconds}s"
        )
    if len(matches) > 1:
        raise AmbiguousControlError(
            f"{len(matches)} {control_type} controls named {name!r} matched; expected exactly one"
        )
    return matches[0]


def find_all_controls(
    parent: Any,
    control_type: str,
    name: str | None = None,
) -> list[Any]:
    """Locate every matching control under parent, no retry."""
    kwargs: dict[str, Any] = {"control_type": control_type}
    if name is not None:
        kwargs["title"] = name
    return parent.children(**kwargs)
