"""Ambassador Agent pattern: one accountable, autonomous agent per external-system boundary."""
from .ambassador import Admission, Ambassador, BoundaryContext, Resilience
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
    Reasoner,
    Sanitizer,
    Subscriber,
    TransientError,
)

__all__ = [
    "ActionRequest", "ActionResult", "Admission", "Advice", "Ambassador", "AmbassadorSpec",
    "BoundaryContext", "BoundaryError", "Capability", "Compensation", "Connector", "CredentialBroker",
    "ExternalEvent", "Fallback", "Intelligence", "Journal", "Notice", "Outcome", "PermanentError",
    "Policy", "Principal", "Reasoner", "Resilience", "Sanitizer", "Subscriber", "TransientError", "Unknown",
]
