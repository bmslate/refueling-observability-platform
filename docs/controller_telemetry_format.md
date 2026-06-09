\# Controller Telemetry Format



This document records the telemetry format produced by the original C-based refueling controller used in the \*\*Refueling Safety Observability Platform\*\* project.



The purpose of this document is to preserve the verified controller output format before building the Python telemetry monitor and Prometheus metrics exporter.



\---



\## Verification Summary



The original C refueling controller was successfully copied into the new project and verified locally.



Project path:



```text

C:\\github\\refueling-observability-platform

```



Controller source file:



```text

controller\\controller.c

```



Controller executable generated locally:



```text

controller\\controller.exe

```



The executable is a local build output and should not be committed to GitHub.



\---



\## Build Command



From the project root:



```powershell

cd C:\\github\\refueling-observability-platform

gcc controller\\controller.c -o controller\\controller.exe

```



\---



\## Run Command



From the project root:



```powershell

.\\controller\\controller.exe

```



\---



\## Startup Output



When the controller starts successfully, it prints:



```text

BOOT,SOFTWARE\_IN\_THE\_LOOP\_REFUELING\_CONTROLLER

INFO,READY\_FOR\_COMMANDS

```



This confirms that the controller is running and ready to receive commands through standard input.



\---



\## Example Input Commands



The controller accepts text-based commands.



Example commands tested:



```text

RESET

START\_APPROACH

```



\---



\## Example Output After RESET



Input:



```text

RESET

```



Output:



```text

ACK,RESET\_TO\_SAFE

TLM,STATE=SAFE,ALIGN=85,PRESSURE=40,FUEL=0,DOCK=0,GATE=CLOSED,FAULT=NONE

```



\---



\## Example Output After START\_APPROACH



Input:



```text

START\_APPROACH

```



Output:



```text

ACK,APPROACH\_STARTED

TLM,STATE=APPROACH,ALIGN=85,PRESSURE=40,FUEL=0,DOCK=0,GATE=CLOSED,FAULT=NONE

```



\---



\## Telemetry Line Format



Telemetry lines start with:



```text

TLM,

```



General format:



```text

TLM,STATE=<state>,ALIGN=<value>,PRESSURE=<value>,FUEL=<value>,DOCK=<value>,GATE=<value>,FAULT=<value>

```



Example:



```text

TLM,STATE=APPROACH,ALIGN=85,PRESSURE=40,FUEL=0,DOCK=0,GATE=CLOSED,FAULT=NONE

```



\---



\## Telemetry Fields



| Field    | Example Value | Description                                                     |

| -------- | ------------: | --------------------------------------------------------------- |

| STATE    |      APPROACH | Current controller state                                        |

| ALIGN    |            85 | Alignment value used to represent docking/alignment quality     |

| PRESSURE |            40 | Current pressure value                                          |

| FUEL     |             0 | Current fuel level                                              |

| DOCK     |             0 | Docking status, where `0` means not docked and `1` means docked |

| GATE     |        CLOSED | Gate status, such as `CLOSED` or `OPEN`                         |

| FAULT    |          NONE | Current fault status                                            |



\---



\## Non-Telemetry Output Types



The controller may also print non-telemetry lines.



\### Boot Message



```text

BOOT,SOFTWARE\_IN\_THE\_LOOP\_REFUELING\_CONTROLLER

```



\### Ready Message



```text

INFO,READY\_FOR\_COMMANDS

```



\### Acknowledgement Message



```text

ACK,RESET\_TO\_SAFE

ACK,APPROACH\_STARTED

```



\### Error Message



```text

ERR,<reason>

```



\### Fault Message



```text

FAULT,<reason>

```



Only lines beginning with `TLM,` should be parsed as telemetry.



\---



\## Parsing Strategy



The future Python telemetry monitor should:



1\. Read controller output line by line.

2\. Ignore non-telemetry lines unless they are needed for logs.

3\. Detect telemetry lines by checking whether the line starts with `TLM,`.

4\. Split telemetry lines by commas.

5\. Split each field by `=`.

6\. Convert numeric fields into numbers.

7\. Convert controller state and fault information into Prometheus-compatible metrics.



Example parsing logic:



```python

def parse\_telemetry(line):

&#x20;   if not line.startswith("TLM,"):

&#x20;       return None



&#x20;   result = {}

&#x20;   parts = line.split(",")\[1:]



&#x20;   for part in parts:

&#x20;       if "=" in part:

&#x20;           key, value = part.split("=", 1)

&#x20;           result\[key.strip()] = value.strip()



&#x20;   return result

```



\---



\## Planned Prometheus Metrics



The Python telemetry monitor will convert controller telemetry into Prometheus-compatible metrics.



Planned metrics:



```text

refueling\_alignment

refueling\_pressure

refueling\_fuel\_level

refueling\_docked

refueling\_gate\_open

refueling\_fault\_count

refueling\_abort\_count

refueling\_controller\_health

refueling\_telemetry\_age\_seconds

```



\---



\## Example Metric Mapping



| Telemetry Field           | Prometheus Metric               | Notes                                         |

| ------------------------- | ------------------------------- | --------------------------------------------- |

| ALIGN                     | refueling\_alignment             | Numeric alignment value                       |

| PRESSURE                  | refueling\_pressure              | Numeric pressure value                        |

| FUEL                      | refueling\_fuel\_level            | Numeric fuel level                            |

| DOCK                      | refueling\_docked                | `0` or `1`                                    |

| GATE                      | refueling\_gate\_open             | `1` if gate is open, otherwise `0`            |

| FAULT                     | refueling\_fault\_count           | Incremented when fault is not `NONE`          |

| Last telemetry timestamp  | refueling\_telemetry\_age\_seconds | Used to detect stale telemetry                |

| Controller process status | refueling\_controller\_health     | `1` if controller is reachable, otherwise `0` |



\---



\## Example Parsed Telemetry Object



Input telemetry line:



```text

TLM,STATE=APPROACH,ALIGN=85,PRESSURE=40,FUEL=0,DOCK=0,GATE=CLOSED,FAULT=NONE

```



Expected parsed result:



```json

{

&#x20; "STATE": "APPROACH",

&#x20; "ALIGN": "85",

&#x20; "PRESSURE": "40",

&#x20; "FUEL": "0",

&#x20; "DOCK": "0",

&#x20; "GATE": "CLOSED",

&#x20; "FAULT": "NONE"

}

```



\---



\## Notes for MVP Phase 1



For the MVP version, the telemetry monitor does not need to implement the full AWS, MQTT, Kubernetes, Go, or AI Agent workflow yet.



The MVP should focus on:



\* Reading or simulating telemetry

\* Providing `/health`

\* Providing `/metrics`

\* Exposing Prometheus-compatible metrics

\* Visualizing metrics in Grafana

\* Documenting the verified controller output format



\---



\## Current Status



Verified:



\* The original `controller.c` compiles successfully.

\* The generated `controller.exe` runs locally.

\* The controller accepts commands through standard input.

\* The controller outputs structured telemetry lines beginning with `TLM,`.

\* The telemetry format is suitable for parsing by a Python telemetry monitor.



Next step:



```text

Create telemetry\_monitor/app.py with /health endpoint.

```



