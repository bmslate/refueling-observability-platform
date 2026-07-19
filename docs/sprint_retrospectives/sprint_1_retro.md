# Sprint 1 Retrospective

## Sprint

**Project:** Refueling Safety Observability Platform  
**Sprint:** Sprint 1 — Local Observability MVP

## Retrospective Goal

Review what worked well, what caused difficulty, what was learned, and what should change in the next sprint.

## What Went Well

### 1. The Work Was Broken Into Small Steps

The project progressed through small, verifiable tasks:

- Build the controller
- Read telemetry
- Parse telemetry
- Expose metrics
- Connect Prometheus
- Build Grafana
- Add Docker Compose
- Simulate a fault
- Write runbooks
- Update documentation

This made debugging easier and reduced the risk of changing too many parts at once.

### 2. Safety Logic Remained Deterministic

The C controller remained responsible for safety-critical behavior.

Python, Prometheus, Grafana, and documentation tools only observed or reported controller state.

This preserved a clear safety boundary.

### 3. Manual Verification Was Valuable

The controller was tested directly inside Docker before relying on Prometheus or Grafana.

The manual pressure-high test confirmed:

```text
STATE=ABORT
PRESSURE=90
GATE=CLOSED
FAULT=PRESSURE_OUT_OF_RANGE
```

This made later dashboard results easier to trust.

### 4. The Observability Stack Became Reproducible

Docker Compose reduced the number of manual startup steps.

The stack can now be started with:

```powershell
docker compose up -d --build
```

This is a major improvement over starting each component separately.

### 5. The Incident Scenario Produced Clear Evidence

The pressure-high scenario created visible changes in:

- Controller output
- Prometheus metrics
- Grafana panels
- Saved screenshots
- Runbook documentation

This made the project more useful as a portfolio demonstration.

### 6. Documentation Improved Alongside the Code

The README and runbooks were updated to match the real implementation.

The documentation now clearly distinguishes between:

- Software-in-the-loop telemetry
- Real hardware telemetry
- Service health
- Controller fault state
- Current indicators
- Future cumulative counters

## What Could Be Improved

### 1. The Current Process Model Is Inefficient

The telemetry-monitor starts a new C controller process for every Prometheus scrape.

This works for an MVP, but it is not a realistic continuous telemetry architecture.

It also means the selected scenario is replayed repeatedly.

### 2. Some Metric Names Are Misleading

The metrics:

```text
refueling_fault_count
refueling_abort_count
```

currently behave as state indicators.

They do not count cumulative events.

This should be corrected in a future sprint by either:

- Renaming them as state metrics, or
- Implementing true counters

### 3. Telemetry Age Is Not Yet Real

`refueling_telemetry_age_seconds` is currently simplified.

A real implementation should record the timestamp of the latest valid telemetry sample and calculate age dynamically.

### 4. Timeout Behavior Is Documented but Not Yet Simulated

The telemetry-timeout runbook exists, but there is not yet a dedicated timeout scenario.

A future test should intentionally:

- Delay controller output
- Stop controller output
- Terminate the controller process
- Return malformed telemetry

### 5. Some Documentation Was Created Late

Several documentation tasks were completed after the technical implementation.

In the next sprint, documentation should be updated closer to the related code changes.

### 6. Repository Cleanup Requires More Discipline

Several old planning files and backup files remained untracked.

The next sprint should include a cleanup task to decide whether each file should be:

- Deleted
- Archived
- Added to `.gitignore`
- Merged into official documentation
- Committed intentionally

## What Was Learned

### Technical Lessons

- `subprocess.Popen` can maintain one controller process for a multi-command sequence
- A background thread can safely read controller output while the main thread sends commands
- A queue is useful for passing output between threads
- Prometheus scraping and Grafana refresh are separate processes
- Grafana can remain healthy while the controller reports a fault
- Service health and process safety state must be represented separately
- Docker named volumes are useful for runtime persistence
- Runtime backup directories should not be committed to Git

### Process Lessons

- Verify the source system before debugging the monitoring layer
- Use screenshots as incident evidence
- Keep commit messages focused
- Avoid `git add .` when unrelated files are present
- Separate feature commits from documentation commits
- Keep README claims aligned with actual implementation
- Record limitations honestly instead of presenting planned work as completed

## Action Items for Sprint 2

### Architecture

- [ ] Create one persistent long-running controller process
- [ ] Add a background telemetry reader
- [ ] Store the latest valid telemetry sample in memory
- [ ] Prevent Prometheus scrapes from restarting the controller
- [ ] Add controller process lifecycle management

### Metrics

- [ ] Implement real telemetry timestamps
- [ ] Calculate real telemetry age
- [ ] Rename fault and abort indicators or implement true counters
- [ ] Add metric labels only where they provide clear value

### Testing

- [ ] Add automated reset-scenario test
- [ ] Add automated pressure-high test
- [ ] Add malformed telemetry test
- [ ] Add controller timeout test
- [ ] Add controller process exit test

### Alerting

- [ ] Add pressure-high alert rule
- [ ] Add telemetry-timeout alert rule
- [ ] Add controller-unhealthy alert rule
- [ ] Evaluate Alertmanager integration

### Documentation

- [ ] Update architecture diagram
- [ ] Update README when persistent telemetry is implemented
- [ ] Add incident evidence for timeout behavior
- [ ] Keep runbooks synchronized with implementation
- [ ] Clean up old planning and backup files

## Start Doing

- Update documentation during each feature
- Add tests with each scenario
- Use one focused commit per logical change
- Confirm metric semantics before naming metrics
- Track architecture limitations as GitHub Issues

## Stop Doing

- Replaying a full simulator scenario on every scrape
- Treating state indicators as if they were event counters
- Leaving temporary files in the repository root without a decision
- Delaying documentation until the end of a sprint

## Continue Doing

- Preserve deterministic safety decisions in the C controller
- Test manually before adding observability layers
- Use GitHub Issues and Project Board status tracking
- Save screenshots as verification evidence
- Document limitations honestly
- Build the project in small, reviewable increments

## Retrospective Summary

Sprint 1 successfully established the local observability foundation.

The main technical debt is the per-scrape controller process model.

Sprint 2 should focus on persistent telemetry, accurate freshness detection, automated testing, and alerting while preserving the deterministic safety boundary.
