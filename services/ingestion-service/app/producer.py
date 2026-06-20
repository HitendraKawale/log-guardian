"""Kafka producer for the optional streaming ingestion path.

The producer is a module-level singleton started/stopped with the app lifespan.
When Kafka is disabled it stays ``None`` and ``publish_log`` is never reached
(the route guards on ``settings.kafka_enabled``).
"""

import logging

from .config import settings
from .schemas import LogCreate

logger = logging.getLogger(__name__)

_producer = None


async def start_producer() -> None:
    global _producer
    if not settings.kafka_enabled:
        return
    from aiokafka import AIOKafkaProducer

    _producer = AIOKafkaProducer(bootstrap_servers=settings.kafka_bootstrap_servers)
    await _producer.start()
    logger.info("Kafka producer started -> %s", settings.kafka_bootstrap_servers)


async def stop_producer() -> None:
    global _producer
    if _producer is not None:
        await _producer.stop()
        _producer = None


async def publish_log(log: LogCreate) -> None:
    if _producer is None:
        raise RuntimeError("Kafka producer is not running")
    await _producer.send_and_wait(settings.kafka_topic, log.model_dump_json().encode("utf-8"))
