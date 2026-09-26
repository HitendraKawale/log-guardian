"""Small source-owned fixtures shared by adapter and import boundary checks."""

import json

OWNER = {
    "sources": [
        {
            "source_id": "edge",
            "service": "gateway",
            "event_kind": "gateway_request",
            "request_namespace": "shop",
            "format": "nginx_json",
        },
        {
            "source_id": "auth",
            "service": "authentication",
            "event_kind": "authentication_result",
            "request_namespace": "shop",
            "format": "application_auth_json",
        },
    ]
}
SCOPE = {
    "services": ["gateway", "authentication"],
    "start": "2026-09-01T10:00:00Z",
    "end": "2026-09-01T10:10:00Z",
}
NGINX = {
    "time": "2026-09-01T10:00:02+00:00",
    "request_id": "request-1",
    "remote_addr": "192.0.2.1",
    "status": "200",
    "route": "/login",
}
AUTH = {
    "event_id": "auth-1",
    "timestamp": "2026-09-01T10:00:01Z",
    "request_id": "request-1",
    "account_ref": "account-1",
    "outcome": "failure",
}


def payload(nginx=None, auth=None):
    return {
        "scope": SCOPE,
        "logs": {"edge": json.dumps(nginx or NGINX), "auth": json.dumps(auth or AUTH)},
    }
