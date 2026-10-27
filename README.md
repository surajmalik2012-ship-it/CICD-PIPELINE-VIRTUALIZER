# CI/CD Pipeline Visualizer

Paste a GitHub Actions workflow (YAML or JSON) and see it as a graph: which jobs run in which stage, which chain of jobs decides the total time (the *critical path*), and what happens to the rest of the pipeline when a job fails.

## Features (all working end to end)

| Feature | What it does | Where |
|---|---|---|
| Parse and validate | Reads YAML/JSON, reports unknown `needs`, self-dependencies, circular dependencies and bad input in plain language | `app/pipeline.py` |
| Stage layout | Groups jobs into stages: a job sits one stage after its slowest dependency | `app/pipeline.py` |
| Critical path | Finds the longest dependent chain by minutes: the fastest the pipeline can possibly finish | `app/pipeline.py` |
| Failure simulation | Click jobs to make them fail, then run: downstream jobs are skipped, `if: always()` and `if: failure()` are respected | `app/pipeline.py` |
| Time saved by parallelism | Compares run time with parallel jobs against running everything one after another | `app/pipeline.py` |
| Interactive graph | SVG graph, animated run, keyboard accessible | `static/` |

## Run it

```bash
pip install -r requirements.txt     # only PyYAML
python run.py                       # then open http://127.0.0.1:8000
```

## Run the tests

```bash
python -m unittest discover -v      # 36 tests: logic + HTTP API
```

## Architecture

```
Browser (static/index.html, app.js, style.css)
   |  JSON over HTTP
   v
app/server.py      routes, input limits, static files      <- thin layer
   |
   v
app/pipeline.py    parse -> validate -> stages -> critical path -> simulate   <- all the logic
   |
samples/*.yml      example workflows
```

Python standard library only for the server (plus PyYAML for reading YAML). No database: a workflow is analysed on request and nothing is stored.

## How durations work

Add `x-duration-minutes: 4` to a job to set how long it takes. If you leave it out, each step counts as one minute. This is an assumption, because a workflow file does not say how long jobs take.

## What I learned

> Edit this section in your own words before submitting. Suggested points are below.

- A pipeline is a directed acyclic graph. Stages come from a topological sort (Kahn's algorithm), and the same algorithm detects circular dependencies.
- The critical path is the longest path in that graph. Speeding up a job that is not on it does not make the pipeline faster.
- Keeping logic in `pipeline.py` and away from the web layer made it easy to unit test.
- Validation messages should name the exact job that is wrong.
- User-supplied text must never be inserted as HTML (the page uses `textContent`), and file serving must block path traversal.

## Limits

- Understands `jobs`, `needs`, `if: always()` / `if: failure()`, `strategy.matrix` and `runs-on`. It does not run real workflows or call GitHub.
- Other CI tools (GitLab CI, Jenkins) are not supported yet.
