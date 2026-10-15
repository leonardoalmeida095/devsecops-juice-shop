import asyncio
import logging
import os
import time

import google.auth.transport.requests
import google.oauth2.id_token
import httpx
from fastapi import FastAPI, Form, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("web")

API_URL = os.environ.get("API_URL", "http://127.0.0.1:8081").rstrip("/")
API_AUTH = os.environ.get("API_AUTH", "true").lower() == "true"
SECURITY_HEADERS = {
    "content-security-policy": (
        "default-src 'self'; img-src 'self'; style-src 'self'; "
        "script-src 'none'; form-action 'self'; frame-ancestors 'none'; base-uri 'self'"
    ),
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
    "permissions-policy": "camera=(), microphone=(), geolocation=()",
    "cross-origin-resource-policy": "same-origin",
    "cross-origin-opener-policy": "same-origin",
    "cross-origin-embedder-policy": "require-corp",
    "cache-control": "no-store",
}

app = FastAPI(title="Web", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
_token = {"value": "", "exp": 0.0}


def service_name() -> str:
    return os.environ.get("K_SERVICE", os.environ.get("SERVICE_NAME", "run-svc-frontend"))


def revision() -> str:
    return os.environ.get("K_REVISION", "local")


def page(request: Request, **extra: object) -> dict:
    context = {"service": service_name(), "revision": revision(), "request": request}
    context.update(extra)
    return context


def browser_from(request: Request, note: str = "") -> dict[str, str]:
    return {
        "note": note.strip()[:200],
        "user_agent": request.headers.get("user-agent", "")[:500],
        "accept_language": request.headers.get("accept-language", "")[:200],
        "accept": request.headers.get("accept", "")[:300],
    }


def clear_token() -> None:
    _token["value"] = ""
    _token["exp"] = 0.0


def fetch_token() -> str:
    now = time.time()
    if _token["value"] and now < _token["exp"]:
        return _token["value"]
    auth_request = google.auth.transport.requests.Request()
    token = google.oauth2.id_token.fetch_id_token(auth_request, API_URL)
    _token["value"] = token
    _token["exp"] = now + 45 * 60
    return token


async def api_headers() -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if API_AUTH:
        token = await asyncio.to_thread(fetch_token)
        headers["Authorization"] = f"Bearer {token}"
    return headers


async def api_request(method: str, path: str, body: dict | None = None) -> httpx.Response:
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            headers = await api_headers()
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.request(method, f"{API_URL}{path}", headers=headers, json=body)
            if response.status_code in (401, 403) and API_AUTH and attempt < 2:
                clear_token()
                await asyncio.sleep(1 + attempt)
                continue
            if response.status_code == 503 and attempt < 2:
                await asyncio.sleep(1 + attempt)
                continue
            log.info("api %s %s -> %s", method, path, response.status_code)
            return response
        except httpx.HTTPError as exc:
            last_error = exc
            log.info("api %s %s erro %s", method, path, exc.__class__.__name__)
            await asyncio.sleep(1 + attempt)
    raise last_error or httpx.ConnectError("api indisponível")


def render_error(request: Request, status: int, message: str) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "error.html",
        page(request, status=status, message=message),
        status_code=status,
    )


async def render_visit(request: Request, note: str = "") -> HTMLResponse:
    payload = browser_from(request, note)
    try:
        response = await api_request("POST", "/v1/client-info", payload)
    except httpx.HTTPError:
        return render_error(request, 502, "A API não respondeu.")
    if response.status_code >= 400:
        return render_error(request, 502, "A API recusou os dados do navegador.")
    body = response.json()
    return templates.TemplateResponse(
        request,
        "index.html",
        page(request, sent=body.get("from_browser", payload), api=body.get("seen_by_api", {})),
    )


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    for key, value in SECURITY_HEADERS.items():
        response.headers[key] = value
    if "server" in response.headers:
        del response.headers["server"]
    return response


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": service_name(), "revision": revision()}


@app.get("/health/ready")
async def ready() -> JSONResponse:
    try:
        response = await api_request("GET", "/health")
    except httpx.HTTPError:
        return JSONResponse({"status": "down"}, status_code=502)
    if response.status_code != 200:
        return JSONResponse({"status": "down", "api_status": response.status_code}, status_code=502)
    payload = response.json()
    return JSONResponse(
        {
            "status": "ok",
            "service": service_name(),
            "revision": revision(),
            "api": payload.get("service"),
            "api_revision": payload.get("revision"),
        }
    )


@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    return await render_visit(request)


@app.post("/", response_class=HTMLResponse)
async def send_note(request: Request, note: str = Form(default="")) -> HTMLResponse:
    return await render_visit(request, note)


@app.exception_handler(RequestValidationError)
async def invalid_form(request: Request, exc: RequestValidationError) -> HTMLResponse:
    log.info("formulario invalido %s", len(exc.errors()))
    return render_error(request, 400, "Não foi possível ler o formulário.")


@app.exception_handler(404)
async def not_found(request: Request, exc: Exception) -> HTMLResponse:
    if request.url.path.startswith("/health"):
        return JSONResponse({"detail": "not found"}, status_code=404)
    return render_error(request, 404, "Página não encontrada.")


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",  # nosec B104
        port=int(os.environ.get("PORT", "8080")),
        proxy_headers=True,
        forwarded_allow_ips="*",
        server_header=False,
    )
