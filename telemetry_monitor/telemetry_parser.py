def parse_telemetry_line(line: str) -> dict[str, str]:
    """Convert one TLM line into a dictionary of telemetry fields."""
    if not line.startswith("TLM,"):
        raise ValueError("Telemetry line must start with 'TLM,'.")

    telemetry: dict[str, str] = {}

    for item in line.removeprefix("TLM,").split(","):
        key, value = item.split("=", maxsplit=1)
        telemetry[key] = value

    return telemetry


if __name__ == "__main__":
    sample_line = (
        "TLM,STATE=SAFE,ALIGN=85,PRESSURE=40,"
        "FUEL=0,DOCK=0,GATE=CLOSED,FAULT=NONE"
    )

    parsed = parse_telemetry_line(sample_line)

    print(parsed)
    print(f"Pressure: {parsed['PRESSURE']}")
    print(f"Alignment: {parsed['ALIGN']}")