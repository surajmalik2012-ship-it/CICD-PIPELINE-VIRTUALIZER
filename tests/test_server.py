import json
import threading
import unittest
import urllib.error
import urllib.request

from app.server import make_server

PIPELINE = "jobs:\n  a:\n    x-duration-minutes: 2\n    steps: [{run: x}]\n  b:\n    needs: a\n    steps: [{run: x}]"


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = make_server(port=0)  # port 0 = any free port
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def request(self, path, body=None, raw=None):
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        req = urllib.request.Request(self.base + path, data=data, method="POST" if data is not None else "GET")
        try:
            with urllib.request.urlopen(req) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as err:
            return err.code, err.read()

    def test_home_page_is_served(self):
        status, body = self.request("/")
        self.assertEqual(status, 200)
        self.assertIn(b"Pipeline", body)

    def test_samples_list_and_fetch(self):
        status, body = self.request("/api/samples")
        names = json.loads(body)
        self.assertEqual(status, 200)
        self.assertIn("web-app", names)
        status, body = self.request("/api/samples/web-app")
        self.assertEqual(status, 200)
        self.assertIn(b"jobs:", body)

    def test_analyze_returns_graph(self):
        status, body = self.request("/api/analyze", {"text": PIPELINE})
        graph = json.loads(body)["graph"]
        self.assertEqual(status, 200)
        self.assertEqual(graph["stage_count"], 2)
        self.assertEqual(graph["critical_path"], ["a", "b"])

    def test_simulate_with_failure(self):
        status, body = self.request("/api/simulate", {"text": PIPELINE, "fail": ["a"]})
        run = json.loads(body)["run"]
        self.assertEqual(status, 200)
        self.assertEqual(run["jobs"]["b"]["status"], "skipped")

    def test_invalid_pipeline_returns_400_with_errors(self):
        status, body = self.request("/api/analyze", {"text": "jobs:\n  a:\n    needs: ghost"})
        self.assertEqual(status, 400)
        self.assertIn("ghost", json.loads(body)["errors"][0])

    def test_bad_json_body_returns_400(self):
        status, _ = self.request("/api/analyze", raw=b"not json")
        self.assertEqual(status, 400)

    def test_fail_must_be_a_list(self):
        status, _ = self.request("/api/simulate", {"text": PIPELINE, "fail": "a"})
        self.assertEqual(status, 400)

    def test_unknown_route_is_404(self):
        self.assertEqual(self.request("/nope")[0], 404)

    def test_path_traversal_is_blocked(self):
        self.assertEqual(self.request("/static/../app/server.py")[0], 404)
        self.assertEqual(self.request("/static/%2e%2e/app/server.py")[0], 404)


if __name__ == "__main__":
    unittest.main()
