import os
from collections.abc import Sequence
from pathlib import Path
from queue import Empty, Queue
from subprocess import PIPE, Popen, TimeoutExpired
from threading import Thread
import time

from telemetry_parser import parse_telemetry_line


# PROJECT_ROOT is used only when the project runs locally on Windows.
#
# File location:
# telemetry_monitor/simulator_client.py
#
# parents[1] moves up from telemetry_monitor/ to the project root folder.
PROJECT_ROOT = Path(__file__).resolve().parents[1]


# Docker Compose provides this environment variable:
#
# RUNNING_IN_DOCKER=true
#
# When the variable is missing, this code assumes that it is running locally
# on Windows and uses controller.exe.
RUNNING_IN_DOCKER = os.getenv("RUNNING_IN_DOCKER", "false").lower() == "true"


# Select the correct C controller executable for the current environment.
#
# Local Windows development:
# C:\github\refueling-observability-platform\controller\controller.exe
#
# Linux Docker container:
# /controller/controller
#
# The Linux executable is compiled from controller.c by the Dockerfile.
if RUNNING_IN_DOCKER:
    CONTROLLER_PATH = Path("/controller/controller")
else:
    CONTROLLER_PATH = PROJECT_ROOT / "controller" / "controller.exe"


def _read_stream(stream, output_queue: Queue[str]) -> None:
    """
    Continuously read controller stdout in a background thread.

    The C controller stays alive while commands are being sent. This reader
    places every output line into a Queue so the main thread can wait for
    telemetry without blocking directly on stream.readline().
    """
    for line in iter(stream.readline, ""):
        output_queue.put(line.rstrip())


def _wait_for_telemetry(
    output_queue: Queue[str],
    command: str,
    timeout_seconds: float = 5.0,
) -> dict[str, str]:
    """
    Wait for the next TLM line produced after one controller command.

    Controller output may also contain BOOT, INFO, ACK, ERR, FAULT, and LOG
    lines. Those lines are intentionally skipped here because this function
    returns only the machine-readable telemetry snapshot.
    """
    deadline = time.time() + timeout_seconds

    while time.time() < deadline:
        try:
            line = output_queue.get(timeout=0.5)

            if line.startswith("TLM,"):
                return parse_telemetry_line(line)

        except Empty:
            continue

    raise TimeoutError(
        "No telemetry line was received within "
        f"{timeout_seconds:.1f} seconds for command: {command}"
    )


def get_simulator_telemetry_sequence(
    commands: Sequence[str],
) -> dict[str, str]:
    """
    Run one controller process, execute a command sequence, and return the
    final parsed telemetry snapshot.

    A single persistent controller process is used for the entire sequence so
    state changes are preserved between commands.

    Example pressure-high sequence:
        [
            "RESET",
            "START_APPROACH",
            "CHECK_ALIGNMENT",
            "LOCK_DOCK",
            "OPEN_GATE",
            "CHECK_PRESSURE",
            "START_REFUEL",
            "SIM_PRESSURE 90",
        ]

    Expected final telemetry:
        {
            "STATE": "ABORT",
            "ALIGN": "85",
            "PRESSURE": "90",
            "FUEL": "0",
            "DOCK": "1",
            "GATE": "CLOSED",
            "FAULT": "PRESSURE_OUT_OF_RANGE",
        }

    Important:
    - This is a controlled software-in-the-loop simulator workflow.
    - Python observes and drives test commands only.
    - Deterministic safety decisions remain inside controller.c.
    """
    if not commands:
        raise ValueError("At least one controller command is required.")

    if not CONTROLLER_PATH.exists():
        raise FileNotFoundError(
            f"Controller executable was not found: {CONTROLLER_PATH}"
        )

    process = Popen(
        [str(CONTROLLER_PATH)],
        stdin=PIPE,
        stdout=PIPE,
        stderr=PIPE,
        text=True,
        bufsize=1,
    )

    if process.stdout is None or process.stdin is None:
        process.terminate()
        raise RuntimeError("Could not open controller input/output streams.")

    output_queue: Queue[str] = Queue()

    Thread(
        target=_read_stream,
        args=(process.stdout, output_queue),
        daemon=True,
    ).start()

    latest_telemetry: dict[str, str] | None = None

    try:
        for command in commands:
            normalized_command = command.strip()

            if not normalized_command:
                raise ValueError("Controller commands must not be empty.")

            if process.poll() is not None:
                raise RuntimeError(
                    "Controller process stopped before the command sequence "
                    f"completed. Next command was: {normalized_command}"
                )

            # Send one command and wait for the telemetry snapshot produced
            # by that same command-processing cycle before sending the next.
            process.stdin.write(f"{normalized_command}\n")
            process.stdin.flush()

            latest_telemetry = _wait_for_telemetry(
                output_queue=output_queue,
                command=normalized_command,
            )

        if latest_telemetry is None:
            raise RuntimeError("The controller returned no telemetry.")

        return latest_telemetry

    finally:
        # Always stop the temporary simulator process after the sequence ends.
        process.terminate()

        try:
            process.wait(timeout=5)
        except TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def get_simulator_telemetry(command: str = "RESET") -> dict[str, str]:
    """
    Backward-compatible helper for callers that need only one command.

    Existing code such as app.py can continue calling:
        get_simulator_telemetry("RESET")
    """
    return get_simulator_telemetry_sequence([command])


if __name__ == "__main__":
    pressure_high_scenario = [
        "RESET",
        "START_APPROACH",
        "CHECK_ALIGNMENT",
        "LOCK_DOCK",
        "OPEN_GATE",
        "CHECK_PRESSURE",
        "START_REFUEL",
        "SIM_PRESSURE 90",
    ]

    result = get_simulator_telemetry_sequence(pressure_high_scenario)

    print("Final pressure-high telemetry:")
    for key, value in result.items():
        print(f"{key}: {value}")
