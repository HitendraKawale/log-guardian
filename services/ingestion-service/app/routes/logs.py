from fastapi import APIRouter
from app.schemas import LogCreate

router = APIRouter(prefix="/logs", tags=["logs"])

@router.post("/")
async def ingest_log(log: LogCreate):
    return {"message": "Log received"}