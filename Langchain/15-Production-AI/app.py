"""
Module 15 mini project: AI Chat API.

Exposes a LangChain chatbot over HTTP, with the things a service needs that a
script does not: authentication, structured logging, request ids, streaming,
health checks, and provider errors translated into sensible HTTP status codes.

    GET  /health        liveness, no auth, no model call
    GET  /config        what the service is configured with, no secrets
    POST /chat          answer a question, returns JSON
    POST /chat/stream   the same, streamed as server-sent events

Run it:
    uvicorn app:app --reload --port 8000

Then:
    curl http://localhost:8000/health
    curl -X POST http://localhost:8000/chat ^
        -H "X-API-Key: local-dev-key" ^
        -H "Content-Type: application/json" ^
        -d "{\"message\": \"hello\"}"
"""

import json
import logging
import os
import sys
import time
import uuid
from contextvars import ContextVar
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import ConfigError, active_model_name, arun_with_fallback, build_model
from common.errors import is_bad_argument, is_model_missing, is_quota_exhausted, is_rate_limited
from common.models import api_keys, model_names

SYSTEM_PROMPT = "You are a concise assistant. Answer in at most three sentences."

# The key clients send to this service. It is NOT the Gemini key: the provider
# key stays on the server and is never accepted from, or exposed to, a caller.
SERVICE_KEYS = {
    key.strip()
    for key in os.getenv("SERVICE_API_KEYS", "local-dev-key").split(",")
    if key.strip()
}

# Carries the request id into log records without threading it through every
# function call.
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIdFilter(logging.Filter):
    def filter(self, record):
        record.request_id = request_id_var.get()
        return True


handler = logging.StreamHandler()
handler.setFormatter(
    logging.Formatter("%(asctime)s %(levelname)s [%(request_id)s] %(message)s")
)
handler.addFilter(RequestIdFilter())

log = logging.getLogger("chat-api")
log.setLevel(logging.INFO)
log.addHandler(handler)
log.propagate = False

app = FastAPI(title="AI Chat API", version="1.0.0")


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    temperature: float = Field(default=0.3, ge=0.0, le=2.0)


class ChatResponse(BaseModel):
    reply: str
    model: str
    request_id: str
    latency_ms: int
    input_tokens: int | None = None
    output_tokens: int | None = None


def require_api_key(x_api_key: str = Header(default="")) -> str:
    """
    Authenticate the caller.

    An LLM endpoint costs real money per request, so leaving it open is not
    merely untidy. This is the simplest thing that works; a real service would
    use per-client keys with rate limits attached, or OAuth.
    """
    if x_api_key not in SERVICE_KEYS:
        raise HTTPException(status_code=401, detail="invalid or missing X-API-Key")
    return x_api_key


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """
    Give every request an id, log it, and time it.

    The id goes into the response headers as well as the logs, so a user
    reporting a problem can quote something that finds the exact request.
    """
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
    request_id_var.set(request_id)
    started = time.perf_counter()

    response = await call_next(request)

    elapsed = int((time.perf_counter() - started) * 1000)
    response.headers["X-Request-ID"] = request_id
    log.info(
        "%s %s -> %s in %dms",
        request.method,
        request.url.path,
        response.status_code,
        elapsed,
    )
    return response


def http_error_for(error: Exception) -> HTTPException:
    """
    Translate a provider error into an HTTP status the caller can act on.

    This mapping is the difference between an API and a wrapper. A client
    seeing 429 with Retry-After knows to back off; a client seeing 500 knows
    only that something broke, and will usually retry immediately and make it
    worse.
    """
    if is_quota_exhausted(error) or is_rate_limited(error):
        return HTTPException(
            status_code=429,
            detail="upstream model quota exhausted, try again later",
            headers={"Retry-After": "60"},
        )
    if is_model_missing(error):
        return HTTPException(status_code=502, detail="configured model is unavailable")
    if is_bad_argument(error):
        return HTTPException(status_code=502, detail="upstream rejected the request")
    if isinstance(error, ConfigError):
        return HTTPException(status_code=503, detail="service is not configured")
    return HTTPException(status_code=502, detail="upstream model call failed")


@app.get("/health")
async def health() -> dict:
    """
    Liveness check. No auth, no model call, no cost.

    Deliberately does not call the model. A health check that costs a request
    will exhaust a quota all by itself once a load balancer starts polling it
    every few seconds.
    """
    return {"status": "ok", "model": active_model_name()}


@app.get("/config")
async def config(_: str = Depends(require_api_key)) -> dict:
    """What the service is configured with. Counts keys, never returns them."""
    return {
        "models": model_names(),
        "api_keys_configured": len(api_keys()),
        "service_keys_configured": len(SERVICE_KEYS),
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, _: str = Depends(require_api_key)) -> ChatResponse:
    started = time.perf_counter()
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=payload.message),
    ]

    try:
        response = await arun_with_fallback(
            lambda model: model.ainvoke(messages),
            verbose=False,
            temperature=payload.temperature,
            max_output_tokens=400,
        )
    except Exception as error:
        # log the real cause, return a sanitised message. provider errors can
        # contain project ids and quota details a caller has no business seeing.
        log.warning("model call failed: %s", str(error).splitlines()[0][:200])
        raise http_error_for(error) from error

    usage = response.usage_metadata or {}
    elapsed = int((time.perf_counter() - started) * 1000)
    log.info(
        "chat ok model=%s in=%s out=%s",
        response.response_metadata.get("model_name", active_model_name()),
        usage.get("input_tokens"),
        usage.get("output_tokens"),
    )

    return ChatResponse(
        reply=str(response.text).strip(),
        model=response.response_metadata.get("model_name", active_model_name()),
        request_id=request_id_var.get(),
        latency_ms=elapsed,
        input_tokens=usage.get("input_tokens"),
        output_tokens=usage.get("output_tokens"),
    )


@app.post("/chat/stream")
async def chat_stream(payload: ChatRequest, _: str = Depends(require_api_key)):
    """
    Stream the answer as server-sent events.

    Streaming changes error handling in a way that is easy to miss. Once the
    first chunk is sent the status code is already 200, so a later failure
    cannot become a 500. It has to be reported inside the stream, which is why
    an error event exists below.
    """
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=payload.message),
    ]
    request_id = request_id_var.get()

    async def events():
        try:
            model = build_model(model_names()[0], api_keys()[0], temperature=payload.temperature)
            async for chunk in model.astream(messages):
                text = str(chunk.text)
                if text:
                    yield f"data: {json.dumps({'delta': text})}\n\n"
        except Exception as error:
            log.warning("stream failed: %s", str(error).splitlines()[0][:200])
            detail = http_error_for(error).detail
            yield f"data: {json.dumps({'error': detail})}\n\n"

        yield f"data: {json.dumps({'done': True, 'request_id': request_id})}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Request-ID": request_id},
    )
