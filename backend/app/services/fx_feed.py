"""Daily exchange rates from a published feed.

Frankfurter is primary: ECB rates, free, no key. It does not publish RWF —
this app's base currency — so a second free source fills the gap.

Best-effort. A feed being down is not the user's problem: stored rates stay
usable and the next run retries. What must never happen is a failure leaving a
*wrong* rate, so nothing is written unless a real number came back.
"""

import json
import logging
import urllib.error
import urllib.request
from decimal import Decimal, InvalidOperation

logger = logging.getLogger(__name__)

CURRENCY_FREAKS = "CURRENCY_FREAKS"
FRANKFURTER = "FRANKFURTER"
OPEN_ER_API = "OPEN_ER_API"

CURRENCY_FREAKS_URL = "https://api.currencyfreaks.com/v2.0/rates/latest"
FRANKFURTER_URL = "https://api.frankfurter.dev/v1/latest"
OPEN_ER_API_URL = "https://open.er-api.com/v6/latest"

# Long enough for a slow morning, short enough not to hold a worker.
TIMEOUT_SECONDS = 15


def _get(url: str) -> dict | None:
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "Montra/1.0"})
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            if response.status != 200:
                return None
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
        logger.warning("exchange rate feed unavailable: %s (%s)", url, exc)
        return None


def _as_decimal(value) -> Decimal | None:
    try:
        rate = Decimal(str(value))
    except (InvalidOperation, TypeError):
        return None
    return rate if rate.is_finite() and rate > 0 else None


def _from_currency_freaks(base: str, wanted: list[str]) -> dict[str, tuple[Decimal, str]]:
    """CurrencyFreaks, used only when a key is configured.

    Its free tier quotes against USD, so a non-USD base is crossed through it
    rather than assumed honoured. Both legs come from one response.
    """
    from app.core.config import settings

    key = (settings.currencyfreaks_api_key or "").strip()
    if not key:
        return {}

    symbols = ",".join(sorted({*wanted, base, "USD"}))
    payload = _get(f"{CURRENCY_FREAKS_URL}?apikey={key}&symbols={symbols}")
    if not payload or "rates" not in payload:
        return {}

    rates = payload["rates"]
    # Everything in the response is "one USD in X".
    usd_to_base = _as_decimal(rates.get(base)) if base != "USD" else Decimal(1)
    if usd_to_base is None:
        return {}

    found: dict[str, tuple[Decimal, str]] = {}
    for code in wanted:
        usd_to_code = _as_decimal(rates.get(code)) if code != "USD" else Decimal(1)
        if usd_to_code is None:
            continue
        # base -> code, via USD.
        found[code] = ((usd_to_code / usd_to_base), CURRENCY_FREAKS)
    return found


def fetch_all(base: str) -> dict[str, tuple[Decimal, str]]:
    """Every rate a feed publishes for one base, in one request.

    What makes the shared table cheap: tracking a new currency costs nothing.
    """
    base = base.upper()
    found: dict[str, tuple[Decimal, str]] = {}

    payload = _get(f"{FRANKFURTER_URL}?base={base}")
    for code, value in (payload or {}).get("rates", {}).items():
        rate = _as_decimal(value)
        if rate is not None:
            found[code.upper()] = (rate, FRANKFURTER)

    # Broader coverage, and the only one of the two that publishes RWF.
    payload = _get(f"{OPEN_ER_API_URL}/{base}")
    if payload and payload.get("result") == "success":
        for code, value in payload.get("rates", {}).items():
            code = code.upper()
            if code in found or code == base:
                continue
            rate = _as_decimal(value)
            if rate is not None:
                found[code] = (rate, OPEN_ER_API)

    return found


def fetch(base: str, symbols: list[str]) -> dict[str, tuple[Decimal, str]]:
    """One unit of `base` in each requested currency, with its source.

    CurrencyFreaks when keyed, then Frankfurter, then the keyless fallback for
    what is missing. What no feed publishes is absent rather than invented.
    """
    base = base.upper()
    wanted = [s.upper() for s in symbols if s.upper() != base]
    if not wanted:
        return {}

    found: dict[str, tuple[Decimal, str]] = dict(_from_currency_freaks(base, wanted))
    remaining = [c for c in wanted if c not in found]
    if not remaining:
        return found

    payload = _get(f"{FRANKFURTER_URL}?base={base}&symbols={','.join(remaining)}")
    for code, value in (payload or {}).get("rates", {}).items():
        rate = _as_decimal(value)
        if rate is not None:
            found[code.upper()] = (rate, FRANKFURTER)

    missing = [c for c in wanted if c not in found]
    if not missing:
        return found

    # Frankfurter does not publish these — RWF among them.
    payload = _get(f"{OPEN_ER_API_URL}/{base}")
    if payload and payload.get("result") == "success":
        rates = payload.get("rates", {})
        for code in missing:
            rate = _as_decimal(rates.get(code))
            if rate is not None:
                found[code] = (rate, OPEN_ER_API)

    still_missing = [c for c in wanted if c not in found]
    if still_missing:
        logger.info("no published rate for %s against %s", still_missing, base)
    return found
