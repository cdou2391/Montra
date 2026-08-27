"""Throttling the endpoints worth guessing at.

Sign-in matters most: unlimited, a password is only as strong as the attacker's
patience. Argon2 also makes each attempt expensive for us, so an unthrottled
login is a way to spend the server's CPU from outside it.

Counting lives in Redis so the limit holds across workers. If Redis is
unreachable the request is allowed — availability over enforcement, which is
why this is one control among several rather than the only one.
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


# Generous for a household app: a person fumbling their own password should
# never meet the limit, and a script will.
LOGIN = Limit(attempts=8, window=300)

# Per account as well as per address, to catch guessing spread across many
# addresses. Deliberately loose: a tight per-account limit lets anyone who
# knows your address lock you out, which is easier than the attack it prevents.
LOGIN_ACCOUNT = Limit(attempts=20, window=3600)

REGISTER = Limit(attempts=5, window=3600)
SENSITIVE = Limit(attempts=10, window=300)


def hit(bucket: str, key: str, limit: Limit) -> None:
    """Count one attempt against a bucket, raising once the limit is passed.

    Fixed window, not sliding: one round trip, and the worst case is two
    windows' attempts across a boundary — immaterial at these numbers.
    """
    if not settings.rate_limit_enabled:
        return

    connection = client()
    if connection is None:
        return

    # The window is part of the key, so it expires by moving on.
    slot = int(time.time() // limit.window)
    redis_key = f"ratelimit:{bucket}:{key}:{slot}"

    try:
        pipe = connection.pipeline()
        pipe.incr(redis_key)
        pipe.expire(redis_key, limit.window)
        used, _ = pipe.execute()
    except redis.RedisError:
        # Availability over enforcement. See the module note.
        logger.warning("rate limit store unavailable; allowing %s", bucket)
        return

    if int(used) > limit.attempts:
        elapsed = int(time.time()) % limit.window
        raise RateLimited(retry_after=max(1, limit.window - elapsed))


def clear(bucket: str, key: str, limit: Limit) -> None:
    """Forget the attempts in the current window.

    Called after a success, so four mistypes then the right password does not
    leave someone throttled.
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

    The socket address is the proxy's for every caller, so the first
    X-Forwarded-For entry is used — trusted only because nothing reaches the
    API except through that proxy.
    """
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
