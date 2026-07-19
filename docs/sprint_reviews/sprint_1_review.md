# Sprint 1 Review

## Sprint Overview

**Project:** Refueling Safety Observability Platform  
**Sprint:** Sprint 1 — Local Observability MVP  
**Status:** Completed with documented follow-up work

Sprint 1 focused on turning the existing deterministic C refueling controller into a locally observable software-in-the-loop system.

The sprint goal was to make controller behavior visible through telemetry, Prometheus metrics, Grafana dashboards, Docker Compose, and incident-response documentation.

## Sprint Goal

Build a repeatable local observability stack that can:

- Run the C refueling controller inside Docker
- Collect controller-generated telemetry
- Expose telemetry as Prometheus-compatible metrics
- Visualize controller status in Grafana
- Demonstrate a controlled safety fault
- Document detection, investigation, and recovery steps
- Track work through GitHub Issues, Projects, and milestones

## Completed Work

### Controller and Safety Logic

- Imported and validated the original C refueling controller
- Compiled the controller inside the telemetry-monitor Docker image
- Restored automatic safety checks during command processing
- Verified deterministic fault detection and abort behavior
- Verified that unsafe pressure causes:
  - `STATE=ABORT`
  - `GATE=CLOSED`
  - `FAULT=PRESSURE_OUT_OF_RANGE`
  - `ABORT_PRESSURE_OUT_OF_RANGE` in the event log

### Telemetry Integration

- Added a Python telemetry parser for controller `TLM` output
- Added a simulator client that:
  - Starts the controller process
  - Sends commands through standard input
  - Reads output through standard output
  - Uses a background reader thread and queue
  - Supports multi-command scenario execution
- Connected the FastAPI monitor to controller-generated telemetry

### FastAPI and Prometheus

- Added the `/health` endpoint
- Added the `/metrics` endpoint
- Exported refueling telemetry through `prometheus-client`
- Added metrics for:
  - Alignment
  - Pressure
  - Fuel level
  - Docked state
  - Gate state
  - Fault state
  - Abort state
  - Controller collection health
  - Telemetry age
- Configured Prometheus to scrape every 5 seconds
- Verified that the Prometheus target is `UP`

### Docker Compose

- Added Docker Compose for:
  - telemetry-monitor
  - Prometheus
  - Grafana
- Added a named Docker volume for persistent Grafana data
- Added environment-based simulator scenario selection

### Simulator Scenarios

Implemented:

```text
reset
pressure_high
```

The pressure-high scenario injects:

```text
SIM_PRESSURE 90
```

The safe maximum pressure is:

```text
80
```

The scenario was verified manually and through the observability stack.

### Grafana

- Built a dashboard with:
  - Controller Health
  - Fault Count
  - Abort Count
  - Telemetry Age
  - Alignment Trend
  - Refueling Pressure Trend
- Enabled dashboard auto-refresh
- Saved evidence for:
  - Pressure-high fault state
  - Recovered reset state

Evidence files:

```text
docs/images/grafana_simulator_mode_dashboard_PRESSURE_HIGH.png
docs/images/grafana_simulator_mode_dashboard_RESET.png
```

### Incident Documentation

Created:

```text
runbooks/pressure_high.md
runbooks/telemetry_timeout.md
```

The runbooks document:

- Symptoms
- Detection methods
- Metrics to inspect
- Logs and commands to inspect
- Recovery steps
- Recovery verification
- Current platform limitations

### Documentation and Workflow

- Updated `README.md`
- Updated the repository structure and local run instructions
- Documented current implementation limitations
- Used GitHub Issues, Projects, and sprint-style milestones
- Linked technical work to incident and documentation tasks

## Demonstrated Outcome

The local stack can now reproduce and observe a controlled pressure fault.

Expected pressure-high outcome:

```text
STATE=ABORT
PRESSURE=90
GATE=CLOSED
FAULT=PRESSURE_OUT_OF_RANGE
```

Expected Prometheus and Grafana indicators:

```text
refueling_pressure 90
refueling_fault_count 1
refueling_abort_count 1
refueling_gate_open 0
refueling_controller_health 1
```

Recovery to the reset scenario produces:

```text
refueling_pressure 40
refueling_fault_count 0
refueling_abort_count 0
refueling_controller_health 1
```

## What Was Not Completed

The following items were intentionally deferred:

- Persistent long-running controller process
- Continuous background telemetry streaming
- Dedicated telemetry-timeout simulation
- Real timestamp-based stale telemetry detection
- Alertmanager integration
- Automated alert rules
- MQTT or other pub/sub telemetry
- Kubernetes deployment
- AWS deployment
- Real hardware integration

## Current Technical Limitations

- A new controller process is started for every Prometheus scrape
- The active scenario is replayed for every scrape
- Only the final telemetry sample is exported
- Fault and abort metrics are state indicators, not cumulative counters
- Telemetry age is currently simplified
- Recovery requires changing configuration and restarting the service
- The platform is software-in-the-loop only

## Sprint Result

Sprint 1 successfully delivered a functioning local observability MVP.

The project now demonstrates:

- Deterministic C safety logic
- Python subprocess integration
- Telemetry parsing
- Prometheus metrics
- Grafana visualization
- Docker Compose deployment
- Controlled incident simulation
- Incident runbooks
- Agile-style project tracking

## Next Sprint Priorities

1. Replace per-scrape process creation with a persistent simulator process
2. Add a continuous background telemetry reader
3. Track telemetry timestamps and calculate real telemetry age
4. Add alert rules for:
   - Pressure high
   - Telemetry timeout
   - Controller unhealthy
5. Add automated scenario tests
6. Prepare for event-driven telemetry using MQTT or another pub/sub mechanism
