import json
import unittest
from pathlib import Path

from app.pipeline import PipelineError, analyze, build_graph, parse_text, simulate

SAMPLES = Path(__file__).resolve().parent.parent / "samples"

DIAMOND = """
name: Diamond
jobs:
  a: {x-duration-minutes: 1, steps: [{run: x}]}
  b: {needs: a, x-duration-minutes: 5, steps: [{run: x}]}
  c: {needs: a, x-duration-minutes: 2, steps: [{run: x}]}
  d: {needs: [b, c], x-duration-minutes: 1, steps: [{run: x}]}
"""


class ParsingTests(unittest.TestCase):
    def test_parses_yaml(self):
        self.assertIn("jobs", parse_text(DIAMOND))

    def test_parses_json(self):
        data = parse_text(json.dumps({"jobs": {"a": {"steps": [{"run": "x"}]}}}))
        self.assertIn("a", data["jobs"])

    def test_empty_text_is_rejected(self):
        with self.assertRaises(PipelineError):
            parse_text("   ")

    def test_non_mapping_is_rejected(self):
        with self.assertRaises(PipelineError):
            parse_text("- just\n- a list")

    def test_bad_yaml_gives_readable_error(self):
        with self.assertRaises(PipelineError) as ctx:
            parse_text("jobs: [unclosed")
        self.assertIn("YAML", ctx.exception.errors[0])


class ValidationTests(unittest.TestCase):
    def test_missing_jobs_section(self):
        with self.assertRaises(PipelineError):
            build_graph({"name": "x"})

    def test_unknown_dependency_is_named(self):
        with self.assertRaises(PipelineError) as ctx:
            analyze("jobs:\n  a:\n    needs: ghost\n    steps: [{run: x}]")
        self.assertIn("ghost", ctx.exception.errors[0])

    def test_self_dependency(self):
        with self.assertRaises(PipelineError) as ctx:
            analyze("jobs:\n  a:\n    needs: a\n    steps: [{run: x}]")
        self.assertIn("itself", ctx.exception.errors[0])

    def test_cycle_is_detected(self):
        text = (SAMPLES / "broken-cycle.yml").read_text()
        with self.assertRaises(PipelineError) as ctx:
            analyze(text)
        self.assertIn("Circular", ctx.exception.errors[0])

    def test_needs_with_wrong_type(self):
        with self.assertRaises(PipelineError):
            analyze("jobs:\n  a:\n    needs: {x: 1}\n    steps: [{run: x}]")


class GraphTests(unittest.TestCase):
    def setUp(self):
        self.graph = analyze(DIAMOND)

    def test_stages(self):
        stages = {j.id: j.stage for j in self.graph.jobs}
        self.assertEqual(stages, {"a": 0, "b": 1, "c": 1, "d": 2})

    def test_stage_count_and_parallelism(self):
        self.assertEqual(self.graph.stage_count, 3)
        self.assertEqual(self.graph.max_parallel_jobs, 2)

    def test_critical_path_picks_slowest_branch(self):
        self.assertEqual(self.graph.critical_path, ["a", "b", "d"])
        self.assertEqual(self.graph.critical_minutes, 7)

    def test_edges(self):
        pairs = {(e["from"], e["to"]) for e in self.graph.edges()}
        self.assertEqual(pairs, {("a", "b"), ("a", "c"), ("b", "d"), ("c", "d")})

    def test_duration_defaults_to_one_minute_per_step(self):
        g = analyze("jobs:\n  a:\n    steps: [{run: 1}, {run: 2}, {run: 3}]")
        self.assertEqual(g.job("a").minutes, 3)

    def test_matrix_size(self):
        g = analyze(
            "jobs:\n  t:\n    strategy:\n      matrix:\n        py: [1, 2, 3]\n        os: [a, b]\n"
            "    steps: [{run: x}]"
        )
        self.assertEqual(g.job("t").matrix_size, 6)

    def test_single_job_pipeline(self):
        g = analyze("jobs:\n  only:\n    steps: [{run: x}]")
        self.assertEqual((g.stage_count, g.critical_path), (1, ["only"]))

    def test_job_order_in_file_does_not_matter(self):
        g = analyze("jobs:\n  last:\n    needs: first\n    steps: [{run: x}]\n  first:\n    steps: [{run: x}]")
        self.assertEqual([j.id for j in g.jobs], ["first", "last"])


class SimulationTests(unittest.TestCase):
    def setUp(self):
        self.graph = analyze(DIAMOND)

    def test_all_green(self):
        run = simulate(self.graph)
        self.assertEqual(run["overall"], "success")
        self.assertEqual(run["wall_clock_minutes"], 7)  # critical path
        self.assertEqual(run["sequential_minutes"], 9)
        self.assertEqual(run["minutes_saved_by_parallelism"], 2)

    def test_failure_skips_downstream_jobs(self):
        run = simulate(self.graph, ["b"])
        self.assertEqual(run["overall"], "failed")
        self.assertEqual(run["jobs"]["c"]["status"], "success")  # parallel branch still runs
        self.assertEqual(run["jobs"]["d"]["status"], "skipped")
        self.assertEqual(run["failed_jobs"], ["b"])
        self.assertEqual(run["skipped_jobs"], ["d"])

    def test_unknown_failing_job_is_rejected(self):
        with self.assertRaises(PipelineError):
            simulate(self.graph, ["nope"])

    def test_always_runs_even_after_failure(self):
        g = analyze("jobs:\n  a:\n    steps: [{run: x}]\n  n:\n    needs: a\n    if: always()\n    steps: [{run: x}]")
        self.assertEqual(simulate(g, ["a"])["jobs"]["n"]["status"], "success")

    def test_failure_condition_runs_only_after_failure(self):
        g = analyze("jobs:\n  a:\n    steps: [{run: x}]\n  alert:\n    needs: a\n    if: failure()\n    steps: [{run: x}]")
        self.assertEqual(simulate(g)["jobs"]["alert"]["status"], "skipped")
        self.assertEqual(simulate(g, ["a"])["jobs"]["alert"]["status"], "success")

    def test_job_starts_when_slowest_need_finishes(self):
        run = simulate(self.graph)
        self.assertEqual(run["jobs"]["d"]["start"], 6)  # a(1) + b(5)


class SampleFileTests(unittest.TestCase):
    def test_good_samples_parse(self):
        for name in ("web-app", "python-package"):
            graph = analyze((SAMPLES / f"{name}.yml").read_text())
            self.assertGreater(len(graph.jobs), 3, name)

    def test_web_app_critical_path(self):
        graph = analyze((SAMPLES / "web-app.yml").read_text())
        self.assertEqual(graph.critical_path[0], "unit-tests")
        self.assertEqual(graph.critical_path[-1], "notify")

    def test_web_app_notify_runs_after_failure(self):
        graph = analyze((SAMPLES / "web-app.yml").read_text())
        run = simulate(graph, ["unit-tests"])
        self.assertEqual(run["jobs"]["build"]["status"], "skipped")
        self.assertEqual(run["jobs"]["notify"]["status"], "success")


if __name__ == "__main__":
    unittest.main()
