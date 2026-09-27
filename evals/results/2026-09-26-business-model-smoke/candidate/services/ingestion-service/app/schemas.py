"""Pydantic request/response schemas."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class LogCreate(BaseModel):
    service: str = Field(..., examples=["payment-api"])
    level: LogLevel
    message: str = Field(..., examples=["Database connection failed."])
    timestamp: datetime


class AIResponse(BaseModel):
    """Response contract returned by the AI service's /analyze endpoint."""

    anomaly_score: float = Field(..., ge=0.0, le=1.0)
    is_anomaly: bool
    predicted_severity: Severity


class LogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    service: str
    level: LogLevel
    message: str
    timestamp: datetime
    status: str
    anomaly_score: float | None = None
    is_anomaly: bool | None = None
    predicted_severity: Severity | None = None
    true_label: bool | None = None


class FeedbackCreate(BaseModel):
    """Human-supplied ground truth for a log."""

    is_anomaly: bool


class LabeledLog(BaseModel):
    """A training example exported from human feedback."""

    model_config = ConfigDict(from_attributes=True)

    service: str
    level: LogLevel
    message: str
    timestamp: datetime
    true_label: bool
