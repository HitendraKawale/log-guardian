from fastapi import FastAPI
from app.routes import logs

app = FastAPI(title="Log Guardian Ingestion Service")
app.include_router(logs.router)

@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "ok"}

@app.get("/readiness", tags=["Health"])
async def readiness_check():
    return {"status": "ready"}
