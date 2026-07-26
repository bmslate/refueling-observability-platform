import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, Gauge, generate_latest
import uvicorn

from simulator_client import PersistentSimulatorProcess


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

SUPPORTED_SCENARIOS = {
    "reset",
    "pressure_high",
}


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


# One shared simulator object belongs to this FastAPI process.
#
# lifespan() starts its C controller once when FastAPI starts and stops that
# same controller once when FastAPI shuts down.
PERSISTENT_SIMULATOR = PersistentSimulatorProcess()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    Manage the C controller for the complete FastAPI service lifetime.

    Startup:
        Validate the configured scenario and start one controller process.

    Shutdown:
        Stop the same controller process safely.

    Safety boundary:
    - Python supervises the process and sends controlled simulator commands.
    - Deterministic safety decisions remain inside controller.c.
    """
    if SIMULATOR_SCENARIO not in SUPPORTED_SCENARIOS:
        supported_values = ", ".join(sorted(SUPPORTED_SCENARIOS))
        raise RuntimeError(
            "Unsupported SIMULATOR_SCENARIO: "
            f"{SIMULATOR_SCENARIO!r}. "
            f"Supported values are: {supported_values}."
        )

    PERSISTENT_SIMULATOR.start()

    print(
        "Persistent C controller started. "
        f"PID={PERSISTENT_SIMULATOR.pid}"
    )

    try:
        yield
    finally:
        previous_pid = PERSISTENT_SIMULATOR.pid
        PERSISTENT_SIMULATOR.stop()

        print(
            "Persistent C controller stopped. "
            f"Previous PID={previous_pid}"
        )


app = FastAPI(
    title="Refueling Safety Telemetry Monitor",
    version="0.5.0",
    lifespan=lifespan,
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
    "Controller process health: 1 means running, 0 means unavailable",
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
    Execute the selected scenario through the existing controller process.

    reset:
        Sends RESET and returns safe-state telemetry.

    pressure_high:
        Executes a valid refueling sequence, injects pressure=90, and returns
        the ABORT telemetry produced by controller.c.

    Important:
    - This function does not create or terminate the controller process.
    - The scenario is still replayed for every /metrics scrape.
    - Background telemetry collection and caching belong to later Sprint 2
      issues.
    """
    if not PERSISTENT_SIMULATOR.is_running():
        raise RuntimeError("Persistent controller process is not running.")

    if SIMULATOR_SCENARIO == "reset":
        return PERSISTENT_SIMULATOR.send_command("RESET")

    if SIMULATOR_SCENARIO == "pressure_high":
        return PERSISTENT_SIMULATOR.send_commands(PRESSURE_HIGH_COMMANDS)

    # lifespan() validates the value during startup. This defensive branch
    # protects direct function calls in tests or future refactors.
    raise RuntimeError(
        "Unsupported SIMULATOR_SCENARIO reached telemetry collection: "
        f"{SIMULATOR_SCENARIO!r}"
    )


def update_metrics_from_simulator() -> None:
    """
    Collect final telemetry from the selected scenario and update Gauges.

    Current Sprint 2 Issue 1 flow:

        FastAPI-owned persistent controller
            ->
        selected scenario commands
            ->
        controller.c safety logic
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

        # Telemetry is collected synchronously during this scrape, so its age
        # is effectively zero here. A real continuously increasing telemetry
        # age will be implemented with the later background-cache work.
        refueling_telemetry_age_seconds.set(0)

    except Exception:
        refueling_controller_health.set(0)
        raise


@app.get("/health")
def health_check() -> dict[str, object]:
    """
    Report FastAPI availability and persistent controller process status.

    Process health and safety state are different concepts. A running
    controller can still report a safety fault such as PRESSURE_OUT_OF_RANGE.
    """
    controller_running = PERSISTENT_SIMULATOR.is_running()

    return {
        "status": "ok" if controller_running else "degraded",
        "simulator_scenario": SIMULATOR_SCENARIO,
        "controller_running": controller_running,
        "controller_pid": PERSISTENT_SIMULATOR.pid,
    }


@app.get("/metrics")
def metrics() -> Response:
    """
    Expose Prometheus-compatible metrics using the persistent controller.

    Current limitation:
    - The controller process is persistent across scrapes.
    - The selected scenario is still replayed for every scrape.
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
