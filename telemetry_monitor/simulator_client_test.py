from simulator_client import get_simulator_telemetry


def main() -> None:
    """
    Test the reusable simulator client module.

    This script should:
    1. Start controller.exe.
    2. Send RESET.
    3. Receive one TLM line.
    4. Return parsed telemetry as a dictionary.
    """

    telemetry = get_simulator_telemetry("RESET")

    print("Simulator client returned telemetry:")
    print(telemetry)

    print("\nSelected values:")
    print(f"State: {telemetry['STATE']}")
    print(f"Pressure: {telemetry['PRESSURE']}")
    print(f"Alignment: {telemetry['ALIGN']}")


if __name__ == "__main__":
    main()