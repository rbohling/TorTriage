"""Serve the local Shadow demo dashboard and its latest measurement reports."""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


STATE = Path("/var/lib/tortriage")
HTML = Path(__file__).with_name("dashboard.html")
SCENARIOS = ("baseline", "constrained")


class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            self.respond("text/html; charset=utf-8", HTML.read_bytes())
        elif self.path == "/api/results":
            reports = {}
            for scenario in SCENARIOS:
                path = STATE / f"{scenario}.json"
                try:
                    reports[scenario] = json.loads(path.read_bytes())
                except FileNotFoundError:
                    reports[scenario] = None
            self.respond("application/json", json.dumps(reports).encode("utf-8"))
        else:
            self.send_error(404)

    def respond(self, content_type, body):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    with ThreadingHTTPServer(("0.0.0.0", 8787), DashboardHandler) as server:
        server.serve_forever()
