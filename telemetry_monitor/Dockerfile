# Use a lightweight Linux Python image as the runtime environment.
FROM python:3.12-slim

# Set the working directory for the FastAPI telemetry monitor.
WORKDIR /app

# Install GCC so the Linux container can compile controller.c.
#
# We compile the C controller inside Docker because controller.exe is a
# Windows executable and cannot run directly inside this Linux container.

# RUN apt-get update \
#     && apt-get install -y --no-install-recommends gcc \
#     && rm -rf /var/lib/apt/lists/*

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy Python dependency list first.
# This keeps Docker build caching efficient when only source code changes.
COPY telemetry_monitor/requirements.txt .

# Install Python dependencies for FastAPI and Prometheus metrics.
RUN pip install --no-cache-dir -r requirements.txt

# Copy the Python telemetry monitor source files.
COPY telemetry_monitor/app.py .
COPY telemetry_monitor/telemetry_parser.py .
COPY telemetry_monitor/simulator_client.py .

# Copy the C controller source code into the Linux container.
COPY controller/controller.c /controller/controller.c

# Compile the C controller into a Linux executable.
#
# Output:
# /controller/controller
RUN gcc /controller/controller.c -o /controller/controller

# FastAPI listens on port 8000.
EXPOSE 8000

# Start the FastAPI telemetry monitor.
CMD ["python", "app.py"]