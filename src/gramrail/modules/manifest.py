"""Explicit, inspectable module requirements; this is not a code sandbox."""
from dataclasses import dataclass

from ..errors import InvalidInput


@dataclass(frozen=True)
class Module:
    name: str
    description: str
    requires: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ()


MODULES = {
    "forms": Module("forms", "Saved multi-step questions, validation, back and cancel.", capabilities=("database",)),
    "approvals": Module("approvals", "Review completed forms through authorized Telegram buttons.", requires=("forms",), capabilities=("database", "delivery")),
}


def resolve(names: list[str]) -> list[Module]:
    found: list[Module] = []
    visited: set[str] = set()
    active: set[str] = set()

    def visit(name: str) -> None:
        if name in active:
            raise InvalidInput("Cyclic module requirements.")
        if name in visited:
            return
        if name not in MODULES:
            raise InvalidInput(f"Unknown module '{name}'. Available: {', '.join(MODULES)}.")
        active.add(name)
        for dependency in MODULES[name].requires:
            visit(dependency)
        active.remove(name)
        visited.add(name)
        found.append(MODULES[name])
    for name in names:
        visit(name)
    return found
