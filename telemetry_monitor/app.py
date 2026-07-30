import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Response
from prometheus_client import CONTENT_TYPE_LATEST, Gauge, generate_latest
import uvicorn

from simulator_client import PersistentSimulatorProcess, TelemetrySample


# Select the controlled software-in-the-loop scenario used to initialize the
# latest telemetry cache when FastAPI starts.
#
# Supported values:
#   reset
#   pressure_high
#
# Docker Compose can override this with:
#   SIMULATOR_SCENARIO=pressure_high
#
# The default remains reset so the service starts from a safe scenario.
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


def run_initial_scenario() -> None:
    """
    Execute the configured simulator scenario once during FastAPI startup.

    The background telemetry reader parses the resulting TLM lines and updates
    the latest telemetry cache. Prometheus scrapes do not execute scenarios.
    """
    if not PERSISTENT_SIMULATOR.is_running():
        raise RuntimeError("Persistent controller process is not running.")

    if SIMULATOR_SCENARIO == "reset":
        PERSISTENT_SIMULATOR.send_command("RESET")
        return

    if SIMULATOR_SCENARIO == "pressure_high":
        PERSISTENT_SIMULATOR.send_commands(PRESSURE_HIGH_COMMANDS)
        return

    # The lifespan function validates the value before calling this function.
    raise RuntimeError(
        "Unsupported SIMULATOR_SCENARIO reached initialization: "
        f"{SIMULATOR_SCENARIO!r}"
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    Manage the C controller for the complete FastAPI service lifetime.

    Startup:
        1. Validate the configured scenario.
        2. Start one persistent controller process.
        3. Run the configured scenario once.
        4. Verify that the latest telemetry cache was populated.

    Shutdown:
        Stop the same controller process and reader thread safely.

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

    try:
        run_initial_scenario()

        initial_sample = PERSISTENT_SIMULATOR.get_latest_telemetry()

        if initial_sample is None:
            raise RuntimeError(
                "The initial simulator scenario completed without populating "
                "the latest telemetry cache."
            )

        print(
            "Persistent C controller started and telemetry cache initialized. "
            f"PID={PERSISTENT_SIMULATOR.pid}, "
            f"scenario={SIMULATOR_SCENARIO}, "
            f"sequence={initial_sample.sequence}"
        )

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
    version="0.6.0",
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


def update_metrics_from_cache(sample: TelemetrySample) -> None:
    """
    Update Prometheus Gauges from one cached telemetry sample.

    This function does not send controller commands and does not consume the
    telemetry observation queue.
    """
    telemetry = sample.telemetry

    refueling_alignment.set(float(telemetry["ALIGN"]))
    refueling_pressure.set(float(telemetry["PRESSURE"]))
    refueling_fuel_level.set(float(telemetry["FUEL"]))
    refueling_docked.set(float(telemetry["DOCK"]))

    refueling_gate_open.set(convert_gate_to_number(telemetry["GATE"]))
    refueling_fault_count.set(convert_fault_to_count(telemetry["FAULT"]))
    refueling_abort_count.set(1 if telemetry["STATE"] == "ABORT" else 0)

    refueling_controller_health.set(
        1 if PERSISTENT_SIMULATOR.is_running() else 0
    )

    # Real telemetry age will be calculated from received_monotonic in Issue 4.
    refueling_telemetry_age_seconds.set(0)


@app.get("/health")
def health_check() -> dict[str, object]:
    """
    Report FastAPI, controller, reader, and telemetry-cache status.

    Process health, telemetry availability, and controller safety state are
    intentionally reported as separate concepts.
    """
    controller_running = PERSISTENT_SIMULATOR.is_running()
    reader_running = PERSISTENT_SIMULATOR.reader_thread_alive
    latest_sample = PERSISTENT_SIMULATOR.get_latest_telemetry()
    telemetry_available = latest_sample is not None
    reader_failure = PERSISTENT_SIMULATOR.reader_failure

    healthy = (
        controller_running
        and reader_running
        and telemetry_available
        and reader_failure is None
    )

    return {
        "status": "ok" if healthy else "degraded",
        "simulator_scenario": SIMULATOR_SCENARIO,
        "controller_running": controller_running,
        "controller_pid": PERSISTENT_SIMULATOR.pid,
        "reader_running": reader_running,
        "reader_failure": reader_failure,
        "telemetry_available": telemetry_available,
        "telemetry_sequence": (
            latest_sample.sequence if latest_sample is not None else None
        ),
    }


@app.get("/metrics")
def metrics() -> Response:
    """
    Expose Prometheus-compatible metrics from the latest telemetry cache.

    Prometheus scrapes do not:
    - start or restart the controller
    - send RESET
    - replay the pressure-high sequence
    - consume telemetry observation events
    """
    controller_running = PERSISTENT_SIMULATOR.is_running()
    refueling_controller_health.set(1 if controller_running else 0)

    latest_sample = PERSISTENT_SIMULATOR.get_latest_telemetry()

    if latest_sample is None:
        raise HTTPException(
            status_code=503,
            detail="Latest controller telemetry is not available.",
        )

    try:
        update_metrics_from_cache(latest_sample)
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Latest controller telemetry is invalid: {exc}",
        ) from exc

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
