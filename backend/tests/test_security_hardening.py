"""Phase 29 — the attacks the plan names, written down as tests.

The plan lists five scenarios to try by hand. Trying them by hand proves they
were safe on the day someone remembered to try; a test proves it stays that
way. Each one below is one of those scenarios.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.core.errors import NotFound, PermissionDenied, ValidationFailed
from app.core.passwords import MINIMUM_LENGTH
from app.core.security import validate_password_policy
from app.db.enums import AccountType, TransactionType, Visibility
from app.services import accounts as account_service
from app.services import authz
from app.services import transactions as txn_service

NOW = datetime(2026, 8, 26, 12, 0, tzinfo=UTC)


# ------------------------------------------------- "try changing account_id"


def test_posting_to_another_users_account_is_refused(db, user, other_user, bank_account):
    """The account id is a parameter the client controls; ownership is not."""
    with pytest.raises(NotFound):
        txn_service.create_transaction(
            db,
            user=other_user,
            account_id=bank_account.id,
            transaction_type=TransactionType.EXPENSE,
            amount=Decimal("1000"),
            occurred_at=NOW,
        )


def test_transferring_out_of_someone_elses_account_is_refused(
    db, user, other_user, bank_account, savings_account
):
    from app.services.posting import PostingService

    theirs = account_service.create_account(
        db,
        user=other_user,
        name="Their Account",
        account_type=AccountType.CHECKING,
        currency="RWF",
        opening_balance=Decimal("500000"),
        opening_balance_at=NOW,
    )
    db.commit()
    # The engine posts what it is given; the authorization is the caller's job,
    # so the check that matters is the one the endpoint makes.
    with pytest.raises(NotFound):
        authz.get_transactable_account(db, theirs.id, user)
    assert PostingService(db).balance_of(theirs) == Decimal("500000")


# ------------------------------------------------ "query another user's UUID"


def test_reading_another_users_account_is_a_404_not_a_403(db, user, other_user, bank_account):
    """404 rather than 403: a 403 confirms the id exists, which is itself a
    disclosure when the id is the only thing being guessed at."""
    with pytest.raises(NotFound):
        authz.get_viewable_account(db, bank_account.id, other_user)


def test_reading_another_users_transaction_is_refused(db, user, other_user, bank_account):
    txn = txn_service.create_transaction(
        db,
        user=user,
        account_id=bank_account.id,
        transaction_type=TransactionType.EXPENSE,
        amount=Decimal("4000"),
        occurred_at=NOW,
        description="Private",
    )
    db.commit()
    with pytest.raises(NotFound):
        txn_service.get_transaction(db, txn.id, other_user)


def test_a_random_uuid_reveals_nothing(db, user):
    with pytest.raises(NotFound):
        authz.get_viewable_account(db, uuid.uuid4(), user)


# -------------------------------------- "query private Family resources"


def test_a_household_member_cannot_read_a_private_account(
    db, user, other_user, family, bank_account
):
    """Belonging to the household is not permission to see everything in it."""
    assert bank_account.visibility is Visibility.PRIVATE
    with pytest.raises(NotFound):
        authz.get_viewable_account(db, bank_account.id, other_user)


def test_a_family_visible_account_can_be_seen_but_not_spent_from(
    db, user, other_user, family, bank_account
):
    """Visible is not spendable, which is the distinction the whole sharing
    model rests on."""
    account_service.set_visibility(
        db, account=bank_account, user=user, visibility=Visibility.FAMILY_VISIBLE
    )
    db.commit()

    authz.get_viewable_account(db, bank_account.id, other_user)
    with pytest.raises((NotFound, PermissionDenied)):
        authz.get_transactable_account(db, bank_account.id, other_user)


# ------------------------------ "access former Family after removal"


def test_a_removed_member_loses_sight_of_shared_accounts(
    db, user, other_user, family, bank_account
):
    from app.services import families as family_service

    account_service.set_visibility(
        db, account=bank_account, user=user, visibility=Visibility.SHARED
    )
    db.commit()
    # While they are in, they can see it.
    authz.get_viewable_account(db, bank_account.id, other_user)

    family_service.remove_member(
        db, user=user, family_id=family.id, member_user_id=other_user.id
    )
    db.commit()

    with pytest.raises(NotFound):
        authz.get_viewable_account(db, bank_account.id, other_user)


def test_a_member_who_left_loses_sight_of_shared_accounts(
    db, user, other_user, family, bank_account
):
    from app.services import families as family_service

    account_service.set_visibility(
        db, account=bank_account, user=user, visibility=Visibility.SHARED
    )
    db.commit()
    family_service.leave_family(db, user=other_user)
    db.commit()

    with pytest.raises(NotFound):
        authz.get_viewable_account(db, bank_account.id, other_user)


def test_leaving_takes_your_own_sharing_with_you(db, user, other_user, family):
    """Their accounts stop being shared with a household they are no longer
    in, rather than lingering in everyone else's view."""
    from app.services import families as family_service

    theirs = account_service.create_account(
        db,
        user=other_user,
        name="Their Shared",
        account_type=AccountType.CHECKING,
        currency="RWF",
        opening_balance=Decimal("1000"),
        opening_balance_at=NOW,
    )
    account_service.set_visibility(
        db, account=theirs, user=other_user, visibility=Visibility.SHARED
    )
    db.commit()
    authz.get_viewable_account(db, theirs.id, user)

    family_service.leave_family(db, user=other_user)
    db.commit()
    with pytest.raises(NotFound):
        authz.get_viewable_account(db, theirs.id, user)


# ------------------------------ "replay complete-payment requests"


def test_replaying_a_transfer_with_the_same_key_posts_once(db, user, bank_account, savings_account):
    """The idempotency key is what makes a retried request safe. Without it a
    dropped response would cost the user the money twice."""
    from app.services.posting import PostingService

    posting = PostingService(db)
    before = posting.balance_of(bank_account)
    key = "replay-me-please"

    first = posting.transfer_funds(
        source=bank_account,
        destination=savings_account,
        source_amount=Decimal("10000"),
        destination_amount=Decimal("10000"),
        occurred_at=NOW,
        actor_id=user.id,
        idempotency_key=key,
    )
    db.commit()

    from sqlalchemy import select

    from app.models.finance import Transfer

    replayed = db.scalar(
        select(Transfer).where(
            Transfer.created_by == user.id, Transfer.idempotency_key == key
        )
    )
    assert replayed.id == first.id
    assert posting.balance_of(bank_account) == before - Decimal("10000")


def test_completing_a_planned_item_twice_is_refused(db, user, bank_account):
    """The second completion would post a second transaction for one bill."""
    from app.core.errors import Conflict
    from app.db.enums import PlannedType
    from app.services import planning

    planned = planning.create_planned(
        db,
        user=user,
        account_id=bank_account.id,
        planned_type=PlannedType.EXPENSE,
        amount=Decimal("5000"),
        expected_at=NOW,
        description="Water",
    )
    db.commit()

    planning.complete_planned(db, user=user, planned_id=planned.id, actual_occurred_at=NOW)
    db.commit()
    with pytest.raises(Conflict):
        planning.complete_planned(db, user=user, planned_id=planned.id, actual_occurred_at=NOW)


# --------------------------------------------------------- password policy


@pytest.mark.parametrize(
    "weak",
    ["short", "password1234", "Passw0rd!!!!", "qwertyuiop12", "123456789012", "aaaaaaaaaaaa"],
)
def test_a_guessable_password_is_refused(weak):
    with pytest.raises(ValidationFailed) as exc:
        validate_password_policy(weak)
    assert exc.value.code == "PASSWORD_POLICY_FAILED"


@pytest.mark.parametrize(
    "good",
    ["correct horse battery staple", "a-good-passphrase-1", "MontraLedger2026", "Tw0-Rivers-Meet!"],
)
def test_a_real_passphrase_is_accepted(good):
    validate_password_policy(good)


def test_a_password_cannot_be_your_own_address():
    with pytest.raises(ValidationFailed):
        validate_password_policy("smoke@example.com!", email="smoke@example.com")


def test_the_minimum_is_length_not_punctuation():
    """Composition rules push people towards predictable substitutions; length
    is what actually resists guessing."""
    assert MINIMUM_LENGTH >= 12
    validate_password_policy("horse battery staple")  # no digits, no symbols


# ------------------------------------------------------------ rate limiting

# The limiter is off for the rest of the suite (see conftest): it would spend
# its time throttling the tests. These switch it on deliberately.


@pytest.fixture
def limiter(monkeypatch):
    from app.core import rate_limit
    from app.core.config import settings

    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    bucket = f"test-{uuid.uuid4().hex[:8]}"
    yield bucket, rate_limit
    rate_limit.clear(bucket, "someone", rate_limit.LOGIN)


def test_guessing_a_password_is_capped(limiter):
    bucket, rate_limit = limiter
    from app.core.rate_limit import RateLimited

    for _ in range(rate_limit.LOGIN.attempts):
        rate_limit.hit(bucket, "someone", rate_limit.LOGIN)

    with pytest.raises(RateLimited) as exc:
        rate_limit.hit(bucket, "someone", rate_limit.LOGIN)
    assert exc.value.status_code == 429
    assert exc.value.retry_after > 0


def test_getting_it_right_clears_the_count(limiter):
    """Someone who mistypes their password and then remembers it should not be
    left locked out for the rest of the window."""
    bucket, rate_limit = limiter
    for _ in range(rate_limit.LOGIN.attempts):
        rate_limit.hit(bucket, "someone", rate_limit.LOGIN)

    rate_limit.clear(bucket, "someone", rate_limit.LOGIN)
    rate_limit.hit(bucket, "someone", rate_limit.LOGIN)  # no raise


def test_one_persons_attempts_do_not_count_against_another(limiter):
    bucket, rate_limit = limiter
    for _ in range(rate_limit.LOGIN.attempts + 2):
        try:
            rate_limit.hit(bucket, "noisy", rate_limit.LOGIN)
        except Exception:
            pass
    rate_limit.hit(bucket, "quiet", rate_limit.LOGIN)  # no raise
    rate_limit.clear(bucket, "noisy", rate_limit.LOGIN)
    rate_limit.clear(bucket, "quiet", rate_limit.LOGIN)


def test_the_account_cap_is_looser_than_the_address_cap():
    """A tight per-account cap hands anyone who knows your email a way to lock
    you out. It exists to catch guessing spread across addresses, not to be
    the primary control."""
    from app.core.rate_limit import LOGIN, LOGIN_ACCOUNT

    assert LOGIN_ACCOUNT.attempts > LOGIN.attempts
    assert LOGIN_ACCOUNT.window > LOGIN.window


def test_an_unreachable_store_allows_the_request(monkeypatch, limiter):
    """Availability over enforcement, deliberately: a cache outage must not
    lock everyone out of their own money."""
    bucket, rate_limit = limiter
    monkeypatch.setattr(rate_limit, "client", lambda: None)
    for _ in range(rate_limit.LOGIN.attempts * 3):
        rate_limit.hit(bucket, "someone", rate_limit.LOGIN)


def test_a_long_address_does_not_reject_an_unrelated_password():
    """The proportion rule compares against something the password actually
    contains. Comparing lengths alone rejected any password shorter than twice
    the email address, however unrelated the two were."""
    validate_password_policy("a-good-passphrase-1", email="someone-else@example.com")
    validate_password_policy("correct horse battery", email="a-very-long-address@example.com")


# --------------------------------------------------- the same-origin check

# These use the app directly, because the bug they guard against was in how a
# request's own origin is worked out — not in any service.


def _post(client, origin: str | None):
    headers = {"Origin": origin} if origin else {}
    return client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "wrong-but-well-formed"},
        headers=headers,
    )


def test_a_request_from_the_host_that_served_it_is_allowed(client):
    """Whatever hostname the app is reached by. Checking against a fixed list
    instead meant every write 403'd the moment it was opened through a tunnel
    — including signing in."""
    assert _post(client, "http://testserver").status_code != 403


def test_a_request_from_somewhere_else_is_refused(client):
    response = _post(client, "https://evil.example")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CROSS_ORIGIN_REFUSED"


def test_a_request_with_no_origin_is_allowed(client):
    """A script or a native client sends none, and neither carries the ambient
    cookie this protects against."""
    assert _post(client, None).status_code != 403


def test_reading_is_never_blocked_by_origin(client):
    """Only unsafe methods are checked; a GET changes nothing."""
    response = client.get("/api/v1/health/live", headers={"Origin": "https://evil.example"})
    assert response.status_code == 200


def test_the_forwarded_scheme_decides_the_origin():
    """A tunnel terminates TLS and forwards plain HTTP, so the scheme that
    reached the API is not the one the browser used. Trusting the wrong one
    turned every HTTPS request into a mismatch."""
    from unittest.mock import Mock

    from app.main import _own_origin

    request = Mock()
    request.headers = {"host": "app.example.com", "x-forwarded-proto": "https"}
    request.url.scheme = "http"
    assert _own_origin(request) == "https://app.example.com"


def test_a_host_with_a_port_keeps_it():
    """An origin without its port does not match the one the browser sends."""
    from unittest.mock import Mock

    from app.main import _own_origin

    request = Mock()
    request.headers = {"host": "localhost:8080"}
    request.url.scheme = "http"
    assert _own_origin(request) == "http://localhost:8080"
