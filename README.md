# Montra

Personal and household finance tracking. Mobile-first web application.

Montra answers five questions: how much you have, how much you owe, where the
money went, what is coming next, and what your household's position looks like.

The full specification set lives in [`docs/`](docs/). This README covers running
the code; the documents are the source of truth for behaviour.

---

## Current status

Implemented through **Phase 7** of the
[implementation plan](docs/Montra%20—%20End%20to%20End%20Implementation%20Plan.md) —
milestones **M1 (Platform)** and **M2 (Financial Core)**.

| Working | Not yet built |
|---|---|
| Registration, login, logout, sessions | Planned and recurring transactions |
| Default categories and onboarding | Reminders, worker jobs, notifications |
| Accounts of all eight types | Loans payable and receivable |
| The financial posting engine | Family sharing and the family dashboard |
| Income, expenses, transfers | Net worth history, forecasting, insights |
| Balance reconciliation | Attachments, audit log, CSV import/export |

Family sharing is deliberately refused rather than half-enforced: creating a
`FAMILY_VISIBLE` or `SHARED` account returns `NO_ACTIVE_FAMILY` until the
authorization rules in Phases 16-19 exist to back it up.

---

## Running it

Requires Docker and Docker Compose.

```bash
cp .env.example .env
docker compose up -d
```

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| API | http://localhost:8000/api/v1 |
| OpenAPI docs | http://localhost:8000/api/v1/docs |
| Mail catcher | http://localhost:8025 |

Then apply migrations and open the app:

```bash
docker compose run --rm --no-deps api alembic upgrade head
```

`make help` lists the shortcuts.

---

## Architecture

A modular monolith, following the
[technical architecture spec](docs/Montra%20—%20Technical%20Architecture%20Specification.md).

```text
web (Next.js) ──▶ api (FastAPI) ──┬──▶ postgres   financial source of truth
                                  └──▶ redis      queue and cache
                                            ▲
                       worker + scheduler ──┘     (Celery, jobs land in Phase 12+)
```

```text
backend/
  app/
    api/v1/      route handlers, thin: parse, authorize, delegate, serialize
    core/        config, logging, errors, money, security
    db/          engine, session, enums
    models/      SQLAlchemy models
    schemas/     Pydantic request models
    services/    domain logic — posting, accounts, transactions, auth, authz
  alembic/       migrations
  tests/         ledger invariants and API behaviour
frontend/
  app/           Next.js routes
  components/    shell, UI primitives, financial components
  lib/           API client, formatting
```

---

## The posting engine

Every balance-moving operation goes through
[`app/services/posting.py`](backend/app/services/posting.py). Routes never
create a `Transaction` or mutate a balance directly.

The engine's one job is turning an operation plus an account's nature into a
ledger direction, where direction is defined against the account's **own balance
scale**:

- `INCREASE` — the account's own balance goes up: asset value up, or debt owed up
- `DECREASE` — the account's own balance goes down

This is deliberately not double-entry debit/credit. There are no contra
accounts, and only a transfer writes two entries. The whole rulebook is one
table:

| Operation | ASSET | LIABILITY |
|---|---|---|
| Income | INCREASE | DECREASE (refund lowers debt) |
| Expense | DECREASE | INCREASE (card purchase raises debt) |
| Transfer out | DECREASE | INCREASE (cash advance borrows more) |
| Transfer in | INCREASE | DECREASE (repayment lowers debt) |

A consequence worth internalising: **a credit-card repayment decreases both
sides.** The asset loses value and the liability loses debt, so net worth is
unchanged. Transfers are not always one increase and one decrease.

Balances are always derived, never cached:

```text
opening_balance + SUM(INCREASE) - SUM(DECREASE)
```

One formula covers both natures, because direction already carries the
account's perspective.

---

## Tests

```bash
make test
```

70 tests. The ledger suites
([`test_posting.py`](backend/tests/test_posting.py),
[`test_transfers.py`](backend/tests/test_transfers.py)) are the ones that matter
most — they assert the financial invariants directly: card purchases raise debt,
repayments lower it, transfers preserve net worth, cancelled and deleted entries
leave no trace in a balance, and decimal precision survives repeated postings.
[`test_time.py`](backend/tests/test_time.py) covers the timezone boundaries
where an hours-off bug would otherwise be invisible. Coverage elsewhere is
deliberately lighter.

---

## Conventions

- Money is `DECIMAL(20,4)` in the database and a **string** in JSON. No float
  ever touches a financial value.
- Financial events carry a full timestamp. `occurred_at` is when the money
  moved; `created_at` is when it was entered. Both are stored UTC and rendered
  in the user's timezone. Date filters resolve to local day boundaries, so a
  23:30 purchase belongs to that day and not the next.
- Amounts are stored positive; `direction` carries the ledger effect.
- Authorization is enforced server-side in `services/authz.py`. A resource the
  caller may not see returns `404`, not `403`, so the API never confirms that
  someone else's private account exists.
- Deletes are soft. A cancelled or deleted transaction stops affecting balances
  but stays on the record.
- Transfers accept an `Idempotency-Key` header; replaying a key returns the
  original transfer instead of posting again.
