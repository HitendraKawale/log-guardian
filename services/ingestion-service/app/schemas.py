from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field

class LogLevel(str, Enum):
    DEBUG = 'DEBUG'
    INFO = 'INFO'
    WARNING = 'WARNING'
    ERROR = 'ERROR'
    CRITICAL = 'CRITICAL'

class LogCreate(BaseModel):
    service: str = Field(..., example="payment-api")
    level: LogLevel
    message: str = Field(..., example="Database connection failed.")
    timestamp: datetime

class AIResponse(BaseModel):
    anomaly_score: float
    is_anomaly: bool

class LogResponse(BaseModel):
    id: int
    service: str
    level: LogLevel
    message: str
    timestamp: datetime
    status: str
    anomaly_score: float | None = None
