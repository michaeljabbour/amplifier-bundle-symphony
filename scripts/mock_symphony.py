"""Mock Symphony API server for testing the Amplifier bundle."""

from http.server import HTTPServer, BaseHTTPRequestHandler
import json

MOCK_STATE = {
    "generated_at": "2026-03-08T12:30:00Z",
    "counts": {"running": 2, "retrying": 1},
    "running": [
        {"issue_id": "abc123", "issue_identifier": "MT-649", "state": "In Progress",
         "session_id": "thread-1-turn-1", "turn_count": 7, "last_event": "notification",
         "last_message": "Working on tests", "started_at": "2026-03-08T12:10:00Z",
         "last_event_at": "2026-03-08T12:29:00Z",
         "tokens": {"input_tokens": 1200, "output_tokens": 800, "total_tokens": 2000}},
        {"issue_id": "def456", "issue_identifier": "MT-650", "state": "In Progress",
         "session_id": "thread-2-turn-3", "turn_count": 3, "last_event": "turn_completed",
         "last_message": "", "started_at": "2026-03-08T12:20:00Z",
         "last_event_at": "2026-03-08T12:28:00Z",
         "tokens": {"input_tokens": 500, "output_tokens": 300, "total_tokens": 800}}
    ],
    "retrying": [
        {"issue_id": "ghi789", "issue_identifier": "MT-651", "attempt": 3,
         "due_at": "2026-03-08T12:35:00Z", "error": "turn timeout after 3600s"}
    ],
    "codex_totals": {"input_tokens": 45000, "output_tokens": 22000,
                     "total_tokens": 67000, "seconds_running": 7200.5},
    "rate_limits": None
}

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/v1/state":
            self._json(200, MOCK_STATE)
        elif self.path.startswith("/api/v1/"):
            ident = self.path.split("/")[-1]
            self._json(200, {"issue_identifier": ident, "status": "running",
                "workspace": {"path": f"/tmp/symphony_workspaces/{ident}"},
                "attempts": {"restart_count": 1, "current_retry_attempt": 0},
                "running": MOCK_STATE["running"][0], "retry": None,
                "recent_events": [
                    {"at": "2026-03-08T12:29:00Z", "event": "notification", "message": "Working on tests"},
                    {"at": "2026-03-08T12:25:00Z", "event": "turn_completed", "message": "Finished implementing auth module"},
                ],
                "last_error": None})
        else:
            self._json(404, {"error": {"code": "not_found", "message": "Unknown path"}})

    def do_POST(self):
        if self.path == "/api/v1/refresh":
            self._json(202, {"queued": True, "coalesced": False,
                "requested_at": "2026-03-08T12:31:00Z", "operations": ["poll", "reconcile"]})
        else:
            self._json(405, {"error": {"code": "method_not_allowed"}})

    def _json(self, code, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def log_message(self, format, *args):
        print(f"  {args[0]}")

if __name__ == "__main__":
    print("Mock Symphony API running on http://localhost:4000")
    print("  GET  /api/v1/state     -> system status")
    print("  GET  /api/v1/<id>      -> issue detail")
    print("  POST /api/v1/refresh   -> trigger refresh")
    HTTPServer(("localhost", 4000), Handler).serve_forever()
