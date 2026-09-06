from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ResolvedEntity:
    identity: str
    created: bool
