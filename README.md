# Refueling Safety Observability Platform

A portfolio project that extends a C-based **Spacecraft Refueling Safety Simulation** into a local observability platform.

The project demonstrates how a deterministic safety-control system can be monitored through telemetry, Prometheus metrics, Grafana dashboards, Docker containers, incident runbooks, and an Agile-style GitHub workflow.

> This is a portfolio simulation only. It is not intended for real spacecraft operation.

---

## Current Status

**Current stage: MVP Phase 1 — Local Observability**

### Completed

- Imported and validated the original C-based refueling controller
- Created a Python FastAPI telemetry monitor
- Added a `GET /health` endpoint
- Added a Prometheus-compatible `GET /metrics` endpoint
- Created refueling safety metrics with `prometheus-client`
- Configured Prometheus to scrape telemetry every 5 seconds
- Verified the Prometheus target is healthy and queryable
- Built a Grafana dashboard for controller-health and telemetry visualization
- Exported the Grafana dashboard JSON
- Used GitHub Issues, Projects, and sprint-style milestones to track development

### In Progress

- Docker Compose deployment for the full local stack
- Connecting the Python monitor to controller-generated telemetry
- More realistic refueling-state simulation data
- Incident runbooks and alert rules

---

## Project Background

The original project was a spacecraft refueling safety simulation built around a C-based controller and Python-based supervision logic.

It focused on deterministic state transitions, telemetry output, fault detection, and safety abort behavior.

This project reuses that controller concept and extends it into an observability platform closer to real-world Cloud SRE and platform reliability workflows.

---

## Current MVP Architecture

```text
Current implementation

Demo telemetry values
        ↓
Python FastAPI Telemetry Monitor
        ├── GET /health
        └── GET /metrics
                  ↓
Prometheus
        ├── Scrapes metrics every 5 seconds
        └── Stores time-series telemetry data
                  ↓
Grafana Dashboard
        ├── Controller Health
        ├── Fault Count
        ├── Abort Count
        ├── Telemetry Age
        ├── Alignment Trend
        └── Refueling Pressure Trend
```

```text
Planned integration

C Refueling Controller / Simulator
        ↓
Telemetry parsing / exporting layer
        ↓
Python FastAPI Telemetry Monitor
        ↓
Prometheus + Grafana
```

> The current telemetry monitor exports controlled demo values. Connecting it to controller-generated telemetry is planned work.

---

## Current Technology Stack

- C
- Python
- FastAPI
- `prometheus-client`
- Prometheus
- Grafana
- Docker
- Git / GitHub

### Planned Extensions

- Docker Compose
- MQTT / Pub-Sub telemetry
- AWS EC2, S3, CloudWatch, Lambda, and SNS
- Kubernetes
- Go health-check service
- Optional AI-assisted incident triage

---

## Implemented Endpoints

The Python telemetry monitor currently provides:

```text
GET /health
GET /metrics
```

### Health Endpoint

```text
http://127.0.0.1:8000/health
```

Example response:

```json
{
  "status": "ok"
}
```

### Metrics Endpoint

```text
http://127.0.0.1:8000/metrics
```

The endpoint exposes Prometheus-compatible metrics.

Example output:

```text
refueling_alignment 85.0
refueling_pressure 40.0
refueling_fuel_level 0.0
refueling_docked 0.0
refueling_gate_open 0.0
refueling_fault_count 0.0
refueling_abort_count 0.0
refueling_controller_health 1.0
refueling_telemetry_age_seconds 0.0
```

---

## Implemented Metrics

| Metric | Description |
|---|---|
| `refueling_alignment` | Simulated spacecraft-to-tanker alignment value |
| `refueling_pressure` | Simulated refueling line pressure |
| `refueling_fuel_level` | Simulated transferred fuel level |
| `refueling_docked` | Docked state indicator |
| `refueling_gate_open` | Refueling gate state indicator |
| `refueling_fault_count` | Number of detected safety faults |
| `refueling_abort_count` | Number of safety abort events |
| `refueling_controller_health` | Controller health state: `1 = healthy`, `0 = unhealthy` |
| `refueling_telemetry_age_seconds` | Age of the most recent telemetry update |

---

## Prometheus Integration

Prometheus scrapes the telemetry monitor every five seconds.

```text
Python FastAPI /metrics
        ↓
Prometheus scrape
        ↓
Time-series storage
        ↓
Prometheus query interface
        ↓
Grafana visualization
```

Current Prometheus target configuration:

```yaml
global:
  scrape_interval: 5s

scrape_configs:
  - job_name: "refueling-telemetry-monitor"
    static_configs:
      - targets:
          - "host.docker.internal:8000"
```

Prometheus has been verified to:

- Reach the FastAPI `/metrics` endpoint
- Report the telemetry-monitor target as `UP`
- Query refueling metrics such as `refueling_pressure` and `refueling_alignment`
- Store metric history for time-series visualization

---

## Grafana Dashboard

The Grafana dashboard currently visualizes the health and telemetry state of the refueling simulation.

Dashboard panels include:

- Controller Health
- Fault Count
- Abort Count
- Telemetry Age
- Alignment Trend
- Refueling Pressure Trend

The exported dashboard definition is stored at:

```text
grafana/dashboards/refueling_safety_observability_dashboard.json
```

---

## Current Repository Structure

```text
refueling-observability-platform/
├── controller/
│   └── controller.c
├── telemetry_monitor/
│   ├── app.py
│   └── requirements.txt
├── prometheus/
│   └── prometheus.yml
├── grafana/
│   └── dashboards/
│       └── refueling_safety_observability_dashboard.json
├── docs/
│   └── images/
├── .gitignore
└── README.md
```

Planned additions include:

- `docker-compose.yml`
- `runbooks/`
- `incidents/`
- `diagrams/`
- `docs/sprint_reviews/`
- `docs/retrospectives/`

---

## Local Development Setup

### 1. Start the Python telemetry monitor

```powershell
cd telemetry_monitor
.\.venv\Scripts\Activate.ps1
python app.py
```

The telemetry monitor runs at:

```text
http://127.0.0.1:8000
```

Useful endpoints:

```text
http://127.0.0.1:8000/health
http://127.0.0.1:8000/metrics
http://127.0.0.1:8000/docs
```

### 2. Initial Prometheus Container Setup

From the repository root:

```powershell
docker run --name refueling-prometheus -p 9090:9090 `
  -v "${PWD}\prometheus\prometheus.yml:/etc/prometheus/prometheus.yml" `
  prom/prometheus
```

Open Prometheus:

```text
http://localhost:9090
```

### 3. Initial Grafana Container Setup

```powershell
docker run -d `
  --name refueling-grafana `
  -p 3000:3000 `
  grafana/grafana
```

Open Grafana:

```text
http://localhost:3000
```

Default first-login credentials:

```text
Username: admin
Password: admin
```

Grafana should use this Prometheus data source URL:

```text
http://host.docker.internal:9090
```

### 4. Start Existing Containers Later

After containers have already been created, start them with:

```powershell
docker start refueling-prometheus
docker start refueling-grafana
```

---

## MVP Scope

The current MVP includes:

- C controller source code
- Python FastAPI telemetry monitor
- Health endpoint
- Prometheus-compatible metrics endpoint
- Prometheus metric scraping
- Grafana dashboard
- Docker-based Prometheus and Grafana services
- GitHub Project Board and sprint-style workflow

Remaining MVP work:

- Docker Compose deployment
- Controller-to-monitor telemetry integration
- Incident runbooks
- Alert rules
- More realistic telemetry transitions

---

## Planned Incident Runbooks

Planned runbooks:

```text
runbooks/
├── pressure_high.md
└── telemetry_timeout.md
```

Each runbook will include:

- Symptoms
- Detection method
- Metrics to check
- Logs to check
- Recovery steps
- Verification steps

---

## Agile-Style Workflow

This is a personal portfolio project and does not claim to use a full company-level Scrum process.

Development is managed using GitHub Issues, GitHub Projects, and sprint-style milestones to simulate an Agile workflow.

The workflow includes:

- Feature tickets
- Bug reports
- Documentation tasks
- Incident tasks
- Sprint reviews
- Retrospectives
- Issue-to-commit tracking

Recommended wording:

```text
Managed development using GitHub Issues, Projects, and sprint-style milestones to simulate an Agile workflow, including feature tickets, bug reports, incident tasks, sprint reviews, and retrospectives.
```

---

## Future Roadmap

### Phase 2 — Event-Driven Telemetry

- MQTT broker
- Telemetry publisher and consumer
- Pub/sub topics
- Fault and alert events
- Incident event messages

Example topics:

```text
refueling/telemetry
refueling/faults
refueling/alerts
refueling/status
```

### Phase 3 — AWS Incident Workflow

- AWS EC2 deployment
- S3 telemetry archive
- CloudWatch log review
- Lambda incident parser
- SNS alert workflow

### Phase 4 — Kubernetes and Go Add-On

- Kubernetes manifests
- Pod failure simulation
- `kubectl` troubleshooting documentation
- Optional Go health-check service
- `/health`, `/ready`, and `/metrics`
- Liveness and readiness probes

### Phase 5 — AI Incident Triage Agent

- AI-assisted log summarization
- Incident classification
- Runbook lookup
- Metrics snapshot interpretation
- Postmortem drafting

---

## AI and Safety Boundaries

AI tools may support:

- Code explanation
- Debugging strategy
- Test-case planning
- Log summarization
- Incident summary drafting
- Runbook drafting
- Documentation improvement

AI tools do not make safety-critical decisions.

Abort behavior, fault detection, and state transitions remain deterministic and manually verified through builds, logs, metrics, dashboards, and repeatable test scenarios.

---

## Related Project

This project builds on my previous **Spacecraft Refueling Safety Simulation**, reusing the original C-based controller concept and extending it with telemetry monitoring, observability, incident-response workflows, and cloud-native reliability practices.
