"""Contract artifact catalog: versioned catalog schema and its pure model.

The catalog document model lives in `coherence.contracts.model`. Catalog *file*
discovery and lexical path safety are a later task's concern.
"""

from __future__ import annotations

from coherence.contracts.model import (
    CONTRACT_KINDS,
    CONTRACT_STATUSES,
    RELATION_KINDS,
    ContractClosure,
    ContractDeclaration,
    ContractDiagnostic,
    ContractRelation,
)

__all__ = [
    "CONTRACT_KINDS",
    "CONTRACT_STATUSES",
    "RELATION_KINDS",
    "ContractClosure",
    "ContractDeclaration",
    "ContractDiagnostic",
    "ContractRelation",
]
