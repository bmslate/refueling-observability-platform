import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from queue import Empty, Queue
from subprocess import PIPE, STDOUT, Popen, TimeoutExpired
from threading import Event, RLock, Thread
import time
from typing import TextIO

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


@dataclass(frozen=True, slots=True)
class TelemetrySample:
    """
    One telemetry event parsed by the background stdout reader.

    sequence:
        Increasing sample number for the current controller lifecycle.

    telemetry:
        Parsed TLM fields returned by telemetry_parser.py.

    received_monotonic:
        Local monotonic timestamp recorded when the sample was accepted.
    """

    sequence: int
    telemetry: dict[str, str]
    received_monotonic: float


class PersistentSimulatorProcess:
    """
    Own one long-running C controller process and one stdout reader thread.

    Calling start() repeatedly does not create duplicate processes or duplicate
    reader threads. Commands continue to use the same process until stop() is
    called.

    Safety boundary:
    - Python starts and supervises the simulator process.
    - Python sends controlled test commands and observes controller output.
    - controller.c remains responsible for deterministic safety decisions.
    """

    def __init__(
        self,
        controller_path: Path = CONTROLLER_PATH,
        telemetry_timeout_seconds: float = 5.0,
    ) -> None:
        if telemetry_timeout_seconds <= 0:
            raise ValueError("telemetry_timeout_seconds must be greater than 0.")

        self._controller_path = controller_path
        self._telemetry_timeout_seconds = telemetry_timeout_seconds

        self._process: Popen[str] | None = None
        self._reader_thread: Thread | None = None
        self._stop_requested = Event()

        # Command-response telemetry and independently observed telemetry use
        # separate queues. This prevents future cache consumers from removing
        # samples that send_command() is waiting for.
        self._command_response_queue: Queue[TelemetrySample] = Queue()
        self._telemetry_observation_queue: Queue[TelemetrySample] = Queue()

        # Non-TLM output and malformed TLM diagnostics are kept separately.
        self._diagnostic_queue: Queue[str] = Queue()

        self._sample_sequence = 0
        self._last_telemetry_received_monotonic: float | None = None
        self._latest_telemetry: TelemetrySample | None = None
        self._telemetry_parse_error_count = 0
        self._reader_failure: str | None = None

        # Protect process startup and shutdown.
        self._lifecycle_lock = RLock()

        # Protect command writes and complete command sequences.
        #
        # RLock is required because send_commands() protects the full sequence
        # and calls send_command(), which obtains the same lock again.
        self._command_lock = RLock()

        # Protect reader-owned state inspected by other threads.
        self._state_lock = RLock()

    @property
    def pid(self) -> int | None:
        """Return the active controller PID, or None when it is not running."""
        process = self._process

        if process is None or process.poll() is not None:
            return None

        return process.pid

    @property
    def reader_thread_alive(self) -> bool:
        """Return True while the background stdout reader is alive."""
        reader_thread = self._reader_thread
        return reader_thread is not None and reader_thread.is_alive()

    @property
    def reader_thread_ident(self) -> int | None:
        """Return the background reader thread identifier when available."""
        reader_thread = self._reader_thread

        if reader_thread is None:
            return None

        return reader_thread.ident

    @property
    def telemetry_sample_count(self) -> int:
        """Return the number of valid TLM samples parsed in this lifecycle."""
        with self._state_lock:
            return self._sample_sequence

    @property
    def last_telemetry_received_monotonic(self) -> float | None:
        """Return the receive timestamp of the most recent valid telemetry."""
        with self._state_lock:
            return self._last_telemetry_received_monotonic

    @property
    def telemetry_parse_error_count(self) -> int:
        """Return the number of malformed TLM lines rejected by the reader."""
        with self._state_lock:
            return self._telemetry_parse_error_count

    @property
    def reader_failure(self) -> str | None:
        """Return the latest unexpected reader failure, if one occurred."""
        with self._state_lock:
            return self._reader_failure

    def get_latest_telemetry(self) -> TelemetrySample | None:
        """
        Return the newest valid telemetry sample without consuming a queue.

        A defensive copy of the telemetry dictionary is returned so callers
        cannot modify the internal shared cache.
        """
        with self._state_lock:
            sample = self._latest_telemetry

            if sample is None:
                return None

            return TelemetrySample(
                sequence=sample.sequence,
                telemetry=dict(sample.telemetry),
                received_monotonic=sample.received_monotonic,
            )

    def is_running(self) -> bool:
        """Return True when the controller process is alive."""
        process = self._process
        return process is not None and process.poll() is None

    def start(self) -> None:
        """
        Start one controller process and one background reader thread.

        This method is idempotent. Repeated calls while the process is already
        running return without creating another process or reader thread.
        """
        with self._lifecycle_lock:
            if self.is_running():
                return

            if not self._controller_path.exists():
                raise FileNotFoundError(
                    f"Controller executable was not found: {self._controller_path}"
                )

            self._reset_lifecycle_state()

            process = Popen(
                [str(self._controller_path)],
                stdin=PIPE,
                stdout=PIPE,
                stderr=STDOUT,
                text=True,
                bufsize=1,
            )

            if process.stdin is None or process.stdout is None:
                process.terminate()
                raise RuntimeError("Could not open controller input/output streams.")

            self._process = process

            self._reader_thread = Thread(
                target=self._read_stream,
                args=(process.stdout,),
                name="controller-stdout-reader",
                daemon=True,
            )
            self._reader_thread.start()

    def send_command(self, command: str) -> dict[str, str]:
        """
        Send one command and wait for the next telemetry sample produced after
        the command was written.
        """
        normalized_command = command.strip()

        if not normalized_command:
            raise ValueError("Controller command must not be empty.")

        with self._command_lock:
            process = self._process

            if process is None:
                raise RuntimeError(
                    "Controller process has not been started. Call start() first."
                )

            return_code = process.poll()

            if return_code is not None:
                raise RuntimeError(
                    "Controller process is not running. "
                    f"Last return code: {return_code}"
                )

            if process.stdin is None:
                raise RuntimeError("Controller stdin is unavailable.")

            # Ignore telemetry already observed before this command.
            minimum_sequence = self.telemetry_sample_count + 1

            process.stdin.write(f"{normalized_command}\n")
            process.stdin.flush()

            sample = self._wait_for_command_telemetry(
                command=normalized_command,
                minimum_sequence=minimum_sequence,
            )

            return dict(sample.telemetry)

    def send_commands(
        self,
        commands: Sequence[str],
    ) -> dict[str, str]:
        """
        Send a complete sequence through the same controller process.

        The lock covers the entire sequence so another request cannot insert a
        command between scenario steps.
        """
        if not commands:
            raise ValueError("At least one controller command is required.")

        with self._command_lock:
            latest_telemetry: dict[str, str] | None = None

            for command in commands:
                latest_telemetry = self.send_command(command)

            if latest_telemetry is None:
                raise RuntimeError("The controller returned no telemetry.")

            return latest_telemetry

    def get_observed_telemetry(
        self,
        timeout_seconds: float = 0.0,
    ) -> TelemetrySample | None:
        """
        Return the next independently observed telemetry event.

        This queue is separate from command-response handling. Reading an
        observed event removes it from this event stream. Use
        get_latest_telemetry() for a non-consuming latest-value read.
        """
        if timeout_seconds < 0:
            raise ValueError("timeout_seconds must not be negative.")

        try:
            if timeout_seconds == 0:
                sample = self._telemetry_observation_queue.get_nowait()
            else:
                sample = self._telemetry_observation_queue.get(
                    timeout=timeout_seconds
                )
        except Empty:
            return None

        return TelemetrySample(
            sequence=sample.sequence,
            telemetry=dict(sample.telemetry),
            received_monotonic=sample.received_monotonic,
        )

    def get_diagnostic_line(self, timeout_seconds: float = 0.0) -> str | None:
        """Return the next BOOT/INFO/ACK/ERR/FAULT/LOG diagnostic line."""
        if timeout_seconds < 0:
            raise ValueError("timeout_seconds must not be negative.")

        try:
            if timeout_seconds == 0:
                return self._diagnostic_queue.get_nowait()

            return self._diagnostic_queue.get(timeout=timeout_seconds)
        except Empty:
            return None

    def stop(self) -> None:
        """
        Stop the controller and wait for the reader thread to exit.

        Closing stdin first allows the controller's fgets loop to receive EOF
        and exit normally. terminate() and kill() are bounded fallbacks.
        """
        # Wait for an in-flight command or sequence before shutting down.
        with self._command_lock:
            with self._lifecycle_lock:
                process = self._process
                reader_thread = self._reader_thread

                if process is None:
                    return

                self._stop_requested.set()

                if process.stdin is not None:
                    try:
                        process.stdin.close()
                    except OSError:
                        pass

                try:
                    process.wait(timeout=2)
                except TimeoutExpired:
                    process.terminate()

                    try:
                        process.wait(timeout=3)
                    except TimeoutExpired:
                        process.kill()
                        process.wait(timeout=3)

                if reader_thread is not None:
                    reader_thread.join(timeout=2)

                    if reader_thread.is_alive():
                        raise RuntimeError(
                            "Controller stdout reader did not stop cleanly."
                        )

                self._process = None
                self._reader_thread = None

    def _reset_lifecycle_state(self) -> None:
        """Create clean queues and state for a new controller lifecycle."""
        self._stop_requested.clear()

        self._command_response_queue = Queue()
        self._telemetry_observation_queue = Queue()
        self._diagnostic_queue = Queue()

        with self._state_lock:
            self._sample_sequence = 0
            self._last_telemetry_received_monotonic = None
            self._latest_telemetry = None
            self._telemetry_parse_error_count = 0
            self._reader_failure = None

    def _read_stream(self, stream: TextIO) -> None:
        """
        Read and classify controller stdout for the entire process lifetime.

        This is the only method allowed to call readline() on controller stdout.
        Valid TLM lines are parsed once and then routed to two independent
        queues:

        - command-response queue
        - telemetry-observation queue

        Non-TLM lines are routed to the diagnostic queue.
        """
        try:
            for raw_line in iter(stream.readline, ""):
                line = raw_line.rstrip()

                if not line:
                    continue

                if not line.startswith("TLM,"):
                    self._diagnostic_queue.put(line)
                    continue

                try:
                    telemetry = parse_telemetry_line(line)
                except (ValueError, KeyError) as exc:
                    with self._state_lock:
                        self._telemetry_parse_error_count += 1

                    self._diagnostic_queue.put(
                        f"TELEMETRY_PARSE_ERROR,{type(exc).__name__}:{exc},"
                        f"RAW={line}"
                    )
                    continue

                received_monotonic = time.monotonic()

                with self._state_lock:
                    self._sample_sequence += 1
                    sequence = self._sample_sequence
                    self._last_telemetry_received_monotonic = (
                        received_monotonic
                    )

                    sample = TelemetrySample(
                        sequence=sequence,
                        telemetry=dict(telemetry),
                        received_monotonic=received_monotonic,
                    )

                    # Update the cache only after the TLM line was parsed
                    # successfully.
                    self._latest_telemetry = sample

                # Queueing the same internal sample object is safe. Public
                # methods return copies of the dictionary to callers.
                self._command_response_queue.put(sample)
                self._telemetry_observation_queue.put(sample)

        except Exception as exc:
            failure = f"{type(exc).__name__}: {exc}"

            with self._state_lock:
                self._reader_failure = failure

            self._diagnostic_queue.put(f"READER_FAILURE,{failure}")

        finally:
            try:
                stream.close()
            except OSError:
                pass

            if not self._stop_requested.is_set():
                process = self._process

                if process is not None and process.poll() is None:
                    failure = (
                        "Controller stdout reached EOF while the process "
                        "was still running."
                    )

                    with self._state_lock:
                        self._reader_failure = failure

                    self._diagnostic_queue.put(
                        f"READER_FAILURE,{failure}"
                    )

    def _wait_for_command_telemetry(
        self,
        command: str,
        minimum_sequence: int,
    ) -> TelemetrySample:
        """Wait for the first command-response sample after a sequence number."""
        deadline = time.monotonic() + self._telemetry_timeout_seconds

        while True:
            remaining = deadline - time.monotonic()

            if remaining <= 0:
                break

            reader_failure = self.reader_failure

            if reader_failure is not None:
                raise RuntimeError(
                    "Background telemetry reader failed while waiting for "
                    f"command {command!r}: {reader_failure}"
                )

            process = self._process

            if process is None:
                raise RuntimeError(
                    "Controller process was stopped while waiting for telemetry."
                )

            return_code = process.poll()

            if (
                return_code is not None
                and self._command_response_queue.empty()
            ):
                raise RuntimeError(
                    "Controller process exited while waiting for telemetry. "
                    f"Return code: {return_code}; command: {command}"
                )

            try:
                sample = self._command_response_queue.get(
                    timeout=min(0.5, remaining)
                )
            except Empty:
                continue

            if sample.sequence >= minimum_sequence:
                return sample

        raise TimeoutError(
            "No telemetry line was received within "
            f"{self._telemetry_timeout_seconds:.1f} seconds "
            f"for command: {command}"
        )

    def __enter__(self) -> "PersistentSimulatorProcess":
        self.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.stop()


def get_simulator_telemetry_sequence(
    commands: Sequence[str],
) -> dict[str, str]:
    """
    Backward-compatible helper.

    It creates one controller process for the supplied sequence and stops it
    afterward. FastAPI should use one shared PersistentSimulatorProcess.
    """
    with PersistentSimulatorProcess() as simulator:
        return simulator.send_commands(commands)


def get_simulator_telemetry(command: str = "RESET") -> dict[str, str]:
    """Backward-compatible helper for one controller command."""
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

    simulator = PersistentSimulatorProcess()

    if simulator.get_latest_telemetry() is not None:
        raise RuntimeError("Latest telemetry cache was not initially empty.")

    try:
        simulator.start()

        first_pid = simulator.pid
        first_reader_ident = simulator.reader_thread_ident

        # Repeated start() calls must not create a new process or reader.
        simulator.start()

        if first_pid != simulator.pid:
            raise RuntimeError("Duplicate start() created a different process.")

        if first_reader_ident != simulator.reader_thread_ident:
            raise RuntimeError(
                "Duplicate start() created a different reader thread."
            )

        if simulator.get_latest_telemetry() is not None:
            raise RuntimeError(
                "Latest telemetry cache was not empty before the first sample."
            )

        reset_result = simulator.send_command("RESET")
        latest_after_reset = simulator.get_latest_telemetry()

        if latest_after_reset is None:
            raise RuntimeError("RESET did not populate the latest telemetry cache.")

        if latest_after_reset.telemetry != reset_result:
            raise RuntimeError(
                "Latest telemetry cache did not match the RESET response."
            )

        reset_cache_sequence = latest_after_reset.sequence

        # Verify that callers cannot mutate the internal cache.
        latest_after_reset.telemetry["STATE"] = "MUTATED_BY_CALLER"
        latest_after_mutation = simulator.get_latest_telemetry()

        if latest_after_mutation is None:
            raise RuntimeError("Latest telemetry cache unexpectedly became empty.")

        if latest_after_mutation.telemetry["STATE"] == "MUTATED_BY_CALLER":
            raise RuntimeError(
                "Caller mutation changed the internal latest telemetry cache."
            )

        initial_sample_count = simulator.telemetry_sample_count
        result = simulator.send_commands(pressure_high_scenario)
        parsed_sample_count = (
            simulator.telemetry_sample_count - initial_sample_count
        )

        latest_after_pressure_high = simulator.get_latest_telemetry()

        if latest_after_pressure_high is None:
            raise RuntimeError(
                "Pressure-high scenario did not update the latest cache."
            )

        if latest_after_pressure_high.telemetry != result:
            raise RuntimeError(
                "Latest cache did not match final pressure-high telemetry."
            )

        if latest_after_pressure_high.sequence <= reset_cache_sequence:
            raise RuntimeError(
                "Latest cache sequence did not advance after new telemetry."
            )

        expected_final_fields = {
            "STATE": "ABORT",
            "PRESSURE": "90",
            "GATE": "CLOSED",
            "FAULT": "PRESSURE_OUT_OF_RANGE",
        }

        for key, expected_value in expected_final_fields.items():
            actual_value = latest_after_pressure_high.telemetry.get(key)

            if actual_value != expected_value:
                raise RuntimeError(
                    "Latest cache contained an unexpected final value: "
                    f"{key}={actual_value!r}, expected {expected_value!r}"
                )

        expected_observed_events = 1 + len(pressure_high_scenario)
        observed_samples: list[TelemetrySample] = []

        for _ in range(expected_observed_events):
            sample = simulator.get_observed_telemetry(timeout_seconds=1.0)

            if sample is None:
                raise RuntimeError(
                    "The telemetry observation queue did not receive all "
                    "expected samples."
                )

            observed_samples.append(sample)

        print(f"Controller PID: {simulator.pid}")
        print(f"Reader thread ID: {simulator.reader_thread_ident}")
        print(f"Telemetry samples parsed for scenario: {parsed_sample_count}")
        print(f"Observed telemetry events: {len(observed_samples)}")
        print(f"Latest cache sequence: {latest_after_pressure_high.sequence}")
        print("Defensive cache copy verified.")
        print("Final pressure-high telemetry from latest cache:")

        for key, value in latest_after_pressure_high.telemetry.items():
            print(f"{key}: {value}")

    finally:
        simulator.stop()

    if simulator.reader_thread_alive:
        raise RuntimeError("Reader thread remained alive after stop().")

    simulator.start()

    try:
        if simulator.get_latest_telemetry() is not None:
            raise RuntimeError(
                "Latest telemetry cache was not reset for a new lifecycle."
            )

        if simulator.telemetry_sample_count != 0:
            raise RuntimeError(
                "Telemetry sequence was not reset for a new lifecycle."
            )
    finally:
        simulator.stop()

    print("Reader shutdown verified.")
    print("Latest telemetry cache reset verified.")
