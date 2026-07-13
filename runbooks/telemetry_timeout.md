# Telemetry Timeout Incident Runbook

## Incident Type

Telemetry collection timeout or telemetry-monitor communication failure.

## Purpose

This runbook describes how to detect, investigate, and recover when the
Refueling Safety Observability Platform cannot obtain fresh telemetry from the
C refueling controller simulator.

The current platform is a software-in-the-loop portfolio environment. It does
not represent telemetry from real spacecraft hardware.

## Expected Normal Behavior

Under normal operation:

- The telemetry-monitor service starts the C controller process.
- The selected simulator scenario is sent to the controller.
- Controller `TLM` output is read and parsed.
- The FastAPI `/metrics` endpoint returns Prometheus-compatible metrics.
- Prometheus scrapes the telemetry-monitor every 5 seconds.
- The Prometheus target remains `UP`.
- Grafana displays current telemetry values.

Normal service endpoints:

```text
http://localhost:8000/health
http://localhost:8000/metrics
http://localhost:9090/targets
http://localhost:3000
```

## Possible Symptoms

A telemetry timeout or collection failure may appear as one or more of the
following:

- The `/metrics` endpoint returns an error.
- The `/metrics` request hangs or responds slowly.
- The `/health` endpoint reports a failure.
- `refueling_controller_health` becomes `0`.
- The Prometheus telemetry-monitor target becomes `DOWN`.
- Grafana panels show `No data`.
- Grafana values stop changing.
- Telemetry age increases after a real timestamp-based age calculation is implemented.
- Docker logs show subprocess, pipe, parsing, or timeout errors.

## Detection

### 1. Check the Health Endpoint

Open:

```text
http://localhost:8000/health
```

Expected healthy response:

```json
{
  "status": "ok",
  "simulator_scenario": "reset"
}
```

The selected scenario may also be `pressure_high`.

If the endpoint is unavailable or returns an error, investigate the
telemetry-monitor service.

### 2. Check the Metrics Endpoint

Open:

```text
http://localhost:8000/metrics
```

Expected behavior:

- The endpoint responds without a long delay.
- Refueling metrics are present.
- `refueling_controller_health` is `1`.

Example:

```text
refueling_controller_health 1.0
```

Possible failure indicator:

```text
refueling_controller_health 0.0
```

### 3. Check the Prometheus Target

Open:

```text
http://localhost:9090/targets
```

Expected status:

```text
UP
```

A `DOWN` target indicates that Prometheus cannot successfully scrape the
telemetry-monitor.

### 4. Check Grafana

Open:

```text
http://localhost:3000
```

Possible timeout symptoms:

- Controller Health is unhealthy.
- Panels display `No data`.
- Pressure and alignment graphs stop receiving new samples.
- The most recent values remain stale.

## Investigation Steps

### 1. Check Docker Service Status

From the repository root, run:

```powershell
docker compose ps
```

Confirm that these services are running:

```text
refueling-telemetry-monitor
refueling-prometheus
refueling-grafana
```

### 2. Check Telemetry-Monitor Logs

```powershell
docker compose logs telemetry-monitor
```

Look for:

- `TimeoutError`
- `subprocess.TimeoutExpired`
- broken pipe errors
- controller executable errors
- telemetry parse errors
- missing telemetry output
- invalid scenario configuration
- FastAPI exceptions

For recent logs only:

```powershell
docker compose logs --tail 100 telemetry-monitor
```

### 3. Confirm the Active Scenario

```powershell
docker exec refueling-telemetry-monitor printenv SIMULATOR_SCENARIO
```

Expected values:

```text
reset
```

or:

```text
pressure_high
```

An unsupported value may cause telemetry collection to fail.

### 4. Verify the Controller Executable

```powershell
docker exec refueling-telemetry-monitor ls -l /controller/controller
```

The file should exist and be executable.

### 5. Test the Simulator Client Directly

```powershell
docker exec refueling-telemetry-monitor python simulator_client.py
```

Expected result:

- Parsed telemetry is printed.
- The command finishes without hanging.
- No timeout or parsing exception is raised.

### 6. Test the Controller Manually

```powershell
docker exec -it refueling-telemetry-monitor /controller/controller
```

Then enter:

```text
RESET
GET_STATUS
```

Expected result:

- The controller acknowledges the command.
- A valid `TLM` line is emitted.

Exit the controller after verification.

### 7. Check Prometheus Logs

```powershell
docker compose logs prometheus
```

Look for scrape errors involving:

```text
telemetry-monitor
host.docker.internal
localhost:8000
```

Use the hostname that matches the current Prometheus configuration.

### 8. Check Network Reachability

From the Prometheus container, test the metrics endpoint using an available
HTTP client.

Example when `wget` is available:

```powershell
docker exec refueling-prometheus wget -qO- http://host.docker.internal:8000/metrics
```

If the Compose configuration uses the service name instead:

```powershell
docker exec refueling-prometheus wget -qO- http://telemetry-monitor:8000/metrics
```

## Safe Recovery

### Recovery Option 1: Restart the Telemetry Monitor

```powershell
docker compose restart telemetry-monitor
```

Wait for the service to start, then check:

```text
http://localhost:8000/health
http://localhost:8000/metrics
```

### Recovery Option 2: Rebuild the Telemetry Monitor

Use this when controller code, Python code, dependencies, or the Docker image
may be stale.

```powershell
docker compose up -d --build telemetry-monitor
```

### Recovery Option 3: Restart the Full Stack

```powershell
docker compose down
docker compose up -d --build
```

This restarts telemetry-monitor, Prometheus, and Grafana.

### Recovery Option 4: Return to the Reset Scenario

In `docker-compose.yml`, set:

```yaml
SIMULATOR_SCENARIO: "reset"
```

Then run:

```powershell
docker compose up -d --build
```

This provides the simplest known-good simulator path.

## Recovery Verification

Confirm all of the following:

1. Docker services are running:

```powershell
docker compose ps
```

2. Health endpoint responds:

```text
http://localhost:8000/health
```

3. Metrics endpoint responds:

```text
http://localhost:8000/metrics
```

4. Controller health is healthy:

```text
refueling_controller_health 1.0
```

5. Prometheus target is:

```text
UP
```

6. Grafana panels show telemetry again.

For the reset scenario, expected values include:

```text
refueling_alignment 85.0
refueling_pressure 40.0
refueling_fault_count 0.0
refueling_abort_count 0.0
refueling_controller_health 1.0
```

## Escalation and Follow-Up

If recovery fails:

- Save telemetry-monitor logs.
- Save Prometheus target error details.
- Record the active simulator scenario.
- Record the exact command that caused the failure.
- Record whether the controller executable runs manually.
- Create a GitHub Issue with reproduction steps.
- Add screenshots or log excerpts to the issue.
- Link the issue to the current sprint or milestone.

Suggested issue title:

```text
Incident: Telemetry collection timeout
```

## Current Limitations

- The current implementation starts a new C controller process for each
  Prometheus scrape.
- The selected scenario is replayed for each scrape.
- A persistent background controller process is not yet implemented.
- Continuous telemetry streaming is not yet implemented.
- Telemetry age is currently simplified and does not yet provide full stale-data detection.
- A dedicated timeout simulation switch is not yet implemented.
- Alertmanager and automated timeout alerts are not yet configured.
- This runbook currently covers service-level and subprocess-level timeout
  investigation in the local software-in-the-loop environment.
