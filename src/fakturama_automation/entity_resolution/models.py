"""Result type returned by every entity resolver.

See Doc/adr/0003-entity-resolution.md for why a named result type replaced
the original scaffold's bare Any, and Doc/adr/0010 for why `element` was
dropped once nothing read it.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ResolvedEntity:
    """What a resolver found or created.

    identity: the exact key that was matched or just created (company name,
    SKU, VAT percent as text, payment method name).
    created: True if no exact match existed and a new record was made,
    False if an existing one was matched. Attaching an order to a Debtor
    that was just invented is a different event from attaching it to one
    that was already on file, and the run log says which.
    """

    identity: str
    created: bool
