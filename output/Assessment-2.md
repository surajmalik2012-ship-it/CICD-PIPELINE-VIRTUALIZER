# Assessment-2: CI/CD Pipeline Visualizer

## 1. Project title and description
**CI/CD Pipeline Visualizer.** A web tool that reads a GitHub Actions workflow and shows its jobs as a dependency graph, highlights the critical path, and simulates what happens when jobs fail.

**Problem.** Workflow files get long and hard to read. Developers cannot easily see which jobs run in parallel, why a pipeline is slow, or what a failure will skip.

## 2. Major components
| Component | Role |
|---|---|
| UI | Editor, sample picker, SVG graph, run button, summary figures (`static/`) |
| Logic | Parsing, validation, stage assignment, critical path, simulation (`app/pipeline.py`) |
| Persistence (data) | None for now. Sample workflows live as files in `samples/`. Nothing is stored per user. |

## 3. Architecture
Client-server with a thin HTTP layer in front of a pure-logic module. The browser sends the workflow text to a JSON API, and the logic module returns a graph and run result. Chosen because it keeps logic testable on its own and needs no database for this scope.

## 4. Minimal feature set for the first deliverable
1. Parse a workflow (YAML or JSON) and validate it.
2. Show jobs in stages as a graph.
3. Find and highlight the critical path.
4. Simulate a run with chosen failures.

## 5. Users who benefit
- Students learning CI/CD.
- Developers reviewing or debugging a workflow.
- Team leads looking for slow pipelines.

## 6. Components of the first deliverable
Workflow parser, graph builder, critical-path finder, run simulator, HTTP API, web page.

## 7. Interfaces
| Interface | Input | Output |
|---|---|---|
| `parse_text(text)` | YAML or JSON string | dict, or `PipelineError` |
| `build_graph(workflow)` | dict | `Graph` (jobs, stages, critical path), or `PipelineError` |
| `simulate(graph, failing)` | graph, list of job ids | statuses, timings, time saved |
| `POST /api/analyze` | `{"text": "..."}` | `{"graph": {...}}` or `400 {"errors": [...]}` |
| `POST /api/simulate` | `{"text": "...", "fail": ["job"]}` | `{"graph": {...}, "run": {...}}` |
| `GET /api/samples`, `GET /api/samples/<name>` | none | sample names / sample text |

## 8. Tech stack
- Language: Python 3 (backend), JavaScript (frontend, no framework)
- Libraries: PyYAML; standard library `http.server`, `unittest`
- Database: none
- Tools: Git and GitHub, an LLM assistant for help (interactions saved in `output/LLM-interaction/`)

## 9. Out of scope
Running real workflows, connecting to GitHub, other CI tools, user accounts.

## Assumptions
A job without `x-duration-minutes` takes one minute per step.
