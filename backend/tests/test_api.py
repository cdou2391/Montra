"""API-level tests: auth isolation, account lifecycle, transaction and transfer flows.

Lighter than the ledger suite by design; the invariants live in test_posting.py
and test_transfers.py.
"""

from app.core.version import APP_VERSION


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
        "opening_balance_at": "2026-08-01T09:00:00Z",
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
            "occurred_at": "2026-08-24T14:30:00Z",
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
            "occurred_at": "2026-08-24T14:30:00Z",
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
            "occurred_at": "2026-08-25T09:15:00Z",
            "description": "Salary",
        },
    )
    balance = client.get(f"/api/v1/accounts/{account_id}/balance").json()["data"]
    assert balance["amount"] == "3451500.00"


def test_amounts_serialize_as_strings(client):
    """No JSON float may ever carry a financial value."""
    _register(client)
    account_id = _create_account(client).json()["data"]["id"]
    r = client.post(
        "/api/v1/transactions",
        json={
            "transaction_type": "EXPENSE",
            "account_id": account_id,
            "amount": "0.10",
            "occurred_at": "2026-08-24T14:30:00Z",
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
            "occurred_at": "2026-08-24T14:30:00Z",
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
                "occurred_at": f"2026-08-{day:02d}T10:00:00Z",
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
        "occurred_at": "2026-08-24T14:30:00Z",
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
            "occurred_at": "2026-08-24T14:30:00Z",
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
            "occurred_at": "2026-08-24T14:30:00Z",
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
            "occurred_at": "2026-08-24T14:30:00Z",
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


# --------------------------------------------------------------- credit cards


def _make_card(client, **overrides):
    payload = {
        "name": "BK Visa",
        "account_type": "CREDIT_CARD",
        "currency": "RWF",
        "opening_balance": "200000.00",
        "opening_balance_at": "2026-08-01T09:00:00Z",
        "credit_limit": "3000000.00",
        "payment_due_day": 5,
        "minimum_payment": "20000.00",
        "statement_balance": "180000.00",
    } | overrides
    return client.post("/api/v1/accounts", json=payload)


def test_card_fields_round_trip(client):
    _register(client)
    r = _make_card(client)
    assert r.status_code == 201, r.text
    card = r.json()["data"]["credit_card"]
    assert card["credit_limit"] == "3000000.00"
    assert card["payment_due_day"] == 5


def test_non_card_accounts_carry_no_card_block(client):
    _register(client)
    assert _create_account(client).json()["data"]["credit_card"] is None


def test_card_fields_rejected_on_a_bank_account(client):
    _register(client)
    r = _create_account(client, credit_limit="100000.00")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "NOT_A_CREDIT_CARD"


def test_credit_card_summary_endpoint(client):
    _register(client)
    card_id = _make_card(client).json()["data"]["id"]
    s = client.get(f"/api/v1/credit-cards/{card_id}/summary").json()["data"]
    assert s["outstanding_balance"] == "200000.00"
    assert s["available_credit"] == "2800000.00"
    assert s["utilization_percentage"] == "6.67"
    assert s["utilization_band"] == "NORMAL"
    assert s["payment_due_date"].endswith("-05")


def test_summary_rejects_a_non_card(client):
    _register(client)
    account_id = _create_account(client).json()["data"]["id"]
    r = client.get(f"/api/v1/credit-cards/{account_id}/summary")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "NOT_A_CREDIT_CARD"


def test_card_payment_endpoint_moves_both_balances(client):
    _register(client)
    bank_id = _create_account(client).json()["data"]["id"]
    card_id = _make_card(client).json()["data"]["id"]

    r = client.post(
        f"/api/v1/credit-cards/{card_id}/payments",
        json={
            "source_account_id": bank_id,
            "amount": "150000.00",
            "occurred_at": "2026-08-24T14:30:00Z",
        },
        headers={"Idempotency-Key": "pay-1"},
    )
    assert r.status_code == 201, r.text
    assert client.get(f"/api/v1/accounts/{bank_id}/balance").json()["data"]["amount"] == (
        "850000.00"
    )
    assert client.get(f"/api/v1/accounts/{card_id}/balance").json()["data"]["amount"] == (
        "50000.00"
    )


def test_card_payment_is_idempotent(client):
    _register(client)
    bank_id = _create_account(client).json()["data"]["id"]
    card_id = _make_card(client).json()["data"]["id"]
    body = {
        "source_account_id": bank_id,
        "amount": "150000.00",
        "occurred_at": "2026-08-24T14:30:00Z",
    }
    first = client.post(
        f"/api/v1/credit-cards/{card_id}/payments", json=body, headers={"Idempotency-Key": "k"}
    )
    replay = client.post(
        f"/api/v1/credit-cards/{card_id}/payments", json=body, headers={"Idempotency-Key": "k"}
    )
    assert replay.json()["data"]["id"] == first.json()["data"]["id"]
    assert client.get(f"/api/v1/accounts/{card_id}/balance").json()["data"]["amount"] == (
        "50000.00"
    )


def test_card_payment_does_not_appear_as_an_expense(client):
    _register(client)
    bank_id = _create_account(client).json()["data"]["id"]
    card_id = _make_card(client).json()["data"]["id"]
    client.post(
        f"/api/v1/credit-cards/{card_id}/payments",
        json={
            "source_account_id": bank_id,
            "amount": "150000.00",
            "occurred_at": "2026-08-24T14:30:00Z",
        },
    )
    expenses = client.get("/api/v1/transactions?type=EXPENSE").json()["data"]
    assert expenses == []
    transfers = client.get("/api/v1/transactions?type=TRANSFER").json()["data"]
    assert len(transfers) == 2
    assert {t["direction"] for t in transfers} == {"DECREASE"}


def test_prepaid_top_up_endpoint(client):
    _register(client)
    bank_id = _create_account(client).json()["data"]["id"]
    prepaid_id = _create_account(
        client, name="Prepaid Visa", account_type="PREPAID_CARD", opening_balance="850000.00"
    ).json()["data"]["id"]

    r = client.post(
        f"/api/v1/prepaid-cards/{prepaid_id}/top-ups",
        json={
            "source_account_id": bank_id,
            "amount": "100000.00",
            "occurred_at": "2026-08-24T14:30:00Z",
        },
    )
    assert r.status_code == 201, r.text
    assert client.get(f"/api/v1/accounts/{prepaid_id}/balance").json()["data"]["amount"] == (
        "950000.00"
    )
    assert client.get("/api/v1/transactions?type=EXPENSE").json()["data"] == []


# ------------------------------------------------------------- reconciliation


def test_reconciliation_records_the_difference_not_a_rewrite(client):
    """Phase 8: history and opening balance must survive an adjustment."""
    _register(client)
    account_id = _create_account(client).json()["data"]["id"]
    client.post(
        "/api/v1/transactions",
        json={
            "transaction_type": "EXPENSE",
            "account_id": account_id,
            "amount": "50000.00",
            "occurred_at": "2026-08-24T14:30:00Z",
            "description": "Groceries",
        },
    )

    r = client.post(
        f"/api/v1/accounts/{account_id}/balance-adjustments",
        json={
            "actual_balance": "930000.00",
            "occurred_at": "2026-08-25T09:00:00Z",
            "reason": "Matched bank statement",
        },
    )
    assert r.status_code == 201, r.text
    adjustment = r.json()["data"]
    assert adjustment["transaction_type"] == "ADJUSTMENT"
    assert adjustment["amount"] == "20000.00"
    assert adjustment["direction"] == "DECREASE"

    detail = client.get(f"/api/v1/accounts/{account_id}").json()["data"]
    assert detail["balance"] == "930000.00"
    # Opening balance untouched, and the original expense still on the record.
    assert detail["opening_balance"] == "1000000.00"
    descriptions = [t["description"] for t in client.get("/api/v1/transactions").json()["data"]]
    assert "Groceries" in descriptions
    assert "Matched bank statement" in descriptions


def test_reconciliation_upwards_records_an_increase(client):
    _register(client)
    account_id = _create_account(client).json()["data"]["id"]
    r = client.post(
        f"/api/v1/accounts/{account_id}/balance-adjustments",
        json={"actual_balance": "1200000.00", "occurred_at": "2026-08-25T09:00:00Z"},
    )
    assert r.json()["data"]["direction"] == "INCREASE"
    assert r.json()["data"]["amount"] == "200000.00"


def test_reconciliation_is_a_noop_when_already_matching(client):
    _register(client)
    account_id = _create_account(client).json()["data"]["id"]
    r = client.post(
        f"/api/v1/accounts/{account_id}/balance-adjustments",
        json={"actual_balance": "1000000.00", "occurred_at": "2026-08-25T09:00:00Z"},
    )
    # Nothing was created, so this is a 200 rather than a 201.
    assert r.status_code == 200
    assert r.json()["data"]["adjustment"] is None
    assert client.get("/api/v1/transactions").json()["data"] == []


def test_reconciliation_preview_does_not_write(client):
    _register(client)
    account_id = _create_account(client).json()["data"]["id"]
    p = client.get(
        f"/api/v1/accounts/{account_id}/reconciliation-preview?actual_balance=930000.00"
    ).json()["data"]
    assert p["current_balance"] == "1000000.00"
    assert p["difference"] == "70000.00"
    assert p["direction"] == "DECREASE"
    # Preview only: no ledger entry, no balance change.
    assert client.get("/api/v1/transactions").json()["data"] == []
    assert client.get(f"/api/v1/accounts/{account_id}/balance").json()["data"]["amount"] == (
        "1000000.00"
    )


# ---------------------------------------------------------------------- loans


def _make_loan(client, **overrides):
    payload = {
        "name": "Car Loan",
        "direction": "PAYABLE",
        "currency": "RWF",
        "original_principal": "18000000.00",
        "opening_outstanding_principal": "11850000.00",
        "start_date": "2025-01-01",
        "counterparty": "Bank of Kigali",
        "interest_rate": "7.5",
        "expected_payment_amount": "750000.00",
        "payment_frequency": "MONTHLY",
        "next_payment_date": "2026-08-28",
    } | overrides
    return client.post("/api/v1/loans", json=payload)


def test_loan_lifecycle(client):
    _register(client)
    created = _make_loan(client)
    assert created.status_code == 201, created.text
    loan = created.json()["data"]
    assert loan["outstanding_principal"] == "11850000.00"
    assert loan["percent_paid"] == "34.17"
    assert loan["interest_rate"] == "7.5"

    loan_id = loan["id"]
    assert client.get(f"/api/v1/loans/{loan_id}").status_code == 200
    assert len(client.get("/api/v1/loans").json()["data"]) == 1
    assert client.post(f"/api/v1/loans/{loan_id}/archive").json()["data"]["status"] == "ARCHIVED"
    assert client.get("/api/v1/loans").json()["data"] == []


def test_loan_payment_splits_correctly_over_the_api(client):
    _register(client)
    account_id = _create_account(client).json()["data"]["id"]
    loan_id = _make_loan(
        client, original_principal="1000000.00", opening_outstanding_principal="1000000.00"
    ).json()["data"]["id"]

    r = client.post(
        f"/api/v1/loans/{loan_id}/payments",
        json={
            "account_id": account_id,
            "payment_date": "2026-08-28",
            "total_amount": "150000.00",
            "principal_amount": "120000.00",
            "interest_amount": "25000.00",
            "fee_amount": "5000.00",
        },
        headers={"Idempotency-Key": "loan-pay-1"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["data"]["loan"]["outstanding_principal"] == "880000.00"

    # Cash fell by the whole payment.
    assert client.get(f"/api/v1/accounts/{account_id}/balance").json()["data"]["amount"] == (
        "850000.00"
    )
    # Only interest and fees are spending.
    expenses = client.get("/api/v1/transactions?type=EXPENSE").json()["data"]
    assert sorted(t["amount"] for t in expenses) == ["25000.00", "5000.00"]
    transfers = client.get("/api/v1/transactions?type=TRANSFER").json()["data"]
    assert [t["amount"] for t in transfers] == ["120000.00"]


def test_loan_payment_is_idempotent(client):
    _register(client)
    account_id = _create_account(client).json()["data"]["id"]
    loan_id = _make_loan(
        client, original_principal="1000000.00", opening_outstanding_principal="1000000.00"
    ).json()["data"]["id"]
    body = {
        "account_id": account_id,
        "payment_date": "2026-08-28",
        "total_amount": "100000.00",
        "principal_amount": "100000.00",
    }
    first = client.post(
        f"/api/v1/loans/{loan_id}/payments", json=body, headers={"Idempotency-Key": "k"}
    )
    replay = client.post(
        f"/api/v1/loans/{loan_id}/payments", json=body, headers={"Idempotency-Key": "k"}
    )
    assert replay.json()["data"]["id"] == first.json()["data"]["id"]
    assert (
        client.get(f"/api/v1/loans/{loan_id}").json()["data"]["outstanding_principal"]
        == "900000.00"
    )


def test_loan_payment_rejects_a_bad_allocation(client):
    _register(client)
    account_id = _create_account(client).json()["data"]["id"]
    loan_id = _make_loan(client).json()["data"]["id"]
    r = client.post(
        f"/api/v1/loans/{loan_id}/payments",
        json={
            "account_id": account_id,
            "payment_date": "2026-08-28",
            "total_amount": "100000.00",
            "principal_amount": "50000.00",
            "interest_amount": "10000.00",
        },
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "ALLOCATION_MISMATCH"


def test_loan_payment_history(client):
    _register(client)
    account_id = _create_account(client).json()["data"]["id"]
    loan_id = _make_loan(
        client, original_principal="1000000.00", opening_outstanding_principal="1000000.00"
    ).json()["data"]["id"]
    for day in ("2026-06-28", "2026-07-28", "2026-08-28"):
        client.post(
            f"/api/v1/loans/{loan_id}/payments",
            json={
                "account_id": account_id,
                "payment_date": day,
                "total_amount": "100000.00",
                "principal_amount": "90000.00",
                "interest_amount": "10000.00",
            },
        )
    history = client.get(f"/api/v1/loans/{loan_id}/payments").json()["data"]
    assert len(history) == 3
    # Newest first.
    assert history[0]["payment_date"] == "2026-08-28"


def test_receivable_loan_over_the_api(client):
    _register(client)
    account_id = _create_account(client).json()["data"]["id"]
    loan_id = _make_loan(
        client,
        name="Loan to Jean",
        direction="RECEIVABLE",
        original_principal="300000.00",
        opening_outstanding_principal="300000.00",
    ).json()["data"]["id"]

    client.post(
        f"/api/v1/loans/{loan_id}/payments",
        json={
            "account_id": account_id,
            "payment_date": "2026-08-28",
            "total_amount": "110000.00",
            "principal_amount": "100000.00",
            "interest_amount": "10000.00",
        },
    )
    assert client.get(f"/api/v1/accounts/{account_id}/balance").json()["data"]["amount"] == (
        "1110000.00"
    )
    income = client.get("/api/v1/transactions?type=INCOME").json()["data"]
    assert [t["amount"] for t in income] == ["10000.00"]
    assert client.get("/api/v1/transactions?type=EXPENSE").json()["data"] == []


def test_one_user_cannot_see_another_users_loan(client):
    _register(client, email="first@example.com")
    loan_id = _make_loan(client).json()["data"]["id"]
    client.post("/api/v1/auth/logout")

    _register(client, email="second@example.com")
    assert client.get("/api/v1/loans").json()["data"] == []
    assert client.get(f"/api/v1/loans/{loan_id}").status_code == 404


# -------------------------------------------------------------- profile reset


def test_reset_preview_reports_what_would_go(client):
    _register(client)
    account_id = _create_account(client).json()["data"]["id"]
    client.post(
        "/api/v1/transactions",
        json={
            "transaction_type": "EXPENSE",
            "account_id": account_id,
            "amount": "1000.00",
            "occurred_at": "2026-08-24T14:30:00Z",
        },
    )
    preview = client.get("/api/v1/profile/reset-preview").json()["data"]
    assert preview["accounts"] == 1
    assert preview["transactions"] == 1


def test_reset_wipes_data_but_keeps_the_session(client):
    _register(client)
    account_id = _create_account(client).json()["data"]["id"]
    client.post(
        "/api/v1/transactions",
        json={
            "transaction_type": "EXPENSE",
            "account_id": account_id,
            "amount": "1000.00",
            "occurred_at": "2026-08-24T14:30:00Z",
        },
    )

    r = client.post("/api/v1/profile/reset", json={"password": "a-good-passphrase-1"})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["deleted"]["accounts"] == 1

    # Still signed in, with a clean slate and default categories back.
    assert client.get("/api/v1/auth/me").status_code == 200
    assert client.get("/api/v1/accounts").json()["data"] == []
    assert client.get("/api/v1/transactions").json()["data"] == []
    assert len(client.get("/api/v1/categories").json()["data"]) == 29


def test_reset_refuses_a_wrong_password(client):
    _register(client)
    _create_account(client)
    r = client.post("/api/v1/profile/reset", json={"password": "wrong-password"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "INVALID_CREDENTIALS"
    # And the data is still there.
    assert len(client.get("/api/v1/accounts").json()["data"]) == 1


def test_reset_requires_authentication(client):
    r = client.post("/api/v1/profile/reset", json={"password": "anything"})
    assert r.status_code == 401


# ------------------------------------------------------------ favorite account


def test_favorite_leads_the_accounts_endpoint(client):
    _register(client)
    _create_account(client, name="Alpha")
    zebra = _create_account(client, name="Zebra").json()["data"]["id"]

    assert [a["name"] for a in client.get("/api/v1/accounts").json()["data"]] == [
        "Alpha",
        "Zebra",
    ]

    r = client.post(f"/api/v1/accounts/{zebra}/favorite")
    assert r.status_code == 200, r.text
    assert r.json()["data"]["is_favorite"] is True

    rows = client.get("/api/v1/accounts").json()["data"]
    assert [a["name"] for a in rows] == ["Zebra", "Alpha"]
    assert rows[0]["is_favorite"] is True
    assert rows[1]["is_favorite"] is False


def test_favorite_can_be_cleared_over_the_api(client):
    _register(client)
    _create_account(client, name="Alpha")
    zebra = _create_account(client, name="Zebra").json()["data"]["id"]
    client.post(f"/api/v1/accounts/{zebra}/favorite")

    assert (
        client.delete(f"/api/v1/accounts/{zebra}/favorite").json()["data"]["is_favorite"] is False
    )
    assert [a["name"] for a in client.get("/api/v1/accounts").json()["data"]] == [
        "Alpha",
        "Zebra",
    ]


def test_preferences_report_the_favorite(client):
    _register(client)
    account_id = _create_account(client).json()["data"]["id"]
    client.post(f"/api/v1/accounts/{account_id}/favorite")
    assert client.get("/api/v1/preferences").json()["data"]["favorite_account_id"] == account_id


def test_cannot_favorite_another_users_account_over_the_api(client):
    _register(client, email="first@example.com")
    account_id = _create_account(client).json()["data"]["id"]
    client.post("/api/v1/auth/logout")

    _register(client, email="second@example.com")
    assert client.post(f"/api/v1/accounts/{account_id}/favorite").status_code == 404


# -------------------------------------------------------------------- family


def test_household_invitation_flow(client):
    """Create a household, invite someone, they accept, both see it."""
    _register(client, email="owner@example.com")
    created = client.post(
        "/api/v1/families", json={"name": "Our Household", "base_currency": "RWF"}
    )
    assert created.status_code == 201, created.text
    family = created.json()["data"]
    assert family["role"] == "OWNER"

    invited = client.post(
        f"/api/v1/families/{family['id']}/invitations",
        json={"invitee_email": "partner@example.com", "proposed_role": "ADULT"},
    )
    assert invited.status_code == 201, invited.text
    token = invited.json()["data"]["token"]
    assert token

    client.post("/api/v1/auth/logout")
    _register(client, email="partner@example.com")
    accepted = client.post(f"/api/v1/family-invitations/{token}/accept")
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["data"]["role"] == "ADULT"

    # Both are now members, and /auth/me reports it.
    me = client.get("/api/v1/auth/me").json()["data"]
    assert me["active_family"]["name"] == "Our Household"
    assert len(client.get("/api/v1/families/current").json()["data"]["members"]) == 2


def test_the_invitation_token_is_only_ever_returned_once(client):
    _register(client, email="owner@example.com")
    family_id = client.post("/api/v1/families", json={"name": "H", "base_currency": "RWF"}).json()[
        "data"
    ]["id"]
    client.post(
        f"/api/v1/families/{family_id}/invitations", json={"invitee_email": "p@example.com"}
    )
    listed = client.get(f"/api/v1/families/{family_id}/invitations").json()["data"]
    # Only the hash is stored, so listing cannot reveal it again.
    assert "token" not in listed[0]


def test_cannot_belong_to_two_households(client):
    _register(client, email="owner@example.com")
    client.post("/api/v1/families", json={"name": "First", "base_currency": "RWF"})
    second = client.post("/api/v1/families", json={"name": "Second", "base_currency": "RWF"})
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "ACTIVE_FAMILY_ALREADY_EXISTS"


def test_an_invitation_for_someone_else_is_not_yours_to_accept(client):
    _register(client, email="owner@example.com")
    family_id = client.post("/api/v1/families", json={"name": "H", "base_currency": "RWF"}).json()[
        "data"
    ]["id"]
    token = client.post(
        f"/api/v1/families/{family_id}/invitations",
        json={"invitee_email": "intended@example.com"},
    ).json()["data"]["token"]

    client.post("/api/v1/auth/logout")
    _register(client, email="someone-else@example.com")
    # 404 rather than 403: do not confirm the invitation exists.
    assert client.post(f"/api/v1/family-invitations/{token}/accept").status_code == 404


def test_only_the_owner_can_invite(client):
    _register(client, email="owner@example.com")
    family_id = client.post("/api/v1/families", json={"name": "H", "base_currency": "RWF"}).json()[
        "data"
    ]["id"]
    token = client.post(
        f"/api/v1/families/{family_id}/invitations", json={"invitee_email": "a@example.com"}
    ).json()["data"]["token"]
    client.post("/api/v1/auth/logout")

    _register(client, email="a@example.com")
    client.post(f"/api/v1/family-invitations/{token}/accept")
    denied = client.post(
        f"/api/v1/families/{family_id}/invitations", json={"invitee_email": "b@example.com"}
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "INVITE_NOT_ALLOWED"


def test_sharing_an_account_makes_it_visible_to_the_household(client):
    _register(client, email="owner@example.com")
    family_id = client.post("/api/v1/families", json={"name": "H", "base_currency": "RWF"}).json()[
        "data"
    ]["id"]
    account_id = _create_account(client, name="Salary").json()["data"]["id"]
    token = client.post(
        f"/api/v1/families/{family_id}/invitations", json={"invitee_email": "p@example.com"}
    ).json()["data"]["token"]

    shared = client.patch(
        f"/api/v1/accounts/{account_id}/visibility", json={"visibility": "FAMILY_VISIBLE"}
    )
    assert shared.status_code == 200, shared.text
    assert shared.json()["data"]["visibility"] == "FAMILY_VISIBLE"

    client.post("/api/v1/auth/logout")
    _register(client, email="p@example.com")
    client.post(f"/api/v1/family-invitations/{token}/accept")

    # Joining shares nothing of their own, but they can now see the salary.
    personal = client.get("/api/v1/accounts").json()["data"]
    assert personal == []
    family_view = client.get("/api/v1/accounts?context=family").json()["data"]
    assert [a["name"] for a in family_view] == ["Salary"]
    # Visible is not writable.
    assert family_view[0]["can_transact"] is False


def test_joining_leaves_your_own_accounts_private(client):
    """Nothing is shared until you say so."""
    _register(client, email="owner@example.com")
    family_id = client.post("/api/v1/families", json={"name": "H", "base_currency": "RWF"}).json()[
        "data"
    ]["id"]
    token = client.post(
        f"/api/v1/families/{family_id}/invitations", json={"invitee_email": "p@example.com"}
    ).json()["data"]["token"]
    client.post("/api/v1/auth/logout")

    _register(client, email="p@example.com")
    account_id = _create_account(client, name="Mine").json()["data"]["id"]
    client.post(f"/api/v1/family-invitations/{token}/accept")

    detail = client.get(f"/api/v1/accounts/{account_id}").json()["data"]
    assert detail["visibility"] == "PRIVATE"
    assert client.get("/api/v1/accounts?context=family").json()["data"] == []


def test_dashboard_and_net_worth_respond_in_both_contexts(client):
    _register(client)
    _create_account(client)
    for context in ("personal", "family"):
        assert client.get(f"/api/v1/dashboard?context={context}").status_code == 200
        assert client.get(f"/api/v1/reports/net-worth?context={context}").status_code == 200


def test_meta_names_the_build(client):
    """The About screen needs this before it necessarily has a session, so it
    is unauthenticated like the health endpoints beside it."""
    response = client.get("/api/v1/meta")
    assert response.status_code == 200
    assert response.json() == {"name": "Montra", "version": APP_VERSION}


def test_the_openapi_document_carries_the_same_version():
    """One number for the running system, not one per place that shows it."""
    from app.main import app

    assert app.version == APP_VERSION
