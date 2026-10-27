"""Business logic for the CI/CD Pipeline Visualizer.

Takes a GitHub-Actions-style workflow (YAML or JSON text) and turns it into a
job graph: validated, split into stages, with a critical path and a simulated run.
No web code lives here, so everything is easy to unit test.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from itertools import product
from typing import Any

try:  # PyYAML is optional: JSON input still works without it.
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


class PipelineError(Exception):
    """Raised when the pipeline text cannot be parsed or is invalid."""

    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


@dataclass
class Job:
    id: str
    name: str
    needs: list[str]
    runs_on: str
    steps: int
    minutes: int
    matrix_size: int = 1
    condition: str = ""
    stage: int = 0
    on_critical_path: bool = False


@dataclass
class Graph:
    workflow_name: str
    jobs: list[Job] = field(default_factory=list)
    critical_path: list[str] = field(default_factory=list)
    critical_minutes: int = 0

    def job(self, job_id: str) -> Job:
        return next(j for j in self.jobs if j.id == job_id)

    @property
    def stage_count(self) -> int:
        return max((j.stage for j in self.jobs), default=-1) + 1

    @property
    def max_parallel_jobs(self) -> int:
        counts: dict[int, int] = {}
        for j in self.jobs:
            counts[j.stage] = counts.get(j.stage, 0) + 1
        return max(counts.values(), default=0)

    def edges(self) -> list[dict[str, str]]:
        return [{"from": n, "to": j.id} for j in self.jobs for n in j.needs]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.workflow_name,
            "jobs": [j.__dict__ for j in self.jobs],
            "edges": self.edges(),
            "stage_count": self.stage_count,
            "max_parallel_jobs": self.max_parallel_jobs,
            "critical_path": self.critical_path,
            "critical_minutes": self.critical_minutes,
            "sequential_minutes": sum(j.minutes for j in self.jobs),
        }


# ---------------------------------------------------------------- parsing

def parse_text(text: str) -> dict[str, Any]:
    """Parse workflow text as JSON first, then YAML."""
    if not text or not text.strip():
        raise PipelineError(["The pipeline is empty. Paste a workflow or pick a sample."])
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        if yaml is None:
            raise PipelineError(["This is not valid JSON, and PyYAML is not installed to read YAML."])
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise PipelineError([f"Could not read the YAML: {exc}"])
    if not isinstance(data, dict):
        raise PipelineError(["The pipeline must be a mapping with a top-level 'jobs' key."])
    return data


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(v) for v in value]
    raise PipelineError([f"'needs' must be a string or a list, got {type(value).__name__}."])


def _matrix_size(job: dict[str, Any]) -> int:
    matrix = (job.get("strategy") or {}).get("matrix")
    if not isinstance(matrix, dict):
        return 1
    axes = [v for k, v in matrix.items() if k not in ("include", "exclude") and isinstance(v, list)]
    size = len(list(product(*axes))) if axes else 1
    include = matrix.get("include")
    if isinstance(include, list):
        size += len(include)
    return max(size, 1)


def build_graph(workflow: dict[str, Any]) -> Graph:
    """Validate the workflow and build the staged job graph."""
    jobs_raw = workflow.get("jobs")
    if not isinstance(jobs_raw, dict) or not jobs_raw:
        raise PipelineError(["No jobs found. Add a top-level 'jobs' section with at least one job."])

    errors: list[str] = []
    jobs: list[Job] = []
    for job_id, body in jobs_raw.items():
        body = body if isinstance(body, dict) else {}
        try:
            needs = _as_list(body.get("needs"))
        except PipelineError as exc:
            errors.extend(f"Job '{job_id}': {e}" for e in exc.errors)
            needs = []
        steps = body.get("steps")
        step_count = len(steps) if isinstance(steps, list) else 0
        minutes = body.get("x-duration-minutes")
        if not isinstance(minutes, (int, float)) or minutes <= 0:
            minutes = max(1, step_count)  # assumption: about one minute per step
        jobs.append(Job(
            id=str(job_id),
            name=str(body.get("name") or job_id),
            needs=needs,
            runs_on=str(body.get("runs-on") or "unspecified"),
            steps=step_count,
            minutes=int(minutes),
            matrix_size=_matrix_size(body),
            condition=str(body.get("if") or ""),
        ))

    ids = {j.id for j in jobs}
    for j in jobs:
        for n in j.needs:
            if n == j.id:
                errors.append(f"Job '{j.id}' lists itself in 'needs'.")
            elif n not in ids:
                errors.append(f"Job '{j.id}' needs '{n}', but no job has that name.")
    if errors:
        raise PipelineError(errors)

    graph = Graph(workflow_name=str(workflow.get("name") or "Untitled workflow"), jobs=jobs)
    _assign_stages(graph)
    _find_critical_path(graph)
    return graph


def _assign_stages(graph: Graph) -> None:
    """Stage = 0 for jobs with no needs, otherwise 1 + the latest stage of its needs.

    Uses Kahn's algorithm, which also detects dependency cycles.
    """
    remaining = {j.id: set(j.needs) for j in graph.jobs}
    stage = 0
    done: set[str] = set()
    while remaining:
        ready = [jid for jid, deps in remaining.items() if deps <= done]
        if not ready:
            raise PipelineError([
                "Circular dependency between: " + ", ".join(sorted(remaining)) + ". Remove one 'needs' link."
            ])
        for jid in ready:
            graph.job(jid).stage = stage
            del remaining[jid]
        done.update(ready)
        stage += 1
    graph.jobs.sort(key=lambda j: j.stage)  # stable: keeps file order within a stage


def _find_critical_path(graph: Graph) -> None:
    """Longest chain of dependent jobs by minutes: the pipeline can't finish faster than this."""
    best: dict[str, tuple[int, list[str]]] = {}
    for j in graph.jobs:  # already in dependency order
        prev = max((best[n] for n in j.needs), key=lambda b: b[0], default=(0, []))
        best[j.id] = (prev[0] + j.minutes, prev[1] + [j.id])
    total, path = max(best.values(), key=lambda b: b[0])
    graph.critical_minutes, graph.critical_path = total, path
    for jid in path:
        graph.job(jid).on_critical_path = True


# ------------------------------------------------------------- simulation

def simulate(graph: Graph, failing: list[str] | None = None) -> dict[str, Any]:
    """Pretend to run the pipeline and return per-job status and timings.

    * Jobs run as soon as all their needs finish (parallel where possible).
    * A job whose need failed or was skipped is skipped, unless it has
      `if: always()` (runs regardless) or `if: failure()` (runs only after a failure).
    """
    failing_set = set(failing or [])
    unknown = failing_set - {j.id for j in graph.jobs}
    if unknown:
        raise PipelineError([f"Cannot fail unknown job(s): {', '.join(sorted(unknown))}."])

    result: dict[str, dict[str, Any]] = {}
    for j in graph.jobs:
        needs = [result[n] for n in j.needs]
        upstream_bad = any(n["status"] in ("failed", "skipped") for n in needs)
        cond = j.condition.replace(" ", "")
        if "always()" in cond:
            should_run = True
        elif "failure()" in cond:
            should_run = any(n["status"] == "failed" for n in needs)
        else:
            should_run = not upstream_bad

        start = max((n["end"] for n in needs), default=0)
        if not should_run:
            result[j.id] = {"status": "skipped", "start": start, "end": start}
        else:
            status = "failed" if j.id in failing_set else "success"
            result[j.id] = {"status": status, "start": start, "end": start + j.minutes}

    statuses = [r["status"] for r in result.values()]
    ran = [r for r in result.values() if r["status"] != "skipped"]
    wall = max((r["end"] for r in ran), default=0)
    sequential = sum(graph.job(jid).minutes for jid, r in result.items() if r["status"] != "skipped")
    return {
        "jobs": result,
        "overall": "failed" if "failed" in statuses else "success",
        "wall_clock_minutes": wall,
        "sequential_minutes": sequential,
        "minutes_saved_by_parallelism": sequential - wall,
        "failed_jobs": [jid for jid, r in result.items() if r["status"] == "failed"],
        "skipped_jobs": [jid for jid, r in result.items() if r["status"] == "skipped"],
    }


def analyze(text: str) -> Graph:
    """Convenience: text in, validated graph out."""
    return build_graph(parse_text(text))
