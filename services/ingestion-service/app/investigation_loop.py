"""Bounded read-only tool selection; ambiguous billing stops rather than retries."""

import asyncio
import hashlib
import time
from datetime import UTC, datetime
from decimal import Decimal

import openai
from openai.types.chat import ChatCompletion

from .investigation_agent import (
    MAX_EVIDENCE_BYTES,
    MAX_OUTPUT_TOKENS,
    PRICING,
    PROMPT,
    canonical,
    estimated_cost,
    read_usage,
    validate_citations,
)
from .investigation_schemas import (
    EvidenceBatch,
    InvestigationReport,
    InvestigationScope,
    LogQuery,
    RunbookQuery,
)
from .investigation_tools import MAX_RESULT_BYTES, redact

MAX_MODEL_REQUESTS = 6
MAX_TOOL_EXECUTIONS = 8
TOOL_SCHEMAS = {
    "query_logs": LogQuery,
    "summarize_logs": InvestigationScope,
    "search_runbooks": RunbookQuery,
}
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": TOOL_SCHEMAS[name].model_json_schema(),
        },
    }
    for name, description in (
        ("query_logs", "Read scoped logs; optionally filter a literal substring, at most 50 rows."),
        ("summarize_logs", "Count all scoped logs by service and level, not only a query page."),
        ("search_runbooks", "Search curated operational guidance; not incident evidence."),
    )
]
AGENT_PROMPT = PROMPT.replace(
    "Do not execute actions or request further tools.",
    "Use only the supplied read-only tools. Choose queries from observed evidence; "
    "never expand the authorized scope. Stop when evidence supports a narrow conclusion "
    "or is insufficient. Never repeat an identical tool query.",
)


async def run_agent(question, tools, client, config, *, dry_run=False):
    if not isinstance(question, str) or not question.strip() or len(question) > 2048:
        raise ValueError("Invalid question")
    started = time.monotonic()
    question = redact(question)
    response_format = {
        "type": "json_schema",
        "json_schema": {
            "name": "investigation_report",
            "strict": True,
            "schema": InvestigationReport.model_json_schema(),
        },
    }
    result = {
        "schema_version": 1,
        "system": "C",
        "mode": config.mode,
        "started_at": datetime.now(UTC).isoformat(),
        "question": question,
        "model_requested": config.model,
        "model_returned": None,
        "sdk_version": openai.__version__,
        "prompt_sha256": hashlib.sha256(
            (AGENT_PROMPT + canonical(response_format) + canonical(TOOLS)).encode()
        ).hexdigest(),
        "parameters": {
            "temperature": 0,
            "max_completion_tokens": MAX_OUTPUT_TOKENS,
            "store": False,
            "max_retries": 0,
        },
        "status": "failed",
        "error": None,
        "report": None,
        "trace": [],
        "model_requests": 0,
        "tool_executions": 0,
        "model_calls": [],
        "cache_usage_complete": True,
        "usage": {"input_tokens": 0, "output_tokens": 0, "cached_input_tokens": 0},
        "estimated_cost_usd": "0.00000000",
        "pricing": dict(PRICING),
        "limits": {
            "max_cost_usd": str(config.max_cost_usd),
            "deadline_seconds": config.deadline_seconds,
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "max_evidence_bytes": MAX_EVIDENCE_BYTES,
            "max_model_requests": MAX_MODEL_REQUESTS,
            "max_tool_executions": MAX_TOOL_EXECUTIONS,
        },
    }
    messages = [
        {"role": "system", "content": AGENT_PROMPT},
        {
            "role": "user",
            "content": canonical(
                {
                    "question": question,
                    "scope": redact(tools.scope.model_dump(mode="json")),
                }
            ),
        },
    ]
    batches, seen = [], set()
    evidence_bytes = 0
    known_usage = dict(result["usage"])
    try:
        async with asyncio.timeout(config.deadline_seconds):
            for _ in range(MAX_MODEL_REQUESTS):
                input_bound = (
                    len(canonical(messages).encode())
                    + len(canonical(response_format).encode())
                    + len(canonical(TOOLS).encode())
                    + 4096
                )
                reservation = estimated_cost(
                    {
                        "input_tokens": input_bound,
                        "output_tokens": MAX_OUTPUT_TOKENS,
                        "cached_input_tokens": 0,
                    }
                )
                result.update(
                    input_token_reservation=input_bound, estimated_max_cost_usd=reservation
                )
                if (
                    Decimal(estimated_cost(known_usage)) + Decimal(reservation)
                    > config.max_cost_usd
                ):
                    result["error"] = "cost_budget"
                    return result
                if dry_run:
                    result.update(status="dry_run", mode="dry_run")
                    return result
                if client is None:
                    result["error"] = "provider_not_configured"
                    return result
                remaining = config.deadline_seconds - (time.monotonic() - started)
                if remaining <= 0:
                    raise TimeoutError
                call = {
                    "usage": None,
                    "estimated_cost_usd": None,
                    "input_token_reservation": input_bound,
                }
                result["model_calls"].append(call)
                result["model_requests"] += 1
                result.update(usage=None, estimated_cost_usd=None)
                completion = await client.with_options(
                    max_retries=0, timeout=remaining
                ).chat.completions.create(
                    model=config.model,
                    messages=messages,
                    tools=TOOLS,
                    response_format=response_format,
                    temperature=0,
                    store=False,
                    max_completion_tokens=MAX_OUTPUT_TOKENS,
                )
                try:
                    usage = read_usage(completion.usage)
                    if usage is None:
                        result["error"] = "unknown_usage"
                        return result
                    call.update(usage=usage, estimated_cost_usd=estimated_cost(usage))
                    if usage["cached_input_tokens"] is None:
                        result["cache_usage_complete"] = False
                    for key in known_usage:
                        known_usage[key] += usage[key] or 0
                    result.update(
                        usage=dict(known_usage), estimated_cost_usd=estimated_cost(known_usage)
                    )
                    completion = ChatCompletion.model_validate(completion.model_dump())
                except (AttributeError, TypeError, ValueError):
                    result["error"] = "invalid_response"
                    return result
                result["model_returned"] = completion.model
                if time.monotonic() - started >= config.deadline_seconds:
                    raise TimeoutError
                if Decimal(result["estimated_cost_usd"]) > config.max_cost_usd:
                    result["error"] = "cost_budget"
                    return result
                if (
                    usage["output_tokens"] > MAX_OUTPUT_TOKENS
                    or usage["input_tokens"] > input_bound
                ):
                    result["error"] = "token_budget"
                    return result
                if completion.model != config.model or len(completion.choices) != 1:
                    result["error"] = "invalid_response"
                    return result
                choice = completion.choices[0]
                if choice.message.refusal:
                    result["error"] = "provider_refusal"
                    return result
                calls = choice.message.tool_calls
                if not calls:
                    if choice.finish_reason != "stop":
                        result["error"] = "incomplete_output"
                        return result
                    report = InvestigationReport.model_validate_json(choice.message.content or "")
                    report = InvestigationReport.model_validate(
                        redact(report.model_dump(mode="json"))
                    )
                    validate_citations(report, batches)
                    result.update(status="completed", report=report.model_dump(mode="json"))
                    return result
                if choice.finish_reason != "tool_calls":
                    result["error"] = "incomplete_output"
                    return result
                if len({c.id for c in calls}) != len(calls) or any(not c.id for c in calls):
                    result["error"] = "invalid_response"
                    return result
                messages.append(
                    {"role": "assistant", "tool_calls": [c.model_dump() for c in calls]}
                )
                for call in calls:
                    if time.monotonic() - started >= config.deadline_seconds:
                        raise TimeoutError
                    if result["tool_executions"] >= MAX_TOOL_EXECUTIONS:
                        result["error"] = "tool_budget"
                        return result
                    if call.type != "function" or call.function.name not in TOOL_SCHEMAS:
                        result["error"] = "unknown_tool"
                        return result
                    name = call.function.name
                    try:
                        arguments = (
                            TOOL_SCHEMAS[name]
                            .model_validate_json(call.function.arguments)
                            .model_dump(mode="json")
                        )
                    except ValueError:
                        result["error"] = "invalid_arguments"
                        return result
                    if "services" in arguments:
                        arguments["services"] = sorted(arguments["services"])
                    identity = (name, canonical(arguments))
                    if identity in seen:
                        result["error"] = "duplicate_call"
                        return result
                    seen.add(identity)
                    tool_start = time.monotonic()
                    result["tool_executions"] += 1
                    batch = await getattr(tools, name)(**arguments)
                    batch = EvidenceBatch.model_validate(redact(batch.model_dump(mode="json")))
                    size = len(batch.model_dump_json().encode())
                    if size > MAX_RESULT_BYTES or evidence_bytes + size > MAX_EVIDENCE_BYTES:
                        result["error"] = "evidence_budget"
                        return result
                    evidence_bytes += size
                    batches.append(batch)
                    result["trace"].append(
                        {
                            "tool": name,
                            "arguments": redact(arguments),
                            "result": batch.model_dump(mode="json"),
                            "elapsed_ms": (time.monotonic() - tool_start) * 1000,
                        }
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "content": batch.model_dump_json(),
                        }
                    )
            result["error"] = "model_budget"
    except TimeoutError:
        result["error"] = "deadline_exceeded"
    except openai.OpenAIError:
        result["error"] = "provider_error"
    except ValueError:
        result["error"] = "invalid_report"
    finally:
        result["elapsed_ms"] = (time.monotonic() - started) * 1000
        if result["error"] is None and result["elapsed_ms"] > config.deadline_seconds * 1000:
            result.update(status="failed", error="deadline_exceeded", report=None)
    return result
