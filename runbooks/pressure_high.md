# Pressure High Incident Runbook

## Incident Type

Controlled software-in-the-loop pressure-high incident.

## Purpose

This runbook describes how to detect, investigate, and verify a simulated refueling pressure fault in the Refueling Safety Observability Platform.

The scenario uses the C controller simulator. It does not represent telemetry from real spacecraft hardware.

## Safety Threshold

The deterministic C controller defines the safe pressure range as:

```text
Minimum safe pressure: 20
Maximum safe pressure: 80
```

A pressure value outside this range is considered unsafe.

## Simulated Trigger

The controlled incident scenario injects:

```text
SIM_PRESSURE 90
```

The test command sequence is:

```text
RESET
START_APPROACH
CHECK_ALIGNMENT
LOCK_DOCK
OPEN_GATE
CHECK_PRESSURE
START_REFUEL
SIM_PRESSURE 90
```

## Expected Controller Response

Expected response:

```text
ACK,ABORT_ENTERING_SAFE_MODE,CAUSE=PRESSURE_OUT_OF_RANGE
```

Expected telemetry:

```text
TLM,STATE=ABORT,ALIGN=85,PRESSURE=90,FUEL=0,DOCK=1,GATE=CLOSED,FAULT=PRESSURE_OUT_OF_RANGE
```

Expected event log entry:

```text
ABORT_PRESSURE_OUT_OF_RANGE
```

## Detection

FastAPI metrics endpoint:

```text
http://localhost:8000/metrics
```

Expected metrics:

```text
refueling_pressure 90.0
refueling_fault_count 1.0
refueling_abort_count 1.0
refueling_gate_open 0.0
refueling_controller_health 1.0
```

Prometheus targets:

```text
http://localhost:9090/targets
```

The telemetry-monitor target should remain `UP`.

Grafana dashboard:

```text
http://localhost:3000
```

Expected dashboard indicators:

- Controller Health: HEALTHY
- Fault Count: 1
- Abort Count: 1
- Refueling Pressure: 90
- Alignment: 85
- Telemetry Age: 0

## Investigation Steps

1. Confirm the active simulator scenario:

```powershell
docker exec refueling-telemetry-monitor printenv SIMULATOR_SCENARIO
```

Expected result:

```text
pressure_high
```

2. Check service status:

```powershell
docker compose ps
```

3. Check telemetry-monitor logs:

```powershell
docker compose logs telemetry-monitor
```

4. Check Prometheus target status:

```text
http://localhost:9090/targets
```

5. Verify metrics:

```text
http://localhost:8000/metrics
```

## Safe Recovery

Change `docker-compose.yml` from:

```yaml
SIMULATOR_SCENARIO: "pressure_high"
```

to:

```yaml
SIMULATOR_SCENARIO: "reset"
```

Rebuild and restart:

```powershell
docker compose up -d --build
```

Wait for Prometheus and Grafana to refresh.

## Recovery Verification

Expected reset metrics:

```text
refueling_pressure 40.0
refueling_fault_count 0.0
refueling_abort_count 0.0
refueling_gate_open 0.0
refueling_controller_health 1.0
```

Expected Grafana state:

- Controller Health: HEALTHY
- Fault Count: 0
- Abort Count: 0
- Refueling Pressure: 40
- Alignment: 85

## Evidence

Pressure-high scenario:

```text
docs/images/grafana_simulator_mode_dashboard_PRESSURE_HIGH.png
```

Recovered reset scenario:

```text
docs/images/grafana_simulator_mode_dashboard_RESET.png
```

## Current Limitations

- A new C controller process is started for every Prometheus scrape.
- The selected scenario is replayed during every scrape.
- Continuous background telemetry streaming is not yet implemented.
- The abort metric is currently a state indicator, not a cumulative event count.
- The scenario is software-in-the-loop simulation, not real hardware telemetry.
- Recovery requires changing configuration and restarting the Docker service.
