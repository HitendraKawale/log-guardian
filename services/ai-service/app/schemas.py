"""Request/response contracts for the AI analysis service.

The ``AnalyzeRequest`` shape is intentionally identical to the ingestion
service's ``LogCreate`` payload so the two services share one wire contract.
"""
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


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


class AnalyzeRequest(BaseModel):
    service: str = Field(..., examples=["payment-api"])
    level: LogLevel
    message: str = Field(..., examples=["Database connection failed."])
    timestamp: datetime


class AnalyzeResponse(BaseModel):
    anomaly_score: float = Field(..., ge=0.0, le=1.0)
    is_anomaly: bool
    predicted_severity: Severity
