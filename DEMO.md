# Demo guide (keep this on your laptop, not for grading)

## Before you walk in (10 minutes)
1. `pip install -r requirements.txt`
2. `python -m unittest discover -v` -> shows 36 tests passing
3. `python run.py` -> open http://127.0.0.1:8000
4. Have the GitHub repo open in another tab (README, `output/Assessment-2.md`, `output/LLM-interaction/`)

## 4-minute demo script
1. **Problem (20 s).** "Workflow files are long. It is hard to see what runs in parallel, why a pipeline is slow, or what a failure skips."
2. **Show the graph (40 s).** The web-app sample is loaded. Point out the stages as columns and the three jobs at the start running together.
3. **Critical path (40 s).** Tick the highlight box. "This chain decides the total time. Speeding up lint would not help, because unit tests are slower."
4. **Run simulation (40 s).** Click Run simulation. Everything passes and the summary shows time saved by running jobs together.
5. **Failure (60 s).** Click "Unit tests" so it gets a dashed red outline, run again. Build, Docker, both deploys are skipped, but "Notify team" still runs because of `if: always()`.
6. **Validation (30 s).** Load the "broken cycle" sample. It names the circular dependency and tells you what to do.
7. **Tests and repo (30 s).** Show the test run and the GitHub commits.

## Questions you may be asked
- **How are stages decided?** A job's stage is one more than the latest stage among the jobs it needs. Jobs with no needs are stage 1.
- **How do you detect a cycle?** Repeatedly take jobs whose dependencies are all done. If none are ready but jobs remain, they depend on each other.
- **What is the critical path?** The longest chain of dependent jobs by minutes. The pipeline cannot finish faster than that.
- **Where do durations come from?** From `x-duration-minutes`, or one minute per step if missing. This is an assumption, stated in the README.
- **Why no database?** Nothing needs to be saved. Each request is analysed and returned.
- **Why separate `pipeline.py` from `server.py`?** So the logic can be tested without a web server.
- **What would you add next?** GitLab CI and Jenkins support, reading a workflow straight from a GitHub URL, real run durations from the GitHub API.

## Commits (the course checks this)
Commit on at least two different days. Today and tomorrow both count. Suggested commits:
1. `git init`, add `README.md`, `.gitignore`, `output/Assessment-2.md`
2. Add `app/pipeline.py` and `tests/test_pipeline.py`
3. Add `app/server.py` and `tests/test_server.py`
4. Add `static/` and `samples/`
5. Add your own LLM interactions and README learnings
