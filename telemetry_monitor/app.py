from fastapi import FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, Gauge, generate_latest
import uvicorn

# Import the reusable client that starts controller.exe,
# sends a command, receives one telemetry line, and returns
# parsed telemetry as a Python dictionary.
from simulator_client import get_simulator_telemetry


# Create the FastAPI application.
# FastAPI provides the /health and /metrics HTTP endpoints.
app = FastAPI(
    title="Refueling Safety Telemetry Monitor",
    version="0.3.0",
)


# -------------------------------------------------------------------
# Prometheus Gauges
# -------------------------------------------------------------------
# A Gauge stores the latest numeric value of one metric.
# Prometheus scrapes the /metrics endpoint and reads these values.
#
# Prometheus metrics must be numeric.
# Text values from the C controller such as GATE=CLOSED or FAULT=NONE
# need to be converted into numeric values before storing them here.


# Current spacecraft alignment value.
refueling_alignment = Gauge(
    "refueling_alignment",
    "Current spacecraft alignment value",
)

# Current refueling line pressure value.
refueling_pressure = Gauge(
    "refueling_pressure",
    "Current refueling line pressure value",
)

# Current fuel transfer level.
refueling_fuel_level = Gauge(
    "refueling_fuel_level",
    "Current fuel transfer level",
)

# Docking status:
# 1 = docked
# 0 = not docked
refueling_docked = Gauge(
    "refueling_docked",
    "Docking status: 1 means docked, 0 means not docked",
)

# Gate status:
# 1 = open
# 0 = closed
refueling_gate_open = Gauge(
    "refueling_gate_open",
    "Gate status: 1 means open, 0 means closed",
)

# Current fault indicator/count:
# 0 = no fault
# 1 = one fault condition detected
#
# This is intentionally simple for the MVP.
# Later it can be replaced with labels or detailed fault counters.
refueling_fault_count = Gauge(
    "refueling_fault_count",
    "Number of detected controller faults",
)

# Number of safety abort events.
#
# The current controller telemetry protocol does not expose
# a cumulative abort counter yet, so this remains 0 for now.
refueling_abort_count = Gauge(
    "refueling_abort_count",
    "Number of safety abort events",
)

# Controller health:
# 1 = simulator telemetry was successfully received
# 0 = simulator telemetry could not be collected
refueling_controller_health = Gauge(
    "refueling_controller_health",
    "Controller health: 1 means healthy, 0 means unhealthy",
)

# Age of the latest telemetry sample in seconds.
#
# In this current MVP, telemetry is collected during each /metrics request,
# so the newest sample is treated as 0 seconds old.
refueling_telemetry_age_seconds = Gauge(
    "refueling_telemetry_age_seconds",
    "Age of the latest telemetry sample in seconds",
)


def convert_gate_to_number(gate_value: str) -> int:
    """
    Convert the C controller's text gate state into a numeric metric.

    The C controller sends text such as:

        GATE=OPEN
        GATE=CLOSED

    Prometheus needs numbers, so this function maps:

        OPEN   -> 1
        CLOSED -> 0

    Any unexpected value is treated as closed for this MVP.
    """
    return 1 if gate_value == "OPEN" else 0


def convert_fault_to_count(fault_value: str) -> int:
    """
    Convert the C controller's text fault state into a numeric metric.

    The current simulator uses:

        FAULT=NONE

    This MVP mapping is:

        NONE            -> 0
        any other value -> 1

    This is not yet a cumulative fault counter.
    It is a simple current-fault indicator.

    Later improvement:
    - use a labeled metric for the fault name
    - maintain actual cumulative fault totals
    """
    return 0 if fault_value == "NONE" else 1


def update_metrics_from_simulator() -> None:
    """
    Collect one telemetry sample from the C controller simulator
    and update all Prometheus Gauges.

    Current Simulator Mode flow:

        controller.exe
            ->
        raw telemetry text:
        TLM,STATE=SAFE,ALIGN=85,PRESSURE=40,...
            ->
        simulator_client.py
            ->
        telemetry_parser.py
            ->
        Python dictionary:
        {
            "STATE": "SAFE",
            "ALIGN": "85",
            "PRESSURE": "40",
            ...
        }
            ->
        Prometheus Gauges
            ->
        Grafana dashboard

    The Python monitor reads telemetry only.
    It does not replace or override C controller safety logic.
    """

    # Start the simulator, send RESET, and receive one parsed telemetry sample.
    #
    # Example returned dictionary:
    # {
    #     "STATE": "SAFE",
    #     "ALIGN": "85",
    #     "PRESSURE": "40",
    #     "FUEL": "0",
    #     "DOCK": "0",
    #     "GATE": "CLOSED",
    #     "FAULT": "NONE",
    # }
    telemetry = get_simulator_telemetry("RESET")

    # The controller sends numeric telemetry values as strings.
    # Convert them to float before writing them to Prometheus Gauges.
    refueling_alignment.set(float(telemetry["ALIGN"]))
    refueling_pressure.set(float(telemetry["PRESSURE"]))
    refueling_fuel_level.set(float(telemetry["FUEL"]))
    refueling_docked.set(float(telemetry["DOCK"]))

    # GATE and FAULT are text values, so convert them into numbers.
    refueling_gate_open.set(convert_gate_to_number(telemetry["GATE"]))
    refueling_fault_count.set(convert_fault_to_count(telemetry["FAULT"]))

    # RESET currently produces safe controller telemetry.
    #
    # The controller protocol does not yet provide a total abort count.
    # Keep this value at 0 until the C telemetry format is extended.
    refueling_abort_count.set(0)

    # Receiving and parsing telemetry successfully means the simulator
    # is reachable and responding for this current MVP stage.
    refueling_controller_health.set(1)

    # This telemetry was collected during the current /metrics request.
    # Therefore its age is considered 0 seconds.
    refueling_telemetry_age_seconds.set(0)


@app.get("/health")
def health_check() -> dict[str, str]:
    """
    Confirm that the FastAPI telemetry monitor service is running.

    Current meaning:
    - Python FastAPI service is available.

    Current limitation:
    - This endpoint does not yet confirm that controller.exe is reachable.
    - Controller health is currently represented through Prometheus metrics.
    """
    return {"status": "ok"}


@app.get("/metrics")
def metrics() -> Response:
    """
    Expose Prometheus-compatible telemetry metrics.

    Every time Prometheus requests /metrics:

    1. Python starts controller.exe.
    2. Python sends RESET.
    3. Python receives one TLM telemetry line.
    4. Python parses the line.
    5. Python updates Prometheus Gauges.
    6. Python returns all metrics in Prometheus text format.

    Current limitation:
    - A new controller process is started for each scrape.
    - This is acceptable for the current MVP and learning stage.
    - A later version can keep the controller running continuously
      and stream telemetry in the background.
    """
    update_metrics_from_simulator()

    # generate_latest() converts all Prometheus Gauges into the text format
    # expected by the Prometheus server.
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


# Start the FastAPI/Uvicorn server only when this file is run directly.
#
# host="0.0.0.0" is required for Docker:
# - It allows Docker to expose port 8000 outside the container.
# - Your browser can still use http://localhost:8000.
if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
    )