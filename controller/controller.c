/*
 * Refueling Safety Controller — Software-in-the-Loop Simulator
 *
 * Purpose:
 *   This deterministic C controller models a spacecraft refueling sequence.
 *   It accepts text commands from standard input, updates controller state,
 *   performs safety checks, records a short in-memory event log, and emits
 *   machine-readable telemetry lines for the Python observability service.
 *
 * Safety boundary:
 *   Safety-critical decisions remain in this deterministic C controller.
 *   Python, Prometheus, Grafana, and any future AI component may observe,
 *   summarize, and report telemetry, but they must not replace this logic.
 *
 * Important simulator limitation:
 *   The current event loop is command-driven because fgets() blocks while
 *   waiting for input. Time-based updates and automatic safety checks run
 *   whenever a command-processing cycle occurs; they do not run continuously
 *   while standard input is idle.
 */

#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <ctype.h>
#include <time.h>

/* Fixed-size limits used by the command buffer and in-memory event log. */
#define MAX_LOGS 12
#define MAX_LINE 128

/*
 * Deterministic safety thresholds.
 * Alignment must be at least 60.
 * Pressure must remain within the inclusive range 20..80.
 */
#define ALIGNMENT_MIN_SAFE 60
#define PRESSURE_MIN_SAFE 20
#define PRESSURE_MAX_SAFE 80

/*
 * All valid controller states.
 *
 * The normal sequence is:
 * IDLE/SAFE -> APPROACH -> ALIGNMENT_CHECK -> DOCK_LOCKED
 * -> GATE_OPEN -> PRESSURE_CHECK -> REFUELING -> COMPLETE
 *
 * ABORT and FAULT are protective terminal states that require RESET before
 * most operating commands are accepted again.
 */
typedef enum {
    STATE_IDLE,
    STATE_APPROACH,
    STATE_ALIGNMENT_CHECK,
    STATE_DOCK_LOCKED,
    STATE_GATE_OPEN,
    STATE_PRESSURE_CHECK,
    STATE_REFUELING,
    STATE_COMPLETE,
    STATE_ABORT,
    STATE_SAFE,
    STATE_FAULT
} SystemState;

/*
 * Complete mutable state of one controller instance.
 *
 * eventLog is a small rolling log. When full, the oldest entry is discarded.
 * lastFuelUpdate is used to determine when simulated fuel should increase.
 */
typedef struct {
    SystemState state;
    int alignment;
    int pressure;
    int fuel;
    int dockLocked;
    int gateOpen;
    char faultCause[64];

    char eventLog[MAX_LOGS][96];
    int logCount;

    clock_t lastFuelUpdate;
} RefuelingController;

/*
 * Convert an internal enum value to the stable text value emitted in telemetry.
 */
const char* stateToString(SystemState state) {
    switch (state) {
        case STATE_IDLE: return "IDLE";
        case STATE_APPROACH: return "APPROACH";
        case STATE_ALIGNMENT_CHECK: return "ALIGNMENT_CHECK";
        case STATE_DOCK_LOCKED: return "DOCK_LOCKED";
        case STATE_GATE_OPEN: return "GATE_OPEN";
        case STATE_PRESSURE_CHECK: return "PRESSURE_CHECK";
        case STATE_REFUELING: return "REFUELING";
        case STATE_COMPLETE: return "COMPLETE";
        case STATE_ABORT: return "ABORT";
        case STATE_SAFE: return "SAFE";
        case STATE_FAULT: return "FAULT";
        default: return "UNKNOWN";
    }
}

/*
 * Normalize incoming commands so command matching is case-insensitive.
 */
void toUpperCase(char* text) {
    for (int i = 0; text[i] != '\0'; i++) {
        text[i] = (char)toupper((unsigned char)text[i]);
    }
}

/*
 * Remove CR/LF characters added by terminal input on Windows or Linux.
 */
void trimNewline(char* text) {
    size_t len = strlen(text);

    while (len > 0 && (text[len - 1] == '\n' || text[len - 1] == '\r')) {
        text[len - 1] = '\0';
        len--;
    }
}

/*
 * Append an event to the rolling in-memory log.
 *
 * If the log is full, shift entries left and overwrite the oldest event.
 */
void addEvent(RefuelingController* controller, const char* eventText) {
    if (controller->logCount < MAX_LOGS) {
        snprintf(controller->eventLog[controller->logCount], 96, "%s", eventText);
        controller->logCount++;
    } else {
        for (int i = 1; i < MAX_LOGS; i++) {
            snprintf(controller->eventLog[i - 1], 96, "%s", controller->eventLog[i]);
        }

        snprintf(controller->eventLog[MAX_LOGS - 1], 96, "%s", eventText);
    }
}

/*
 * Restore known-safe default values after startup, a fault, or an abort.
 */
void resetToSafe(RefuelingController* controller) {
    controller->state = STATE_SAFE;
    controller->alignment = 85;
    controller->pressure = 40;
    controller->fuel = 0;
    controller->dockLocked = 0;
    controller->gateOpen = 0;
    snprintf(controller->faultCause, sizeof(controller->faultCause), "NONE");
    controller->lastFuelUpdate = clock();

    addEvent(controller, "RESET_TO_SAFE");
}

/*
 * Initialize the controller at program startup.
 *
 * STATE_IDLE is used for initial boot; RESET moves the controller to STATE_SAFE.
 */
void initializeController(RefuelingController* controller) {
    controller->state = STATE_IDLE;
    controller->alignment = 85;
    controller->pressure = 40;
    controller->fuel = 0;
    controller->dockLocked = 0;
    controller->gateOpen = 0;
    controller->logCount = 0;
    snprintf(controller->faultCause, sizeof(controller->faultCause), "NONE");
    controller->lastFuelUpdate = clock();

    addEvent(controller, "SYSTEM_BOOT");
}

/*
 * Emit one parseable telemetry snapshot.
 *
 * Keep this TLM key/value format stable because telemetry_parser.py depends on
 * these field names: STATE, ALIGN, PRESSURE, FUEL, DOCK, GATE, and FAULT.
 */
void sendTelemetry(const RefuelingController* controller) {
    printf(
        "TLM,STATE=%s,ALIGN=%d,PRESSURE=%d,FUEL=%d,DOCK=%d,GATE=%s,FAULT=%s\n",
        stateToString(controller->state),
        controller->alignment,
        controller->pressure,
        controller->fuel,
        controller->dockLocked,
        controller->gateOpen ? "OPEN" : "CLOSED",
        controller->faultCause
    );

    fflush(stdout);
}

/*
 * Print all currently retained event-log entries between BEGIN/END markers.
 */
void printLog(const RefuelingController* controller) {
    printf("LOG,BEGIN\n");

    for (int i = 0; i < controller->logCount; i++) {
        printf("LOG,%d,%s\n", i + 1, controller->eventLog[i]);
    }

    printf("LOG,END\n");
    fflush(stdout);
}

/*
 * Enter the protective ABORT state.
 *
 * The gate is always closed, the cause is stored in telemetry, and an event is
 * added to the rolling log.
 */
void enterAbort(RefuelingController* controller, const char* cause) {
    controller->state = STATE_ABORT;
    controller->gateOpen = 0;
    snprintf(controller->faultCause, sizeof(controller->faultCause), "%s", cause);

    char logMessage[96];
    snprintf(logMessage, sizeof(logMessage), "ABORT_%s", cause);
    addEvent(controller, logMessage);

    printf("ACK,ABORT_ENTERING_SAFE_MODE,CAUSE=%s\n", cause);
    fflush(stdout);
}

/*
 * Enter the FAULT state when a precondition or validation check fails.
 *
 * As with ABORT, the gate is closed immediately.
 */
void enterFault(RefuelingController* controller, const char* cause) {
    controller->state = STATE_FAULT;
    controller->gateOpen = 0;
    snprintf(controller->faultCause, sizeof(controller->faultCause), "%s", cause);

    char logMessage[96];
    snprintf(logMessage, sizeof(logMessage), "FAULT_%s", cause);
    addEvent(controller, logMessage);

    printf("FAULT,%s\n", cause);
    fflush(stdout);
}

/*
 * Advance the simulated fuel level while the controller is REFUELING.
 *
 * Every 0.7 CPU-seconds of active processing, fuel increases by five points.
 * When fuel reaches 100, the gate closes and the sequence completes.
 */
void updateRefueling(RefuelingController* controller) {
    if (controller->state != STATE_REFUELING) {
        return;
    }

    clock_t now = clock();
    double elapsedSeconds = (double)(now - controller->lastFuelUpdate) / CLOCKS_PER_SEC;

    if (elapsedSeconds >= 0.7) {
        controller->lastFuelUpdate = now;

        if (controller->fuel < 100) {
            controller->fuel += 5;
        }

        if (controller->fuel >= 100) {
            controller->fuel = 100;
            controller->gateOpen = 0;
            controller->state = STATE_COMPLETE;
            addEvent(controller, "REFUELING_COMPLETE");
            printf("ACK,REFUELING_COMPLETE\n");
            fflush(stdout);
        }
    }
}

/*
 * Enforce deterministic safety rules during active refueling.
 *
 * This function intentionally acts only in STATE_REFUELING:
 * - alignment below the safe minimum causes ABORT
 * - pressure outside the safe range causes ABORT
 *
 * Bug fix:
 *   main() now calls this function before and after each command is handled.
 */
void automaticSafetyCheck(RefuelingController* controller) {
    if (controller->state != STATE_REFUELING) {
        return;
    }

    if (controller->alignment < ALIGNMENT_MIN_SAFE) {
        enterAbort(controller, "ALIGNMENT_LOST");
        return;
    }

    if (controller->pressure < PRESSURE_MIN_SAFE || controller->pressure > PRESSURE_MAX_SAFE) {
        enterAbort(controller, "PRESSURE_OUT_OF_RANGE");
        return;
    }
}

/*
 * Split an input line into a command token and one optional argument token.
 *
 * Example:
 *   "SIM_PRESSURE 90" -> command="SIM_PRESSURE", argument="90"
 */
void splitCommand(char* input, char* command, char* argument) {
    command[0] = '\0';
    argument[0] = '\0';

    char* token = strtok(input, " ");

    if (token != NULL) {
        snprintf(command, 64, "%s", token);
    }

    token = strtok(NULL, " ");

    if (token != NULL) {
        snprintf(argument, 64, "%s", token);
    }
}

/*
 * Parse and execute one controller command.
 *
 * Read-only commands and RESET are handled before the FAULT/ABORT command
 * lockout so operators can inspect or recover the controller safely.
 */
void handleCommand(RefuelingController* controller, char* input) {
    trimNewline(input);
    toUpperCase(input);

    char command[64];
    char argument[64];

    splitCommand(input, command, argument);

    if (strlen(command) == 0) {
        printf("ERR,EMPTY_COMMAND\n");
        return;
    }

    if (strcmp(command, "PING") == 0) {
        printf("ACK,PING\n");
        return;
    }

    if (strcmp(command, "GET_STATUS") == 0) {
        sendTelemetry(controller);
        return;
    }

    if (strcmp(command, "GET_LOG") == 0) {
        printLog(controller);
        return;
    }

    if (strcmp(command, "RESET") == 0) {
        resetToSafe(controller);
        printf("ACK,RESET_TO_SAFE\n");
        return;
    }

    if (strcmp(command, "SIM_ALIGN") == 0) {
        if (strlen(argument) == 0) {
            printf("ERR,SIM_ALIGN_REQUIRES_VALUE\n");
            return;
        }

        int value = atoi(argument);

        if (value < 0 || value > 100) {
            printf("ERR,ALIGN_OUT_OF_RANGE\n");
            return;
        }

        controller->alignment = value;
        printf("ACK,SIM_ALIGN=%d\n", controller->alignment);
        return;
    }

    if (strcmp(command, "SIM_PRESSURE") == 0) {
        if (strlen(argument) == 0) {
            printf("ERR,SIM_PRESSURE_REQUIRES_VALUE\n");
            return;
        }

        int value = atoi(argument);

        if (value < 0 || value > 100) {
            printf("ERR,PRESSURE_OUT_OF_RANGE\n");
            return;
        }

        controller->pressure = value;
        printf("ACK,SIM_PRESSURE=%d\n", controller->pressure);
        return;
    }

    /*
     * Allow an explicit abort cause for testing and incident traceability.
     * Without an argument, use the default supervisor-command cause.
     */
    if (strcmp(command, "ABORT") == 0) {
        if (strlen(argument) > 0) {
            enterAbort(controller, argument);
        } else {
            enterAbort(controller, "SUPERVISOR_COMMAND");
        }

        return;
    }

    if (strcmp(command, "INJECT_FAULT") == 0) {
        enterFault(controller, "MANUAL_INJECTION");
        return;
    }

    if ((controller->state == STATE_ABORT || controller->state == STATE_FAULT) &&
        strcmp(command, "RESET") != 0 &&
        strcmp(command, "GET_STATUS") != 0 &&
        strcmp(command, "GET_LOG") != 0 &&
        strcmp(command, "PING") != 0) {
        printf("ERR,SYSTEM_IN_FAULT_OR_ABORT_STATE\n");
        return;
    }

    if (strcmp(command, "START_APPROACH") == 0) {
        if (controller->state != STATE_IDLE && controller->state != STATE_SAFE) {
            printf("ERR,INVALID_STATE_TRANSITION\n");
            return;
        }

        controller->state = STATE_APPROACH;
        addEvent(controller, "START_APPROACH");
        printf("ACK,APPROACH_STARTED\n");
        return;
    }

    if (strcmp(command, "CHECK_ALIGNMENT") == 0) {
        if (controller->state != STATE_APPROACH) {
            printf("ERR,ALIGNMENT_CHECK_REQUIRES_APPROACH\n");
            return;
        }

        controller->state = STATE_ALIGNMENT_CHECK;

        if (controller->alignment < ALIGNMENT_MIN_SAFE) {
            enterFault(controller, "ALIGNMENT_OUT_OF_RANGE");
            return;
        }

        addEvent(controller, "ALIGNMENT_OK");
        printf("ACK,ALIGNMENT_OK\n");
        return;
    }

    if (strcmp(command, "LOCK_DOCK") == 0) {
        if (controller->state != STATE_ALIGNMENT_CHECK) {
            printf("ERR,DOCK_LOCK_REQUIRES_ALIGNMENT_CHECK\n");
            return;
        }

        if (controller->alignment < ALIGNMENT_MIN_SAFE) {
            enterFault(controller, "ALIGNMENT_OUT_OF_RANGE");
            return;
        }

        controller->dockLocked = 1;
        controller->state = STATE_DOCK_LOCKED;
        addEvent(controller, "DOCK_LOCKED");
        printf("ACK,DOCK_LOCKED\n");
        return;
    }

    if (strcmp(command, "OPEN_GATE") == 0) {
        if (controller->state != STATE_DOCK_LOCKED) {
            printf("ERR,GATE_BLOCKED_DOCK_NOT_LOCKED\n");
            return;
        }

        controller->gateOpen = 1;
        controller->state = STATE_GATE_OPEN;
        addEvent(controller, "GATE_OPEN");
        printf("ACK,GATE_OPEN\n");
        return;
    }

    if (strcmp(command, "CHECK_PRESSURE") == 0) {
        if (controller->state != STATE_GATE_OPEN) {
            printf("ERR,PRESSURE_CHECK_REQUIRES_GATE_OPEN\n");
            return;
        }

        if (controller->pressure < PRESSURE_MIN_SAFE || controller->pressure > PRESSURE_MAX_SAFE) {
            enterFault(controller, "PRESSURE_OUT_OF_RANGE");
            return;
        }

        controller->state = STATE_PRESSURE_CHECK;
        addEvent(controller, "PRESSURE_OK");
        printf("ACK,PRESSURE_OK\n");
        return;
    }

    if (strcmp(command, "START_REFUEL") == 0) {
        if (controller->state != STATE_PRESSURE_CHECK) {
            printf("ERR,REFUEL_BLOCKED_PRESSURE_CHECK_REQUIRED\n");
            return;
        }

        if (!controller->dockLocked) {
            printf("ERR,REFUEL_BLOCKED_DOCK_NOT_LOCKED\n");
            return;
        }

        if (!controller->gateOpen) {
            printf("ERR,REFUEL_BLOCKED_GATE_NOT_OPEN\n");
            return;
        }

        if (controller->alignment < ALIGNMENT_MIN_SAFE) {
            enterFault(controller, "ALIGNMENT_OUT_OF_RANGE");
            return;
        }

        controller->state = STATE_REFUELING;
        controller->fuel = 0;
        controller->lastFuelUpdate = clock();
        addEvent(controller, "REFUELING_STARTED");
        printf("ACK,REFUELING_STARTED\n");
        return;
    }

    if (strcmp(command, "STOP_REFUEL") == 0) {
        if (controller->state != STATE_REFUELING) {
            printf("ERR,NOT_REFUELING\n");
            return;
        }

        controller->state = STATE_SAFE;
        controller->gateOpen = 0;
        addEvent(controller, "REFUELING_STOPPED_BY_COMMAND");
        printf("ACK,REFUELING_STOPPED_ENTERING_SAFE\n");
        return;
    }

    printf("ERR,INVALID_COMMAND\n");
}

/*
 * Program entry point and command-driven event loop.
 *
 * Each command-processing cycle:
 * 1. advances time-based refueling progress
 * 2. performs a safety check before accepting the next command
 * 3. executes the command
 * 4. advances progress again if the command changed state
 * 5. performs a second safety check after the command
 * 6. emits one telemetry snapshot
 */
int main(void) {
    RefuelingController controller;
    char input[MAX_LINE];

    initializeController(&controller);

    printf("BOOT,SOFTWARE_IN_THE_LOOP_REFUELING_CONTROLLER\n");
    printf("INFO,READY_FOR_COMMANDS\n");
    fflush(stdout);

    while (fgets(input, sizeof(input), stdin) != NULL) {
        /*
         * Apply any time-based progress accumulated since the previous command.
         */
        updateRefueling(&controller);

        /*
         * BUG FIX: restore the pre-command safety check.
         * This catches an unsafe REFUELING state before another command runs.
         */
        automaticSafetyCheck(&controller);

        /*
         * Process the current command. The command may change pressure,
         * alignment, gate state, or the controller state itself.
         */
        handleCommand(&controller, input);

        /*
         * Apply any time-based change caused by entering or remaining in the
         * REFUELING state.
         */
        updateRefueling(&controller);

        /*
         * BUG FIX: restore the post-command safety check.
         * For example, SIM_PRESSURE 90 during REFUELING is detected in this
         * same command-processing cycle and causes an immediate ABORT.
         */
        automaticSafetyCheck(&controller);

        /* Publish the final state for this command-processing cycle. */
        sendTelemetry(&controller);
    }

    return 0;
}