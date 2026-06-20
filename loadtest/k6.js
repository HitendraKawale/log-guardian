// k6 load test for Log Guardian.
// Run against the running stack:
//   docker run --rm -i -e BASE_URL=http://host.docker.internal:8010 \
//     grafana/k6 run - < loadtest/k6.js
import http from "k6/http";
import { check, sleep } from "k6";
import { Counter } from "k6/metrics";

const BASE = __ENV.BASE_URL || "http://localhost:8000";
const anomalies = new Counter("anomalies_flagged");

export const options = {
  scenarios: {
    // Synchronous ingest — scored inline, so it exercises the AI call path.
    sync: { executor: "constant-vus", vus: 10, duration: "20s", exec: "syncIngest" },
    // Streaming ingest — returns immediately; scoring happens in the worker.
    stream: { executor: "constant-vus", vus: 10, duration: "20s", exec: "streamIngest" },
  },
  thresholds: {
    http_req_failed: ["rate<0.01"],
    "http_req_duration{scenario:stream}": ["p(95)<200"],
  },
};

const LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"];
const MSGS = [
  "request completed in 12ms",
  "connection refused, request failed",
  "read timeout after 3000ms",
  "user 42 logged in",
  "out of memory: killed process",
];

function payload() {
  const level = LEVELS[Math.floor(Math.random() * LEVELS.length)];
  const message = MSGS[Math.floor(Math.random() * MSGS.length)];
  return JSON.stringify({
    service: "loadtest",
    level,
    message,
    timestamp: new Date().toISOString(),
  });
}

const headers = { "Content-Type": "application/json" };

export function syncIngest() {
  const res = http.post(`${BASE}/logs`, payload(), { headers });
  check(res, { "sync 201": (r) => r.status === 201 });
  if (res.status === 201 && res.json("is_anomaly")) anomalies.add(1);
  sleep(0.1);
}

export function streamIngest() {
  const res = http.post(`${BASE}/logs/stream`, payload(), { headers });
  check(res, { "stream 202": (r) => r.status === 202 });
  sleep(0.05);
}
