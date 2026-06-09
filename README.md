# Refueling Safety Observability Platform

This project extends my original **Spacecraft Refueling Safety Simulation** into a cloud-style observability and incident-response platform.

The goal is to demonstrate how an embedded safety-control system can be monitored, visualized, containerized, and gradually extended toward Cloud SRE practices using telemetry, Prometheus, Grafana, Docker, incident runbooks, and an Agile-style GitHub workflow.

## Project Status

Current stage: **MVP Phase 1 - Local Observability**

This MVP version focuses on building the local observability foundation:

* C-based refueling controller source code
* Python telemetry monitor/exporter
* Health endpoint
* Prometheus-compatible metrics endpoint
* Prometheus scraping
* Grafana dashboard
* Docker Compose local deployment
* Basic incident runbooks
* GitHub Issues and sprint-style milestones

Future versions will add MQTT/pub-sub telemetry, AWS deployment, Kubernetes troubleshooting, Go-based health checks, and optional AI-assisted incident triage.

---

## Project Background

The original project was a spacecraft refueling safety simulation built around a C-based controller and Python-based supervision logic. It focused on deterministic state transitions, telemetry output, fault detection, and safety abort behavior.

This new project reuses the original refueling controller concept and extends it into an observability platform that is closer to real-world Cloud SRE and platform reliability workflows.

---

## Planned MVP Architecture

```text
C Refueling Controller / Simulator
        ↓ telemetry output

Python Telemetry Monitor / Exporter
        ↓ health + metrics endpoints

Prometheus
        ↓ scrape metrics

Grafana Dashboard
        ↓ visualize system status
```

---

## Long-Term Architecture

```text
C Refueling Controller / Simulator
        ↓ telemetry output

Python Telemetry Monitor / Exporter
        ↓ metrics + events

Prometheus + Grafana
        ↓ monitoring and visualization

MQTT / Pub-Sub Broker
        ↓ event-driven telemetry

Incident Processor
        ↓ alert and incident workflow

AWS EC2 / S3 / CloudWatch / Lambda / SNS
        ↓ cloud deployment and incident automation

Kubernetes
        ↓ cloud-native deployment and troubleshooting

Optional Go Health Service
        ↓ liveness/readiness/metrics endpoints

Optional AI Incident Triage Agent
        ↓ log summary, runbook lookup, postmortem draft
```

---

## Tech Stack

### Current MVP

* C
* Python
* Docker
* Docker Compose
* Prometheus
* Grafana
* Git / GitHub

### Planned Extensions

* MQTT / Pub-Sub
* AWS EC2
* AWS S3
* AWS CloudWatch
* AWS Lambda
* AWS SNS
* Kubernetes
* Go
* AI-assisted incident triage

---

## Repository Structure

```text
refueling-observability-platform/
├── controller/
│   └── controller.c
├── telemetry_monitor/
├── prometheus/
├── grafana/
├── docs/
│   ├── sprint_reviews/
│   └── retrospectives/
├── runbooks/
├── incidents/
├── diagrams/
├── docker-compose.yml
├── .gitignore
└── README.md
```

---

## MVP Scope

The first MVP version will include:

* Importing the original C refueling controller
* Creating a Python telemetry exporter
* Adding `/health` endpoint
* Adding `/metrics` endpoint
* Exposing Prometheus-compatible metrics
* Configuring Prometheus to scrape telemetry data
* Building a Grafana dashboard
* Running the local stack with Docker Compose
* Writing basic incident runbooks
* Managing development through GitHub Issues and sprint-style milestones

---

## Planned Metrics

The MVP will expose metrics such as:

```text
refueling_pressure
refueling_alignment
refueling_fuel_level
refueling_fault_count
refueling_abort_count
refueling_controller_health
refueling_telemetry_age_seconds
```

These metrics will be used to monitor the simulated controller state and visualize system behavior in Grafana.

---

## Planned Endpoints

The telemetry monitor will provide:

```text
GET /health
GET /metrics
```

### Example `/health` Response

```json
{
  "status": "ok"
}
```

### Example `/metrics` Output

```text
refueling_pressure 40
refueling_alignment 95
refueling_fuel_level 20
refueling_fault_count 0
refueling_abort_count 0
```

---

## Incident Runbooks

The MVP will include basic runbooks for simulated operational issues.

Planned runbooks:

```text
runbooks/
├── pressure_high.md
└── telemetry_timeout.md
```

Each runbook will include:

* Symptoms
* Detection method
* Metrics to check
* Logs to check
* Recovery steps
* Verification steps

---

## Agile-Style Workflow

This is a personal portfolio project, so it does **not** claim to use a full company-level Scrum process.

Development is managed using **GitHub Issues, GitHub Projects, and sprint-style milestones** to simulate an Agile workflow, including:

* Feature tickets
* Bug reports
* Incident tasks
* Documentation tasks
* Sprint reviews
* Retrospectives
* Issue-to-commit tracking

Recommended wording:

```text
Managed development using GitHub Issues, Projects, and sprint-style milestones to simulate an Agile workflow, including feature tickets, bug reports, incident tasks, sprint reviews, and retrospectives.
```

---

## Sprint Plan

### Sprint 1 - Local Observability Foundation

Goal:

* Set up project structure
* Import C controller
* Create Python telemetry exporter
* Add health and metrics endpoints
* Prepare Prometheus and Grafana structure
* Create initial documentation

### Sprint 2 - Prometheus and Grafana MVP

Goal:

* Configure Prometheus scraping
* Build Grafana dashboard
* Visualize pressure, alignment, fuel level, fault count, and abort count
* Add screenshots and documentation

### Sprint 3 - Docker Compose MVP

Goal:

* Containerize telemetry monitor
* Add Prometheus and Grafana to Docker Compose
* Run the local observability stack with one command
* Add basic incident runbooks

---

## Future Roadmap

### Phase 2 - Event-Driven Telemetry

Planned additions:

* MQTT broker
* Telemetry publisher
* Telemetry consumer
* Pub/sub topics
* Incident event messages
* Alert scenarios

Example topics:

```text
refueling/telemetry
refueling/faults
refueling/alerts
refueling/status
```

### Phase 3 - AWS Incident Workflow

Planned additions:

* AWS EC2 deployment
* S3 telemetry archive
* CloudWatch log review
* Lambda incident parser
* SNS alert workflow

### Phase 4 - Kubernetes and Go Add-On

Planned additions:

* Kubernetes manifests
* Pod failure simulation
* kubectl troubleshooting documentation
* Go health-check service
* `/health`, `/ready`, and `/metrics`
* livenessProbe and readinessProbe

### Phase 5 - AI Incident Triage Agent

Planned additions:

* AI-assisted log summary
* Incident classification
* Runbook lookup
* Metrics snapshot interpretation
* Postmortem drafting

Important boundary:

The AI Agent will not control the refueling system or make safety-critical decisions. All safety-critical behavior remains deterministic and manually verified.

---

## AI-Assisted Workflow Boundary

AI tools may be used to support:

* Code explanation
* Debugging strategy
* Test-case planning
* Log summarization
* Incident summary drafting
* Runbook drafting
* Documentation improvement

AI tools are used only as support tools. All code behavior and system results must be manually verified through builds, logs, metrics, dashboards, and repeatable test scenarios.

---

## Safety Boundary

The refueling safety controller is designed around deterministic logic.

Safety-related decisions such as abort behavior, fault detection, and state transitions are handled by the controller and monitoring logic, not by AI-generated decisions.

This project is a portfolio simulation and is not intended for real spacecraft operation.

---

## Related Project

This project builds on my previous **Spacecraft Refueling Safety Simulation**, reusing the original C-based controller concept and extending it with telemetry monitoring, observability, incident-response workflows, and cloud-native reliability practices.

---

## Current Development Stage

Current focus:

```text
MVP Phase 1 - Local Observability
```

Immediate next steps:

1. Import the original `controller.c`
2. Create the Python telemetry monitor
3. Add `/health`
4. Add `/metrics`
5. Configure Prometheus
6. Build Grafana dashboard
7. Run the stack with Docker Compose
8. Document the MVP with screenshots and runbooks

```
```
