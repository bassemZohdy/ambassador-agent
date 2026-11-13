"""Ambassador Agent pattern: one accountable, autonomous agent per external-system boundary."""
from .ambassador import Admission, Ambassador, BoundaryContext, Resilience
from .defaults import HmacDelegations
from .durable import SqliteJournal
from .model import (
    ActionRequest,
    ActionResult,
    AmbassadorSpec,
    BoundaryError,
    Capability,
    Compensation,
    ExternalEvent,
    Fallback,
    Intelligence,
    Notice,
    Outcome,
    Principal,
    Unknown,
)
from .ports import (
    Advice,
    Connector,
    CredentialBroker,
    Journal,
    PermanentError,
    Policy,
    PrincipalVerifier,
    Reasoner,
    Sanitizer,
    Subscriber,
    TransientError,
)

__all__ = [
    "ActionRequest", "ActionResult", "Admission", "Advice", "Ambassador", "AmbassadorSpec",
    "BoundaryContext", "BoundaryError", "Capability", "Compensation", "Connector", "CredentialBroker",
    "ExternalEvent", "Fallback", "HmacDelegations", "Intelligence", "Journal", "Notice", "Outcome", "PermanentError",
    "Policy", "Principal", "PrincipalVerifier", "Reasoner", "Resilience", "Sanitizer", "SqliteJournal", "Subscriber", "TransientError", "Unknown",
]
