"""Small HTTP server (standard library only) for the CI/CD Pipeline Visualizer.

Routes
  GET  /                      the web page
  GET  /static/<file>         css / js
  GET  /api/samples           list of sample pipeline names
  GET  /api/samples/<name>    text of one sample
  POST /api/analyze           {"text": "..."}                  -> graph
  POST /api/simulate          {"text": "...", "fail": ["id"]}  -> graph + run
"""
from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

from .pipeline import PipelineError, analyze, simulate

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "static"
SAMPLES_DIR = ROOT / "samples"
MAX_BODY_BYTES = 1_000_000

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
}


class Handler(BaseHTTPRequestHandler):
    server_version = "PipelineVisualizer/1.0"

    # ------------------------------------------------------------ helpers
    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: dict | list) -> None:
        self._send(status, json.dumps(payload).encode(), "application/json")

    def _file(self, base: Path, relative: str) -> None:
        target = (base / relative).resolve()
        # Block path traversal such as /static/../app/server.py
        if base.resolve() not in target.parents or not target.is_file():
            self._json(404, {"errors": ["Not found."]})
            return
        ctype = CONTENT_TYPES.get(target.suffix, "text/plain; charset=utf-8")
        self._send(200, target.read_bytes(), ctype)

    def _read_json_body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise PipelineError(["Invalid Content-Length header."])
        if length > MAX_BODY_BYTES:
            raise PipelineError(["The pipeline is too large (limit 1 MB)."])
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            raise PipelineError(["Request body must be valid JSON."])
        if not isinstance(data, dict):
            raise PipelineError(["Request body must be a JSON object."])
        return data

    # ------------------------------------------------------------- routes
    def do_GET(self) -> None:  # noqa: N802 (name required by BaseHTTPRequestHandler)
        path = unquote(self.path.split("?", 1)[0])
        if path in ("/", "/index.html"):
            self._file(STATIC_DIR, "index.html")
        elif path.startswith("/static/"):
            self._file(STATIC_DIR, path[len("/static/"):])
        elif path == "/api/samples":
            names = sorted(p.stem for p in SAMPLES_DIR.glob("*.yml"))
            self._json(200, names)
        elif path.startswith("/api/samples/"):
            self._file(SAMPLES_DIR, path[len("/api/samples/"):] + ".yml")
        else:
            self._json(404, {"errors": ["Not found."]})

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path not in ("/api/analyze", "/api/simulate"):
            self._json(404, {"errors": ["Not found."]})
            return
        try:
            body = self._read_json_body()
            graph = analyze(str(body.get("text", "")))
            payload = {"graph": graph.to_dict()}
            if path == "/api/simulate":
                fail = body.get("fail", [])
                if not isinstance(fail, list):
                    raise PipelineError(["'fail' must be a list of job ids."])
                payload["run"] = simulate(graph, [str(f) for f in fail])
            self._json(200, payload)
        except PipelineError as exc:
            self._json(400, {"errors": exc.errors})

    def log_message(self, fmt: str, *args) -> None:  # keep the console quiet
        sys.stderr.write("[server] " + fmt % args + "\n")


def make_server(host: str = "127.0.0.1", port: int = 8000) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), Handler)


def main(port: int = 8000) -> None:
    server = make_server(port=port)
    print(f"CI/CD Pipeline Visualizer running at http://127.0.0.1:{port}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
