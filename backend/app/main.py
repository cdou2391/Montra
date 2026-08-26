"""Montra API application factory."""

import uuid

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.errors import (
    MontraError,
    montra_error_handler,
    unhandled_error_handler,
    validation_error_handler,
)
from app.core.logging import configure_logging, request_id_ctx

configure_logging()

app = FastAPI(
    title="Montra API",
    version="0.1.0",
    description="Personal and household finance tracking.",
    openapi_url=f"{settings.api_v1_prefix}/openapi.json",
    docs_url=f"{settings.api_v1_prefix}/docs",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    """Correlate every log line and error envelope with a request id."""
    request_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:16]}"
    token = request_id_ctx.set(request_id)
    try:
        response = await call_next(request)
    finally:
        request_id_ctx.reset(token)
    response.headers["X-Request-ID"] = request_id
    return response


# The API serves JSON, never a document, so the policy can be as narrow as it
# gets: nothing may be loaded, and nothing may embed it. The frontend's own
# policy is a separate matter and belongs at the proxy.
API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"


SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})

# Bodies larger than this are refused before they are read. Attachments do not
# come through here — they go straight to object storage on a signed URL — so
# nothing legitimate posted to the API is anywhere near a megabyte.
MAX_BODY_BYTES = 1_048_576


@app.middleware("http")
async def enforce_request_limits(request: Request, call_next):
    """Reject an oversized body on its declared length.

    Cheaper than reading it: a client that lies about Content-Length still has
    to get past the proxy's own cap, and this stops the honest-but-enormous
    request from being parsed at all.
    """
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        return JSONResponse(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            content={
                "error": {
                    "code": "REQUEST_TOO_LARGE",
                    "message": "That request is too large.",
                    "details": [],
                }
            },
        )
    return await call_next(request)


@app.middleware("http")
async def verify_same_origin(request: Request, call_next):
    """Reject a state-changing request that came from somewhere else.

    The session is a cookie, so a browser will attach it to a request the user
    never meant to make. SameSite=Lax already blocks the cross-site form post,
    but it is one setting away from being wrong and says nothing about older
    browsers — so the origin is checked as well.

    Only unsafe methods are checked, and only when the browser told us where
    the request came from. A native client or a script sends no Origin at all;
    those are not the requests this protects against, because they carry no
    ambient cookie to abuse.
    """
    if request.method in SAFE_METHODS:
        return await call_next(request)

    origin = request.headers.get("origin")
    if origin is None:
        return await call_next(request)

    if origin not in settings.cors_origin_list and origin not in settings.same_origin_list:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={
                "error": {
                    "code": "CROSS_ORIGIN_REFUSED",
                    "message": "That request came from an origin this API does not accept.",
                    "details": [],
                }
            },
        )
    return await call_next(request)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Content-Security-Policy", API_CSP)
    response.headers.setdefault("Permissions-Policy", "geolocation=(), camera=(), microphone=()")
    response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
    if settings.is_production:
        # Only in production: sending this from a development server would
        # pin a browser to HTTPS on localhost for a year.
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
    return response


@app.on_event("startup")
def refuse_unsafe_production() -> None:
    """Fail loudly rather than run wide open.

    Every one of these is a setting that is right on a laptop and wrong in
    public, and each is the kind of thing that is noticed after it matters.
    """
    if not settings.is_production:
        return
    problems = settings.production_problems()
    if problems:
        raise RuntimeError(
            "Refusing to start in production with unsafe settings:\n  - "
            + "\n  - ".join(problems)
        )


app.add_exception_handler(MontraError, montra_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)
app.add_exception_handler(Exception, unhandled_error_handler)

app.include_router(api_router, prefix=settings.api_v1_prefix)
