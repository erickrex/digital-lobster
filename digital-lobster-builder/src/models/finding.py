import warnings
from enum import Enum

from pydantic import BaseModel, Field

# Pydantic v2 warns that 'construct' shadows BaseModel.model_construct.
# The field name is intentional per the design spec, so suppress the warning
# at import time before the class is defined.
warnings.filterwarnings(
    "ignore",
    message='Field name "construct" in "Finding"',
    category=UserWarning,
)


class FindingSeverity(str, Enum):
    """Severity levels for pipeline findings."""

    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class Finding(BaseModel):
    """A structured diagnostic produced when a pipeline stage encounters
    an unsupported, partially supported, or noteworthy construct."""

    severity: FindingSeverity
    stage: str = Field(min_length=1)
    construct: str = Field(min_length=1)
    message: str = Field(min_length=1)
    recommended_action: str = Field(min_length=1)
