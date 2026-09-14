"""Fixed-template metric tool: bounded, scoped, and absent unless configured."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import pytest
from app.investigation_schemas import InvestigationScope
from app.investigation_tools import EvidenceTools

SCOPE = InvestigationScope(
    services=("checkout", "inventory"),
    start="2026-01-01T10:00:00+00:00",
    end="2026-01-01T10:10:00+00:00",
)
ARGS = {
    "service": "checkout",
    "metric_name": "error_rate",
    "start": "2026-01-01T10:00:00+00:00",
    "end": "2026-01-01T10:05:00+00:00",
}


@pytest.fixture
def prometheus():
    queries = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            parsed = urlparse(self.path)
            queries.append(parse_qs(parsed.query))
            body = json.dumps(
                {
                    "status": "success",
                    "data": {
                        "resultType": "matrix",
                        "result": [{"metric": {}, "values": [[1767261600, "0.4"]]}],
                    },
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}", queries
    server.shutdown()


async def test_unconfigured_deployment_reports_source_unavailable():
    tools = EvidenceTools(SCOPE, records=[])
    batch = await tools.read_metric_series(**ARGS)
    assert batch.error == "source_unavailable" and batch.items == []


async def test_reads_fixed_template_series_with_literal_service(prometheus):
    url, queries = prometheus
    tools = EvidenceTools(SCOPE, records=[], prometheus_url=url)
    batch = await tools.read_metric_series(**ARGS)
    assert batch.error is None
    item = batch.items[0]
    assert item.kind == "metric" and item.content["points"] == [[1767261600.0, "0.4"]]
    query = queries[0]["query"][0]
    assert 'service="checkout"' in query and "5.." in query
    assert queries[0]["step"] == ["15s"]


async def test_rejects_out_of_scope_service_and_window(prometheus):
    url, _ = prometheus
    tools = EvidenceTools(SCOPE, records=[], prometheus_url=url)
    other = await tools.read_metric_series(**{**ARGS, "service": "payments"})
    assert other.error == "scope_violation"
    outside = await tools.read_metric_series(**{**ARGS, "end": "2026-01-01T11:00:01+00:00"})
    assert outside.error in {"invalid_arguments", "scope_violation"}


async def test_rejects_promql_injection_shaped_service_names(prometheus):
    url, queries = prometheus
    tools = EvidenceTools(SCOPE, records=[], prometheus_url=url)
    batch = await tools.read_metric_series(**{**ARGS, "service": 'checkout"}[1m])) or vector(1) #'})
    assert batch.error == "invalid_arguments" and queries == []


async def test_unreachable_prometheus_is_source_unavailable():
    tools = EvidenceTools(SCOPE, records=[], prometheus_url="http://127.0.0.1:1")
    batch = await tools.read_metric_series(**ARGS)
    assert batch.error == "source_unavailable"
