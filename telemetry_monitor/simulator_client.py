import os
from pathlib import Path
from queue import Empty, Queue
from subprocess import PIPE, Popen
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


# Docker Compose will later provide this environment variable:
#
# RUNNING_IN_DOCKER=true
#
# When the variable is missing, this code assumes it is running locally
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
# The Linux executable is compiled from controller.c by Dockerfile.
if RUNNING_IN_DOCKER:
    CONTROLLER_PATH = Path("/controller/controller")
else:
    CONTROLLER_PATH = PROJECT_ROOT / "controller" / "controller.exe"


def _read_stream(stream, output_queue: Queue[str]) -> None:
    """
    Continuously read controller stdout in a background thread.

    The C controller keeps running and writes lines to stdout.
    This thread reads each line and puts it into a Queue so the main
    function can wait for telemetry without blocking on stream.readline().
    """
    for line in iter(stream.readline, ""):
        output_queue.put(line.rstrip())


def get_simulator_telemetry(command: str = "RESET") -> dict[str, str]:
    """
    Run the C controller simulator once and return one parsed TLM telemetry line.

    Workflow:
    1. Start the correct controller executable for the current environment.
    2. Send a controller command such as RESET.
    3. Read controller stdout.
    4. Find the first line beginning with TLM,.
    5. Parse the telemetry line into a dictionary.
    6. Stop the controller process safely.

    Example return value:
    {
        "STATE": "SAFE",
        "ALIGN": "85",
        "PRESSURE": "40",
        "FUEL": "0",
        "DOCK": "0",
        "GATE": "CLOSED",
        "FAULT": "NONE",
    }
    """

    # Do not try to start the simulator if the executable is missing.
    if not CONTROLLER_PATH.exists():
        raise FileNotFoundError(
            f"Controller executable was not found: {CONTROLLER_PATH}"
        )

    # Start the C controller with pipes connected to stdin and stdout.
    #
    # stdin=PIPE:
    #   Python can send commands such as RESET to the controller.
    #
    # stdout=PIPE:
    #   Python can read controller output, including TLM telemetry lines.
    #
    # stderr=PIPE:
    #   Reserved for future error logging and troubleshooting.
    #
    # text=True:
    #   Read and write normal Python strings instead of bytes.
    #
    # bufsize=1:
    #   Use line-buffered text I/O, which is useful for line-based telemetry.
    process = Popen(
        [str(CONTROLLER_PATH)],
        stdin=PIPE,
        stdout=PIPE,
        stderr=PIPE,
        text=True,
        bufsize=1,
    )

    # Validate that the process streams were created successfully.
    if process.stdout is None or process.stdin is None:
        process.terminate()
        raise RuntimeError("Could not open controller input/output streams.")

    # The Queue transfers output lines from the background reader thread
    # to the main telemetry-reading loop.
    output_queue: Queue[str] = Queue()

    # Start reading controller stdout in the background.
    # daemon=True means this thread will not keep Python alive if the
    # main program exits unexpectedly.
    Thread(
        target=_read_stream,
        args=(process.stdout, output_queue),
        daemon=True,
    ).start()

    try:
        # Send one command to the controller, followed by a newline because
        # the controller reads commands line by line.
        process.stdin.write(f"{command}\n")
        process.stdin.flush()

        # Wait up to 5 seconds for a telemetry line.
        # This prevents the API from waiting forever if the controller fails.
        deadline = time.time() + 5

        while time.time() < deadline:
            try:
                # Wait briefly for one new controller output line.
                line = output_queue.get(timeout=0.5)

                # A telemetry line starts with TLM, based on the controller protocol.
                if line.startswith("TLM,"):
                    # Convert raw text into a structured dictionary.
                    return parse_telemetry_line(line)

            except Empty:
                # No line arrived during this short wait.
                # Continue until the total 5-second deadline is reached.
                continue

        # The loop ended without receiving a TLM line.
        raise TimeoutError(
            "No telemetry line was received within 5 seconds "
            f"for command: {command}"
        )

    finally:
        # Always stop the C controller process, even if parsing or timeout fails.
        process.terminate()

        try:
            # Give the process a few seconds to close normally.
            process.wait(timeout=5)
        except TimeoutError:
            # Force-stop only if normal termination did not work.
            process.kill()