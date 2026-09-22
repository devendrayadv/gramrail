"""Authenticated, bot-scoped runtime API. Keys are trusted backend credentials."""
import hmac
import importlib.resources
import logging
import re
import threading
from contextlib import asynccontextmanager
from typing import Annotated, Any, Literal

from fastapi import Depends, FastAPI, Header, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field

from . import __version__
from .adapters.bot_api import BotAPI, FakeBotAPI
from .config import Config
from .delivery import Delivery
from .errors import Forbidden, InvalidInput, RailError
from .jobs import JobQueue
from .modules.manifest import MODULES
from .store import Store
from .telegram import TelegramRouter
from .workflows import WorkflowEngine, WorkflowSpec

logger = logging.getLogger("gramrail")
MAX_BODY = 262144


class LimitBody:
    def __init__(self, app: Any):
        self.app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http" or scope["method"] not in ("POST", "PUT", "PATCH"):
            await self.app(scope, receive, send)
            return
        data = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            data.extend(message.get("body", b""))
            if len(data) > MAX_BODY:
                response = JSONResponse({"error": {"code": "body_too_large", "message": "Request body exceeds 256 KiB."}}, status_code=413)
                await response(scope, receive, send)
                return
            if not message.get("more_body", False):
                break
        pending = True

        async def replay() -> Any:
            nonlocal pending
            if pending:
                pending = False
                return {"type": "http.request", "body": bytes(data), "more_body": False}
            return await receive()
        await self.app(scope, replay, send)


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class JobRequest(Model):
    kind: str = Field(pattern=r"^[a-z][a-zA-Z0-9_.-]{0,99}$")
    payload: dict[str, Any]
    dedupe_key: str | None = Field(default=None, min_length=1, max_length=200)
    priority: int = Field(default=50, ge=0, le=100)
    run_after: float | None = None
    max_attempts: int = Field(default=5, ge=1, le=100)
    recovery: Literal["retry", "uncertain"] = "retry"


class ClaimRequest(Model):
    kinds: list[str] = Field(min_length=1, max_length=50)
    lease_seconds: float = Field(default=30, ge=5, le=3600)


class LeaseRequest(Model):
    lease_token: str = Field(min_length=1, max_length=128)


class CompleteRequest(LeaseRequest):
    result: dict[str, Any] = Field(default_factory=dict)


class FailRequest(LeaseRequest):
    error: str = Field(pattern=r"^[a-zA-Z0-9_.:-]{1,100}$")
    retry_in: float | None = Field(default=None, ge=0, le=604800)
    uncertain: bool = False


class HeartbeatRequest(LeaseRequest):
    lease_seconds: float = Field(default=30, ge=5, le=3600)
    progress: dict[str, Any] | None = None


class MessageRequest(Model):
    chat_id: int = Field(strict=True, ge=-(2**53 - 1), le=2**53 - 1)
    text: str = Field(min_length=1, max_length=4096)
    dedupe_key: str | None = Field(default=None, min_length=1, max_length=200)
    priority: int = Field(default=80, ge=0, le=100)
    run_after: float | None = None


class StartRequest(Model):
    definition: WorkflowSpec
    data: dict[str, Any] = Field(default_factory=dict)
    dedupe_key: str | None = Field(default=None, min_length=1, max_length=200)


class SignalRequest(Model):
    event: str = Field(min_length=1, max_length=64)
    event_key: str = Field(min_length=1, max_length=200)
    expected_revision: int = Field(ge=0)
    patch: dict[str, Any] = Field(default_factory=dict)
    jobs: list[JobRequest] = Field(default_factory=list, max_length=20)


def external_kind(kind: str) -> None:
    if kind.startswith(("telegram.", "gramrail.")):
        raise Forbidden("Reserved job kind. Use the messages API for Telegram delivery.")


def public_job(job: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in job.items() if key != "lease_token"}


def create_app(config: Config, *, store: Store | None = None, live: bool = False,
               background: bool = True, credentials: dict[str, str] | None = None,
               adapters: dict[str, BotAPI | FakeBotAPI] | None = None) -> FastAPI:
    secrets = config.credentials(live=live) if credentials is None else credentials
    auth_values = [secrets[name] for name in [config.admin_key_env, *(bot.api_key_env for bot in config.bots)] if name in secrets]
    if not auth_values or any(not re.fullmatch(r"[!-~]{24,256}", key) for key in auth_values) or len(set(auth_values)) != len(auth_values):
        raise InvalidInput("Provide distinct API keys of 24..256 printable non-space ASCII characters.")
    database = store or Store(config.database)
    queue, workflows = JobQueue(database), WorkflowEngine(database)
    router = TelegramRouter(database, config)
    if adapters is None:
        adapters = {bot.id: BotAPI(secrets[bot.token_env]) if live else FakeBotAPI() for bot in config.bots}
    delivery = Delivery(database, adapters)
    stop = threading.Event()

    def send_loop() -> None:
        while not stop.is_set():
            for bot in config.bots:
                if stop.is_set():
                    break
                try:
                    delivery.tick(bot.id)
                except Exception:
                    # Avoid printing request payloads or token-bearing network exceptions.
                    logger.error("Delivery tick failed for bot %s; inspect the runtime state.", bot.id)
            stop.wait(0.04)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        thread = threading.Thread(target=send_loop, name="gramrail-delivery", daemon=True) if background else None
        if thread:
            thread.start()
        yield
        stop.set()
        if thread:
            thread.join(timeout=15)
        for adapter in adapters.values():
            adapter.close()

    app = FastAPI(title="GramRail Runtime", version=__version__, lifespan=lifespan,
                  description="Trusted backend API. Never embed runtime keys in public clients.",
                  docs_url="/api/docs", redoc_url=None)
    app.add_middleware(LimitBody)
    app.state.store, app.state.delivery, app.state.router = database, delivery, router
    app.state.config, app.state.live = config, live

    @app.middleware("http")
    async def headers(request: Request, call_next: Any) -> Any:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Frame-Options"] = "DENY"
        if request.url.path.startswith("/console"):
            response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        return response

    @app.exception_handler(RailError)
    async def rail_error(request: Request, exc: RailError) -> JSONResponse:
        return JSONResponse({"error": {"code": exc.code, "message": str(exc)}}, status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse({"error": {"code": "validation_error", "message": "Request did not match the API schema.",
                                      "fields": [list(error["loc"]) for error in exc.errors()]}}, status_code=422)

    security = HTTPBearer(auto_error=False)

    def authenticate(auth: Annotated[HTTPAuthorizationCredentials | None, Depends(security)]) -> str:
        if auth is None or auth.scheme.lower() != "bearer" or not auth.credentials.isascii():
            raise Forbidden("Provide a valid Authorization: Bearer API key.")
        if config.admin_key_env in secrets and hmac.compare_digest(auth.credentials, secrets[config.admin_key_env]):
            return "*"
        for bot in config.bots:
            if bot.api_key_env in secrets and hmac.compare_digest(auth.credentials, secrets[bot.api_key_env]):
                return bot.id
        raise Forbidden("Invalid API key.")

    def bot_scope(bot_id: str, principal: Annotated[str, Depends(authenticate)]) -> str:
        if principal not in ("*", bot_id):
            raise Forbidden("This key does not have access to that bot.")
        config.bot(bot_id)
        return bot_id

    scope = Depends(bot_scope)

    @app.get("/health")
    def health() -> dict[str, Any]:
        with database.read() as conn:
            conn.execute("SELECT 1")
        return {"status": "ok", "version": __version__, "mode": "live" if live else "simulation"}

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse("/console")

    @app.get("/console", include_in_schema=False)
    def console() -> FileResponse:
        return FileResponse(str(importlib.resources.files("gramrail").joinpath("web/index.html")))

    @app.get("/console/{asset}", include_in_schema=False)
    def asset(asset: Literal["app.js", "style.css"]) -> FileResponse:
        return FileResponse(str(importlib.resources.files("gramrail").joinpath("web/" + asset)))

    @app.get("/api/v1/bots")
    def bots(principal: Annotated[str, Depends(authenticate)]) -> dict[str, Any]:
        return {"bots": [{"id": bot.id, "name": bot.name, "modules": bot.modules} for bot in config.bots if principal in ("*", bot.id)],
                "mode": "live" if live else "simulation"}

    @app.get("/api/v1/modules")
    def modules(principal: Annotated[str, Depends(authenticate)]) -> list[dict[str, Any]]:
        return [{"name": item.name, "description": item.description, "requires": item.requires, "capabilities": item.capabilities} for item in MODULES.values()]

    @app.post("/api/v1/bots/{bot_id}/updates")
    def updates(body: dict[str, Any], bot_id: str = scope) -> dict[str, Any]:
        return router.ingest(bot_id, body)

    @app.post("/webhooks/{bot_id}")
    def webhook(bot_id: str, body: dict[str, Any],
                x_telegram_bot_api_secret_token: Annotated[str | None, Header()] = None) -> dict[str, Any]:
        bot = config.bot(bot_id)
        expected = secrets.get(bot.webhook_secret_env)
        supplied = x_telegram_bot_api_secret_token
        if not live or not expected or not supplied or not supplied.isascii() or not hmac.compare_digest(supplied, expected):
            raise Forbidden("Invalid webhook secret or webhook disabled in simulation.")
        return router.ingest(bot_id, body)

    @app.post("/api/v1/bots/{bot_id}/messages", status_code=202)
    def message(body: MessageRequest, bot_id: str = scope) -> dict[str, Any]:
        return public_job(delivery.send_text(bot_id, **body.model_dump()))

    @app.post("/api/v1/bots/{bot_id}/jobs", status_code=202)
    def enqueue(body: JobRequest, bot_id: str = scope) -> dict[str, Any]:
        external_kind(body.kind)
        return public_job(queue.enqueue(bot_id, **body.model_dump()))

    @app.get("/api/v1/bots/{bot_id}/jobs")
    def list_jobs(bot_id: str = scope, state: str | None = None,
                  limit: int = Query(default=50, ge=1, le=200)) -> list[dict[str, Any]]:
        return [public_job(job) for job in queue.list(bot_id, state, limit)]

    @app.post("/api/v1/bots/{bot_id}/jobs/claim")
    def claim(body: ClaimRequest, bot_id: str = scope) -> dict[str, Any] | None:
        for kind in body.kinds:
            external_kind(kind)
        return queue.claim(bot_id, body.kinds, body.lease_seconds)

    @app.get("/api/v1/bots/{bot_id}/jobs/{job_id}")
    def get_job(job_id: str, bot_id: str = scope) -> dict[str, Any]:
        return public_job(queue.get(bot_id, job_id))

    @app.post("/api/v1/bots/{bot_id}/jobs/{job_id}/complete")
    def complete(job_id: str, body: CompleteRequest, bot_id: str = scope) -> dict[str, Any]:
        return public_job(queue.complete(bot_id, job_id, body.lease_token, body.result))

    @app.post("/api/v1/bots/{bot_id}/jobs/{job_id}/fail")
    def fail(job_id: str, body: FailRequest, bot_id: str = scope) -> dict[str, Any]:
        return public_job(queue.fail(bot_id, job_id, body.lease_token, body.error, retry_in=body.retry_in, uncertain=body.uncertain))

    @app.post("/api/v1/bots/{bot_id}/jobs/{job_id}/heartbeat")
    def heartbeat(job_id: str, body: HeartbeatRequest, bot_id: str = scope) -> dict[str, Any]:
        return public_job(queue.heartbeat(bot_id, job_id, body.lease_token, lease_seconds=body.lease_seconds, progress=body.progress))

    @app.post("/api/v1/bots/{bot_id}/jobs/{job_id}/cancel")
    def cancel(job_id: str, bot_id: str = scope) -> dict[str, Any]:
        return public_job(queue.cancel(bot_id, job_id))

    @app.post("/api/v1/bots/{bot_id}/workflows", status_code=201)
    def start(body: StartRequest, bot_id: str = scope) -> dict[str, Any]:
        return workflows.start(bot_id, body.definition, body.data, body.dedupe_key)

    @app.get("/api/v1/bots/{bot_id}/workflows")
    def list_workflows(bot_id: str = scope, limit: int = Query(default=50, ge=1, le=200)) -> list[dict[str, Any]]:
        return workflows.list(bot_id, limit)

    @app.get("/api/v1/bots/{bot_id}/workflows/{run_id}")
    def get_workflow(run_id: str, bot_id: str = scope) -> dict[str, Any]:
        return workflows.get(bot_id, run_id)

    @app.post("/api/v1/bots/{bot_id}/workflows/{run_id}/signals")
    def signal(run_id: str, body: SignalRequest, bot_id: str = scope) -> dict[str, Any]:
        for job in body.jobs:
            external_kind(job.kind)
            if job.dedupe_key is not None:
                raise InvalidInput("Transition job idempotency keys are generated from the workflow event.")
        return workflows.signal(bot_id, run_id, body.event, body.event_key,
                                expected_revision=body.expected_revision, patch=body.patch,
                                jobs=[job.model_dump(exclude={"dedupe_key"}) for job in body.jobs])

    @app.get("/api/v1/bots/{bot_id}/events")
    def events(bot_id: str = scope, after: int = Query(default=0, ge=0),
               limit: int = Query(default=100, ge=1, le=200)) -> list[dict[str, Any]]:
        return database.events(bot_id, after, limit)

    return app
