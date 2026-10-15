import logging
import os

from fastapi import FastAPI, Request
from pydantic import BaseModel, Field, field_validator
import uvicorn

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("api")

SAFE_HEADERS = {
    "user-agent",
    "accept",
    "accept-language",
    "x-forwarded-for",
    "x-forwarded-proto",
    "x-cloud-trace-context",
    "forwarded",
    "host",
}

app = FastAPI(title="API", docs_url=None, redoc_url=None, openapi_url=None)


def service_name() -> str:
    return os.environ.get("K_SERVICE", os.environ.get("SERVICE_NAME", "run-svc-backend"))


def revision() -> str:
    return os.environ.get("K_REVISION", "local")


def request_view(request: Request) -> dict:
    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() in SAFE_HEADERS
    }
    client = request.client.host if request.client else None
    return {
        "service": service_name(),
        "revision": revision(),
        "method": request.method,
        "path": request.url.path,
        "client": client,
        "headers": headers,
    }


class ClientInfo(BaseModel):
    note: str = Field(default="", max_length=200)
    user_agent: str = Field(default="", max_length=500)
    accept_language: str = Field(default="", max_length=200)
    accept: str = Field(default="", max_length=300)

    @field_validator("note", "user_agent", "accept_language", "accept", mode="before")
    @classmethod
    def as_text(cls, value: object) -> str:
        if value is None:
            return ""
        if not isinstance(value, str):
            raise ValueError("texto inválido")
        return value.strip()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": service_name(), "revision": revision()}


@app.post("/v1/client-info")
def client_info(body: ClientInfo, request: Request) -> dict:
    log.info("client-info %s", request.method)
    return {"from_browser": body.model_dump(), "seen_by_api": request_view(request)}


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",  # nosec B104
        port=int(os.environ.get("PORT", "8080")),
        proxy_headers=True,
        forwarded_allow_ips="*",
        server_header=False,
    )
