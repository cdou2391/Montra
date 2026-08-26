"""Throttling the endpoints worth guessing at.

Sign-in is the one that matters: without a limit, a password is only as strong
as the attacker's patience. Argon2 makes each attempt expensive for us as well
as for them, which is the second reason to cap the rate — an unthrottled login
is a way to spend all of the server's CPU from outside it.

Counting lives in Redis so the limit holds across every worker rather than
per-process. If Redis is unreachable the request is allowed: an outage in the
cache should not lock everyone out of their own money. That is a deliberate
trade — availability over enforcement — and it is the reason this is one
control among several rather than the only one.
"""

import logging
import time
from dataclasses import dataclass

import redis

from app.core.config import settings
from app.core.errors import MontraError

logger = logging.getLogger(__name__)

_client: redis.Redis | None = None


def client() -> redis.Redis | None:
    global _client
    if _client is None:
        try:
            _client = redis.Redis.from_url(settings.redis_url, socket_timeout=0.25)
        except Exception:  # pragma: no cover - configuration error
            logger.exception("could not build a redis client for rate limiting")
            return None
    return _client


class RateLimited(MontraError):
    """429, with how long to wait."""

    status_code = 429
    code = "RATE_LIMITED"

    def __init__(self, retry_after: int):
        super().__init__(
            "Too many attempts. Wait a moment and try again.",
            code=self.code,
            details=[{"field": "retry_after", "message": str(retry_after)}],
        )
        self.retry_after = retry_after


@dataclass(frozen=True)
class Limit:
    """`attempts` within `window` seconds."""

    attempts: int
    window: int


# Sign-in and registration are guessed at; the rest are just expensive. The
# numbers are deliberately generous for a household app — a person fumbling
# their own password should never meet the limit, and a script will.
LOGIN = Limit(attempts=8, window=300)

# Counting per account as well as per address is what catches guessing spread
# across many addresses. It is deliberately much looser, because a tight
# per-account limit hands anyone who knows your email address a way to keep
# you locked out of your own money — the attack is easier than the one the
# limit prevents. Twenty an hour stops sustained guessing without a person
# who forgot their password ever meeting it.
LOGIN_ACCOUNT = Limit(attempts=20, window=3600)

REGISTER = Limit(attempts=5, window=3600)
SENSITIVE = Limit(attempts=10, window=300)


def hit(bucket: str, key: str, limit: Limit) -> None:
    """Count one attempt against a bucket, raising once the limit is passed.

    A fixed window rather than a sliding one: it is one round trip, and the
    worst case is that an attacker gets two windows' worth of attempts across
    a boundary. For a login cap measured in single digits that is not the
    difference between safe and unsafe.
    """
    if not settings.rate_limit_enabled:
        return

    connection = client()
    if connection is None:
        return

    # The window is part of the key, so it expires by moving on rather than
    # needing to be reset.
    slot = int(time.time() // limit.window)
    redis_key = f"ratelimit:{bucket}:{key}:{slot}"

    try:
        pipe = connection.pipeline()
        pipe.incr(redis_key)
        pipe.expire(redis_key, limit.window)
        used, _ = pipe.execute()
    except redis.RedisError:
        # Availability over enforcement, deliberately. See the module note.
        logger.warning("rate limit store unavailable; allowing %s", bucket)
        return

    if int(used) > limit.attempts:
        elapsed = int(time.time()) % limit.window
        raise RateLimited(retry_after=max(1, limit.window - elapsed))


def clear(bucket: str, key: str, limit: Limit) -> None:
    """Forget the attempts in the current window.

    Called after a success, so someone who mistypes a password four times and
    then gets it right is not left throttled for the rest of the window.
    """
    connection = client()
    if connection is None:
        return
    slot = int(time.time() // limit.window)
    try:
        connection.delete(f"ratelimit:{bucket}:{key}:{slot}")
    except redis.RedisError:
        return


def caller(request) -> str:
    """Who to count against.

    The proxy sits in front of the API, so the socket address is the proxy's
    for every caller. The first entry of X-Forwarded-For is the client as the
    proxy saw it — trusted only because nothing reaches the API except through
    that proxy.
    """
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
