"""Test fixtures.

Each test runs against a freshly created schema in the dedicated test database,
so the financial invariant suite never observes state from another test.
"""

import os
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

os.environ.setdefault("MONTRA_ENV", "test")
# The suite registers and signs in as dozens of users from one address. Left
# on, the limiter would be throttling the tests rather than the tests
# exercising anything — so it is off by default here and switched back on
# explicitly by the tests that are about it.
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")

from app.api.deps import db_session  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.enums import AccountType  # noqa: E402
from app.main import app  # noqa: E402
from app.models import *  # noqa: E402,F401,F403
from app.models.finance import Account  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.accounts import create_account  # noqa: E402
from app.services.auth import register_user  # noqa: E402

TEST_URL = os.environ.get("TEST_DATABASE_URL", settings.test_database_url)

engine = create_engine(TEST_URL, future=True)
TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


@pytest.fixture(scope="session", autouse=True)
def _schema():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def db() -> Session:
    session = TestSession()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        # Truncate between tests so ordering never matters.
        with engine.begin() as conn:
            tables = ",".join(f'"{t.name}"' for t in reversed(Base.metadata.sorted_tables))
            conn.exec_driver_sql(f"TRUNCATE {tables} RESTART IDENTITY CASCADE")


@pytest.fixture
def client(db: Session) -> TestClient:
    def _override():
        yield db

    app.dependency_overrides[db_session] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def user(db: Session) -> User:
    u = register_user(
        db,
        email="owner@example.com",
        password="correct horse battery",
        display_name="Owner",
        base_currency="RWF",
        timezone="Africa/Kigali",
    )
    db.commit()
    return u


@pytest.fixture
def other_user(db: Session) -> User:
    u = register_user(
        db,
        email="other@example.com",
        password="another good passphrase",
        display_name="Other",
        base_currency="RWF",
        timezone="Africa/Kigali",
    )
    db.commit()
    return u


def _make_account(db: Session, user: User, account_type: AccountType, opening: str, name: str):
    account = create_account(
        db,
        user=user,
        name=name,
        account_type=account_type,
        currency="RWF",
        opening_balance=Decimal(opening),
        opening_balance_at=datetime(2026, 8, 1, 9, 0, tzinfo=UTC),
    )
    db.commit()
    return account


@pytest.fixture
def bank_account(db: Session, user: User) -> Account:
    return _make_account(db, user, AccountType.CHECKING, "1000000.0000", "BK Current")


@pytest.fixture
def savings_account(db: Session, user: User) -> Account:
    return _make_account(db, user, AccountType.SAVINGS, "500000.0000", "BK Savings")


@pytest.fixture
def prepaid_card(db: Session, user: User) -> Account:
    return _make_account(db, user, AccountType.PREPAID_CARD, "850000.0000", "Prepaid Visa")


@pytest.fixture
def credit_card(db: Session, user: User) -> Account:
    """Opening balance on a liability is debt owed."""
    return _make_account(db, user, AccountType.CREDIT_CARD, "200000.0000", "BK Visa")


# --------------------------------------------------------------------- family


@pytest.fixture
def third_user(db: Session) -> User:
    """Someone outside the household, for the "no business seeing this" cases."""
    u = register_user(
        db,
        email="outsider@example.com",
        password="a third good passphrase",
        display_name="Outsider",
        base_currency="RWF",
        timezone="Africa/Kigali",
    )
    db.commit()
    return u


@pytest.fixture
def family(db: Session, user: User, other_user: User):
    """A household: `user` owns it, `other_user` joined as ADULT."""
    from app.services import families as family_service

    fam = family_service.create_family(db, user=user, name="Our Household", base_currency="RWF")
    db.commit()
    _, token = family_service.invite(
        db, user=user, family_id=fam.id, invitee_email=other_user.email
    )
    db.commit()
    family_service.accept_invitation(db, user=other_user, token=token)
    db.commit()
    return fam


def make_account(db: Session, owner: User, name: str, visibility, **kw):
    from app.db.enums import AccountType
    from app.services.accounts import create_account

    account = create_account(
        db,
        user=owner,
        name=name,
        account_type=kw.pop("account_type", AccountType.CHECKING),
        currency="RWF",
        opening_balance=Decimal(kw.pop("opening", "100000")),
        opening_balance_at=datetime(2026, 8, 1, 9, 0, tzinfo=UTC),
        visibility=visibility,
        **kw,
    )
    db.commit()
    return account
