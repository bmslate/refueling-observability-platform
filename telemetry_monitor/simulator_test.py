from pathlib import Path
from queue import Empty, Queue
from subprocess import PIPE, Popen
from threading import Thread
import time

from telemetry_parser import parse_telemetry_line


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTROLLER_PATH = PROJECT_ROOT / "controller" / "controller.exe"


def read_stream(stream, output_queue: Queue[str]) -> None:
    """Read controller output in a background thread."""
    for line in iter(stream.readline, ""):
        output_queue.put(line.rstrip())


def main() -> None:
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

    output_queue: Queue[str] = Queue()

    if process.stdout is None or process.stdin is None:
        raise RuntimeError("Could not open controller input/output streams.")

    Thread(
        target=read_stream,
        args=(process.stdout, output_queue),
        daemon=True,
    ).start()

    try:
        print("Sending command: RESET")
        process.stdin.write("RESET\n")
        process.stdin.flush()

        deadline = time.time() + 5

        while time.time() < deadline:
            try:
                line = output_queue.get(timeout=0.5)
                print(f"Controller output: {line}")

                if line.startswith("TLM,"):
                    telemetry = parse_telemetry_line(line)

                    print("\nParsed simulator telemetry:")
                    print(telemetry)
                    print(f"Pressure: {telemetry['PRESSURE']}")
                    print(f"Alignment: {telemetry['ALIGN']}")
                    print(f"Controller state: {telemetry['STATE']}")

                    print(
                        "\nSimulator telemetry was received and "
                        "parsed successfully."
                    )
                    return

            except Empty:
                continue

        raise TimeoutError("No telemetry line was received within 5 seconds.")

    finally:
        process.terminate()
        process.wait(timeout=5)


if __name__ == "__main__":
    main()