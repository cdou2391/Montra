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
def credit_card(db: Session, user: User) -> Account:
    """Opening balance on a liability is debt owed."""
    return _make_account(db, user, AccountType.CREDIT_CARD, "200000.0000", "BK Visa")
