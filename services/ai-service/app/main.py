from fastapi import FastAPI
from pydantic import BaseModel
import random

app = FastAPI()

class LogInput(BaseModel):
    service_name: str
    log_level: str
    message: str

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.post("/analyze")
async def analyze(log: LogInput):
    anomaly_score = random.random
    if anomaly_score > 0.8:
        severity = "high"
    elif anomaly_score > 0.5:
        severity = "medium"
    else:
        severity = "low"
    return {
        "anomaly_score": anomaly_score,
        predicted_severity": severity,
    }