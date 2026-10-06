"""PersonaService — explicit portable persona runtime (PRES-053).

Public surface: PersonaContext, PersonaService, PersonaReceipt,
packaged catalog, explicit adapters, per-phase policy, bundle verify.
"""
from .adapters import (
    CredentialResolver,
    EnvCredentialResolver,
    FileStorage,
    HeuristicScoring,
    NeutralScoring,
    NullCredentialResolver,
    NullStorage,
    ScoringAdapter,
    StorageAdapter,
)
from .bundle import (
    PersonaReceipt,
    required_texts_for_receipt,
    verify_bundle_integrity,
    verify_consumption,
)
from .catalog import PackagedCatalog
from .context import PersonaContext, content_hash
from .policy import NARRATIVE_PHASE_FOR, policy_for_phase
from .service import PersonaService, PersonaServiceError

__all__ = [
    "PersonaContext",
    "PersonaService",
    "PersonaServiceError",
    "PersonaReceipt",
    "PackagedCatalog",
    "StorageAdapter",
    "FileStorage",
    "NullStorage",
    "CredentialResolver",
    "EnvCredentialResolver",
    "NullCredentialResolver",
    "ScoringAdapter",
    "HeuristicScoring",
    "NeutralScoring",
    "policy_for_phase",
    "NARRATIVE_PHASE_FOR",
    "content_hash",
    "verify_bundle_integrity",
    "verify_consumption",
    "required_texts_for_receipt",
]
