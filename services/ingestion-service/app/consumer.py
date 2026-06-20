"""Kafka consumer worker.

Runs as a separate process (``python -m app.consumer``) from the same image as
the ingestion service. It reads raw logs off the topic, scores them via the AI
service, and persists them — reusing ``persist_log`` so streamed and synchronous
logs are handled identically.
"""

import asyncio
import json
import logging

from .ai_client import get_ai_client
from .config import settings
from .database import SessionLocal, init_db
from .models import Log
from .schemas import LogCreate
from .service import persist_log

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("log-consumer")


async def process_record(data: dict, session, ai) -> Log:
    """Validate one raw record and persist the scored log."""
    log = LogCreate(**data)
    return await persist_log(session, log, ai)


async def run() -> None:
    from aiokafka import AIOKafkaConsumer

    await init_db()
    ai = get_ai_client()
    consumer = AIOKafkaConsumer(
        settings.kafka_topic,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=settings.kafka_consumer_group,
        value_deserializer=lambda b: json.loads(b.decode("utf-8")),
        auto_offset_reset="earliest",
    )
    await consumer.start()
    logger.info("Consuming %s from %s", settings.kafka_topic, settings.kafka_bootstrap_servers)
    try:
        async for message in consumer:
            try:
                async with SessionLocal() as session:
                    record = await process_record(message.value, session, ai)
                logger.info("Stored streamed log #%s (%s)", record.id, record.status)
            except Exception:  # pragma: no cover - keep the worker alive
                logger.exception("Failed to process message")
    finally:
        await consumer.stop()


if __name__ == "__main__":
    asyncio.run(run())
