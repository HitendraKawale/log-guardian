"""AI analysis service.

Exposes a single ``/analyze`` endpoint that scores a log entry for anomalies,
plus health and Prometheus metrics endpoints.
"""
from fastapi import FastAPI
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

from .analyzer import active_analyzer, analyze
from .schemas import AnalyzeRequest, AnalyzeResponse

app = FastAPI(title="Log Guardian AI Service", version="0.1.0")

ANALYZE_REQUESTS = Counter(
    "ai_analyze_requests_total", "Total number of analyze requests"
)
ANOMALIES_DETECTED = Counter(
    "ai_anomalies_detected_total", "Total number of logs flagged as anomalies"
)
ANOMALY_SCORE = Histogram(
    "ai_anomaly_score", "Distribution of anomaly scores returned by the model"
)


@app.get("/health", tags=["Health"])
def health_check() -> dict[str, str]:
    return {"status": "ok", "analyzer": active_analyzer.name}


@app.get("/metrics", tags=["Monitoring"])
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/analyze", response_model=AnalyzeResponse, tags=["Analysis"])
def analyze_log(request: AnalyzeRequest) -> AnalyzeResponse:
    ANALYZE_REQUESTS.inc()
    result = analyze(request)
    ANOMALY_SCORE.observe(result.anomaly_score)
    if result.is_anomaly:
        ANOMALIES_DETECTED.inc()
    return result
