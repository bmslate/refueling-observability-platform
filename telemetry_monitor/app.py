from fastapi import FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, Gauge, generate_latest
import uvicorn

app = FastAPI(
    title="Refueling Safety Telemetry Monitor",
    version="0.2.0",
)

# Demo values for the first Prometheus integration step.
# Later these values will come from live C controller telemetry.
refueling_alignment = Gauge(
    "refueling_alignment",
    "Current spacecraft alignment value",
)

refueling_pressure = Gauge(
    "refueling_pressure",
    "Current refueling line pressure value",
)

refueling_fuel_level = Gauge(
    "refueling_fuel_level",
    "Current fuel transfer level",
)

refueling_docked = Gauge(
    "refueling_docked",
    "Docking status: 1 means docked, 0 means not docked",
)

refueling_gate_open = Gauge(
    "refueling_gate_open",
    "Gate status: 1 means open, 0 means closed",
)

refueling_fault_count = Gauge(
    "refueling_fault_count",
    "Number of detected controller faults",
)

refueling_abort_count = Gauge(
    "refueling_abort_count",
    "Number of safety abort events",
)

refueling_controller_health = Gauge(
    "refueling_controller_health",
    "Controller health: 1 means healthy, 0 means unhealthy",
)

refueling_telemetry_age_seconds = Gauge(
    "refueling_telemetry_age_seconds",
    "Age of the latest telemetry sample in seconds",
)


def update_demo_metrics() -> None:
    """Set demo values until live controller telemetry is connected."""
    refueling_alignment.set(85)
    refueling_pressure.set(40)
    refueling_fuel_level.set(0)
    refueling_docked.set(0)
    refueling_gate_open.set(0)
    refueling_fault_count.set(0)
    refueling_abort_count.set(0)
    refueling_controller_health.set(1)
    refueling_telemetry_age_seconds.set(0)


@app.get("/health")
def health_check() -> dict[str, str]:
    """Confirm that the telemetry monitor service is running."""
    return {"status": "ok"}


@app.get("/metrics")
def metrics() -> Response:
    """Expose Prometheus-compatible refueling telemetry metrics."""
    update_demo_metrics()

    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


# if __name__ == "__main__":
#     uvicorn.run(
#         "app:app",
#         host="127.0.0.1",
#         port=8000,
#         reload=True,
#     )
if __name__ == "__main__":
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8000,
    )