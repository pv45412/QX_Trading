"""Universal Publication State Control Module for QX Platform."""

from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class PublicationState(str, Enum):
    """Publication and execution eligibility state across all QX components."""
    VERIFIED = "VERIFIED"          # Verified live market evidence; publication and execution eligible
    RESEARCH_ONLY = "RESEARCH_ONLY"# Research analysis model; non-executable
    SIMULATED = "SIMULATED"        # Simulated / demo / prototype model; non-executable
    BLOCKED = "BLOCKED"            # Stale or unverified evidence; publication & execution blocked


class PublicationMetadata(BaseModel):
    """Publication metadata contract for API responses and dashboard models."""
    state: PublicationState = PublicationState.SIMULATED
    executable: bool = False
    evidence_reason: str = "Prototype payload / simulated execution mode"
    published_at: str = Field(default_factory=lambda: "")

    def to_dict(self) -> dict[str, Any]:
        """Serialize metadata into a dict suitable for JSON payloads."""
        return {
            "publication_state": self.state.value,
            "executable": self.executable,
            "evidence_reason": self.evidence_reason,
            "published_at": self.published_at,
        }

    def is_eligible_for_execution(self) -> tuple[bool, str]:
        """Check whether payload is eligible for live order execution."""
        if self.state != PublicationState.VERIFIED or not self.executable:
            return False, (
                f"Trade object is non-executable (publication_state='{self.state.value}', executable={self.executable}). "
                f"Reason: {self.evidence_reason}. Only VERIFIED trade objects with executable=True can become executable order proposals."
            )
        return True, ""

