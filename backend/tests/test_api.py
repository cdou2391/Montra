"""API-level tests: auth isolation, account lifecycle, transaction and transfer flows.

Lighter than the ledger suite by design; the invariants live in test_posting.py
and test_transfers.py.
"""


def _register(client, email="a@example.com", password="a-good-passphrase-1"):
    return client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "display_name": "Test",
            "base_currency": "RWF",
            "timezone": "Africa/Kigali",
        },
    )


# ------------------------------------------------------------------------- auth


def test_register_creates_session_and_defaults(client):
    r = _register(client)
    assert r.status_code == 201, r.text
    assert r.json()["data"]["email"] == "a@example.com"

    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["data"]["active_family"] is None

    # Phase 3: default categories provisioned on registration.
    cats = client.get("/api/v1/categories").json()["data"]
    assert len(cats) == 29
    assert {c["category_type"] for c in cats} == {"INCOME", "EXPENSE"}


def test_weak_password_is_rejected(client):
    r = _register(client, password="short")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "PASSWORD_POLICY_FAILED"


def test_duplicate_email_is_rejected(client):
    _register(client)
    r = _register(client)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "EMAIL_ALREADY_EXISTS"


def test_login_failure_does_not_reveal_whether_email_exists(client):
    _register(client)
    known = client.post(
        "/api/v1/auth/login", json={"email": "a@example.com", "password": "wrong-password"}
    )
    unknown = client.post(
        "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "wrong-password"}
    )
    assert known.status_code == unknown.status_code == 401

    # request_id is unique per request by design; everything a caller could use
    # to distinguish the two cases must be identical.
    def _comparable(response):
        return {k: v for k, v in response.json()["error"].items() if k != "request_id"}

    assert _comparable(known) == _comparable(unknown)
    assert _comparable(known)["code"] == "INVALID_CREDENTIALS"


def test_unauthenticated_request_is_rejected(client):
    assert client.get("/api/v1/accounts").status_code == 401


def test_logout_revokes_the_session(client):
    _register(client)
    assert client.post("/api/v1/auth/logout").status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401


# --------------------------------------------------------------------- accounts


def _create_account(client, **overrides):
    payload = {
        "name": "BK Current",
        "account_type": "CHECKING",
        "currency": "RWF",
        "opening_balance": "1000000.00",
        "opening_balance_date": "2026-08-01",
    } | overrides
    return client.post("/api/v1/accounts", json=payload)


def test_account_lifecycle(client):
    _register(client)
    created = _create_account(client)
    assert created.status_code == 201, created.text
    data = created.json()["data"]
    assert data["account_nature"] == "ASSET"
    assert data["balance"] == "1000000.00"

    account_id = data["id"]
    assert (
        client.patch(f"/api/v1/accounts/{account_id}", json={"name": "Primary Current"}).json()[
            "data"
        ]["name"]
        == "Primary Current"
    )

    assert client.post(f"/api/v1/accounts/{account_id}/archive").status_code == 204
    assert client.get("/api/v1/accounts").json()["data"] == []
    assert client.post(f"/api/v1/accounts/{account_id}/restore").status_code == 200
    assert len(client.get("/api/v1/accounts").json()["data"]) == 1


def test_credit_card_reports_liability_nature(client):
    _register(client)
    r = _create_account(
        client, name="BK Visa", account_type="CREDIT_CARD", opening_balance="200000.00"
    )
    assert r.json()["data"]["account_nature"] == "LIABILITY"


def test_family_visibility_is_refused_until_family_ships(client):
    _register(client)
    r = _create_account(client, visibility="FAMILY_VISIBLE")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "NO_ACTIVE_FAMILY"


def test_masked_identifier_only_exposes_last_four(client):
    _register(client)
    r = _create_account(client, account_identifier="1234567325")
    assert r.json()["data"]["masked_identifier"] == "**** 7325"


# ---------------------------------------------------------------- user isolation


def test_one_user_cannot_see_another_users_account(client):
    _register(client, email="first@example.com")
    account_id = _create_account(client).json()["data"]["id"]
    client.post("/api/v1/auth/logout")

    _register(client, email="second@example.com")
    assert client.get("/api/v1/accounts").json()["data"] == []
    # 404 rather than 403: the API must not confirm the account exists.
    assert client.get(f"/api/v1/accounts/{account_id}").status_code == 404
    assert (
        client.patch(f"/api/v1/accounts/{account_id}", json={"name": "Hijacked"}).status_code == 404
    )


def test_one_user_cannot_post_transactions_to_another_users_account(client):
    _register(client, email="first@example.com")
    account_id = _create_account(client).json()["data"]["id"]
    client.post("/api/v1/auth/logout")

    _register(client, email="second@example.com")
    r = client.post(
        "/api/v1/transactions",
        json={
            "transaction_type": "EXPENSE",
            "account_id": account_id,
            "amount": "1000.00",
            "transaction_date": "2026-08-24",
        },
    )
    assert r.status_code == 404


# ------------------------------------------------------------------ transactions


def test_expense_and_income_move_the_balance(client):
    _register(client)
    account_id = _create_account(client).json()["data"]["id"]
    category_id = next(
        c["id"] for c in client.get("/api/v1/categories?type=EXPENSE").json()["data"]
    )

    expense = client.post(
        "/api/v1/transactions",
        json={
            "transaction_type": "EXPENSE",
            "account_id": account_id,
            "amount": "48500.00",
            "transaction_date": "2026-08-24",
            "category_id": category_id,
            "description": "Simba Supermarket",
        },
    )
    assert expense.status_code == 201, expense.text
    assert expense.json()["data"]["direction"] == "DECREASE"

    client.post(
        "/api/v1/transactions",
        json={
            "transaction_type": "INCOME",
            "account_id": account_id,
            "amount": "2500000.00",
            "transaction_date": "2026-08-25",
            "description": "Salary",
        },
    )
    balance = client.get(f"/api/v1/accounts/{account_id}/balance").json()["data"]
    assert balance["amount"] == "3451500.00"


def test_amounts_serialize_as_strings(client):
    """No JSON float may ever carry a financial value (API spec section 12)."""
    _register(client)
    account_id = _create_account(client).json()["data"]["id"]
    r = client.post(
        "/api/v1/transactions",
        json={
            "transaction_type": "EXPENSE",
            "account_id": account_id,
            "amount": "0.10",
            "transaction_date": "2026-08-24",
        },
    )
    assert isinstance(r.json()["data"]["amount"], str)


def test_transaction_delete_is_soft_and_restores_balance(client):
    _register(client)
    account_id = _create_account(client).json()["data"]["id"]
    txn_id = client.post(
        "/api/v1/transactions",
        json={
            "transaction_type": "EXPENSE",
            "account_id": account_id,
            "amount": "50000.00",
            "transaction_date": "2026-08-24",
        },
    ).json()["data"]["id"]

    assert client.delete(f"/api/v1/transactions/{txn_id}").status_code == 204
    assert client.get(f"/api/v1/accounts/{account_id}/balance").json()["data"]["amount"] == (
        "1000000.00"
    )
    assert client.get(f"/api/v1/transactions/{txn_id}").status_code == 404


def test_transactions_paginate_by_cursor(client):
    _register(client)
    account_id = _create_account(client).json()["data"]["id"]
    for day in range(1, 8):
        client.post(
            "/api/v1/transactions",
            json={
                "transaction_type": "EXPENSE",
                "account_id": account_id,
                "amount": "1000.00",
                "transaction_date": f"2026-08-{day:02d}",
            },
        )
    first = client.get("/api/v1/transactions?limit=3").json()
    assert len(first["data"]) == 3
    cursor = first["pagination"]["next_cursor"]
    assert cursor

    second = client.get(f"/api/v1/transactions?limit=3&cursor={cursor}").json()
    assert len(second["data"]) == 3
    assert {t["id"] for t in first["data"]} & {t["id"] for t in second["data"]} == set()


# --------------------------------------------------------------------- transfers


def test_transfer_endpoint_moves_money_and_is_idempotent(client):
    _register(client)
    source = _create_account(client).json()["data"]["id"]
    dest = _create_account(
        client, name="BK Savings", account_type="SAVINGS", opening_balance="500000.00"
    ).json()["data"]["id"]

    body = {
        "source_account_id": source,
        "destination_account_id": dest,
        "source_amount": "100000.00",
        "destination_amount": "100000.00",
        "transfer_date": "2026-08-24",
        "notes": "Move to savings",
    }
    first = client.post("/api/v1/transfers", json=body, headers={"Idempotency-Key": "key-1"})
    assert first.status_code == 201, first.text

    replay = client.post("/api/v1/transfers", json=body, headers={"Idempotency-Key": "key-1"})
    assert replay.json()["data"]["id"] == first.json()["data"]["id"]

    # The replay must not have posted a second time.
    assert client.get(f"/api/v1/accounts/{source}/balance").json()["data"]["amount"] == "900000.00"
    assert client.get(f"/api/v1/accounts/{dest}/balance").json()["data"]["amount"] == "600000.00"


def test_transfer_side_cannot_be_deleted_independently(client):
    _register(client)
    source = _create_account(client).json()["data"]["id"]
    dest = _create_account(
        client, name="BK Savings", account_type="SAVINGS", opening_balance="500000.00"
    ).json()["data"]["id"]
    client.post(
        "/api/v1/transfers",
        json={
            "source_account_id": source,
            "destination_account_id": dest,
            "source_amount": "100000.00",
            "transfer_date": "2026-08-24",
        },
    )
    side = client.get(f"/api/v1/transactions?account_id={source}").json()["data"][0]
    r = client.delete(f"/api/v1/transactions/{side['id']}")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "TRANSFER_SIDE_NOT_DELETABLE"


def test_transfer_cancel_restores_both_balances(client):
    _register(client)
    source = _create_account(client).json()["data"]["id"]
    dest = _create_account(
        client, name="BK Savings", account_type="SAVINGS", opening_balance="500000.00"
    ).json()["data"]["id"]
    transfer_id = client.post(
        "/api/v1/transfers",
        json={
            "source_account_id": source,
            "destination_account_id": dest,
            "source_amount": "100000.00",
            "transfer_date": "2026-08-24",
        },
    ).json()["data"]["id"]

    assert client.post(f"/api/v1/transfers/{transfer_id}/cancel").status_code == 200
    assert client.get(f"/api/v1/accounts/{source}/balance").json()["data"]["amount"] == "1000000.00"
    assert client.get(f"/api/v1/accounts/{dest}/balance").json()["data"]["amount"] == "500000.00"


# --------------------------------------------------------------- reconciliation


def test_balance_adjustment_reconciles_to_actual(client):
    _register(client)
    account_id = _create_account(client).json()["data"]["id"]
    r = client.post(
        f"/api/v1/accounts/{account_id}/balance-adjustments",
        json={
            "actual_balance": "980000.00",
            "adjustment_date": "2026-08-24",
            "reason": "Matched bank statement",
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["data"]["direction"] == "DECREASE"
    assert client.get(f"/api/v1/accounts/{account_id}/balance").json()["data"]["amount"] == (
        "980000.00"
    )


# ------------------------------------------------------------------------ health


def test_liveness_needs_no_dependencies(client):
    assert client.get("/api/v1/health/live").json() == {"status": "ok"}


def test_error_envelope_carries_a_request_id(client):
    r = client.get("/api/v1/accounts")
    body = r.json()
    assert set(body["error"]) == {"code", "message", "details", "request_id"}
    assert body["error"]["request_id"]
    assert r.headers["X-Request-ID"]
