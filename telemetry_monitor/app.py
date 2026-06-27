from fastapi import FastAPI
import uvicorn

app = FastAPI(
    title="Refueling Safety Telemetry Monitor",
    version="0.1.0",
)


@app.get("/health")
def health_check() -> dict[str, str]:
    """
    Basic health endpoint for local testing, Docker health checks,
    and future Prometheus/Grafana observability integration.
    """
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )