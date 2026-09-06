from __future__ import annotations


class ControlNotFoundError(Exception):
    pass


class AmbiguousControlError(Exception):
    # Routed to error_handling rather than picked between arbitrarily;
    # resolving it means passing a more specific parent, not retrying.
    pass


class WindowFocusError(Exception):
    # Matters because every grid read here is a screen-region screenshot: an
    # occluded window is captured as whatever is on top of it, which reads as
    # a plausible - and completely wrong - grid rather than as an error.
    pass


class DialogTimeoutError(Exception):
    pass


class GridReadError(Exception):
    # Never degraded to an empty or partial row list: entity_resolution counts
    # those rows to decide between matching and creating, so a failed read
    # that looked like zero rows would create duplicates.
    pass


class GridGeometryError(Exception):
    # Measuring wrongly is worse than not measuring: a click at a
    # wrong-but-plausible coordinate types into the wrong cell exactly as
    # convincingly as into the right one.
    pass
