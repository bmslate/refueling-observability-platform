import os

from fastapi import FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, Gauge, generate_latest
import uvicorn

from simulator_client import (
    get_simulator_telemetry,
    get_simulator_telemetry_sequence,
)


# Select the controlled software-in-the-loop scenario used by /metrics.
#
# Supported values:
#   reset
#   pressure_high
#
# Docker Compose can override this with:
#   SIMULATOR_SCENARIO=pressure_high
#
# The default remains reset so the service starts in a safe scenario.
SIMULATOR_SCENARIO = os.getenv("SIMULATOR_SCENARIO", "reset").strip().lower()


# Valid command sequence for the controlled pressure-high incident scenario.
#
# Python only sends simulator commands. controller.c performs the safety
# decision and enters ABORT when pressure exceeds its safe maximum.
PRESSURE_HIGH_COMMANDS = [
    "RESET",
    "START_APPROACH",
    "CHECK_ALIGNMENT",
    "LOCK_DOCK",
    "OPEN_GATE",
    "CHECK_PRESSURE",
    "START_REFUEL",
    "SIM_PRESSURE 90",
]


app = FastAPI(
    title="Refueling Safety Telemetry Monitor",
    version="0.4.0",
)


# -------------------------------------------------------------------
# Prometheus Gauges
# -------------------------------------------------------------------

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
    "Current controller fault indicator: 1 means active, 0 means none",
)

refueling_abort_count = Gauge(
    "refueling_abort_count",
    "Current abort indicator: 1 means controller state is ABORT",
)

refueling_controller_health = Gauge(
    "refueling_controller_health",
    "Controller health: 1 means healthy, 0 means unhealthy",
)

refueling_telemetry_age_seconds = Gauge(
    "refueling_telemetry_age_seconds",
    "Age of the latest telemetry sample in seconds",
)


def convert_gate_to_number(gate_value: str) -> int:
    """
    Convert the C controller gate text into a numeric Prometheus value.

    OPEN   -> 1
    CLOSED -> 0
    """
    return 1 if gate_value == "OPEN" else 0


def convert_fault_to_count(fault_value: str) -> int:
    """
    Convert the current C controller fault text into a numeric indicator.

    NONE            -> 0
    any other value -> 1
    """
    return 0 if fault_value == "NONE" else 1


def collect_scenario_telemetry() -> dict[str, str]:
    """
    Execute the selected simulator scenario and return final telemetry.

    reset:
        Sends RESET and returns safe-state telemetry.

    pressure_high:
        Executes a valid refueling sequence, injects pressure=90, and returns
        the ABORT telemetry produced by controller.c.
    """
    if SIMULATOR_SCENARIO == "reset":
        return get_simulator_telemetry("RESET")

    if SIMULATOR_SCENARIO == "pressure_high":
        return get_simulator_telemetry_sequence(PRESSURE_HIGH_COMMANDS)

    raise ValueError(
        "Unsupported SIMULATOR_SCENARIO: "
        f"{SIMULATOR_SCENARIO!r}. "
        "Supported values are 'reset' and 'pressure_high'."
    )


def update_metrics_from_simulator() -> None:
    """
    Collect final telemetry from the selected scenario and update Gauges.

    Current flow:

        selected scenario
            ->
        controller.c
            ->
        TLM telemetry
            ->
        simulator_client.py
            ->
        telemetry_parser.py
            ->
        Prometheus Gauges
            ->
        Grafana
    """
    try:
        telemetry = collect_scenario_telemetry()

        refueling_alignment.set(float(telemetry["ALIGN"]))
        refueling_pressure.set(float(telemetry["PRESSURE"]))
        refueling_fuel_level.set(float(telemetry["FUEL"]))
        refueling_docked.set(float(telemetry["DOCK"]))

        refueling_gate_open.set(convert_gate_to_number(telemetry["GATE"]))
        refueling_fault_count.set(convert_fault_to_count(telemetry["FAULT"]))
        refueling_abort_count.set(1 if telemetry["STATE"] == "ABORT" else 0)

        refueling_controller_health.set(1)
        refueling_telemetry_age_seconds.set(0)

    except Exception:
        refueling_controller_health.set(0)
        raise


@app.get("/health")
def health_check() -> dict[str, str]:
    """
    Confirm that the FastAPI telemetry-monitor service is running.
    """
    return {
        "status": "ok",
        "simulator_scenario": SIMULATOR_SCENARIO,
    }


@app.get("/metrics")
def metrics() -> Response:
    """
    Expose Prometheus-compatible metrics for the selected simulator scenario.

    Current limitation:
    - A new controller process is started for each scrape.
    - The selected scenario is replayed for every scrape.
    - Continuous background telemetry streaming is not yet implemented.
    """
    update_metrics_from_simulator()

    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
    )
