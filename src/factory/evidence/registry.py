from __future__ import annotations

from factory.evidence.types import Connector, EvidenceContext
from substrate.validators.schema import validate_against


class Registry:
    """Maps a check `kind` to a Connector and evaluates declared checks. Connector
    code is trusted; check `args` are untrusted agent data validated against each
    connector's `args_schema` before evaluation."""

    def __init__(self) -> None:
        self._by_kind: dict[str, Connector] = {}

    def register(self, connector: Connector) -> None:
        if connector.kind in self._by_kind:
            raise ValueError(f"connector already registered for kind: {connector.kind}")
        self._by_kind[connector.kind] = connector

    def get(self, kind: str) -> Connector | None:
        return self._by_kind.get(kind)

    def evaluate_checks(self, checks: list[dict], ctx: EvidenceContext) -> list[str]:
        """Return a list of error strings (empty = every check passed). Unknown
        kind, invalid args, a failed check, or a connector exception each yield an
        error; nothing here raises."""
        errors: list[str] = []
        for check in checks:
            name = check.get("name", "<unnamed>")
            kind = check.get("kind", "")
            args = check.get("args", {})
            connector = self._by_kind.get(kind)
            if connector is None:
                errors.append(f"check '{name}': unknown kind '{kind}'")
                continue
            arg_errors = validate_against(args, connector.args_schema)
            if arg_errors:
                errors.append(f"check '{name}': invalid args: {'; '.join(arg_errors)}")
                continue
            try:
                result = connector.evaluate(args, ctx)
            except Exception as exc:  # connector bug or unreadable input -> failed check
                errors.append(f"check '{name}': {kind} errored: {exc}")
                continue
            if not result.passed:
                errors.append(f"check '{name}' failed: {result.evidence}")
        return errors
