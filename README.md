# Montra

Personal and household finance tracking. Mobile-first web application.

Montra answers five questions: how much you have, how much you owe, where the
money went, what is coming next, and what your household's position looks like.

This README covers running the code. Behaviour is specified in a separate
document set that is not published with the source.

---

## Current status

Implemented through **Phase 29** of the implementation plan — milestones
**M1 (Platform)** through **M7 (Reporting)**, plus search, attachments,
auditing and security hardening.

| Area | What works |
|---|---|
| Accounts | Eight types — checking, savings, cash, mobile money, credit card, prepaid card, investment, other. Reconciliation, archiving, per-account exclusion from totals |
| Ledger | Income, expenses, transfers, fees as their own line, soft deletes, idempotent transfers |
| Cards | Credit limit, utilization, available credit, statement and due dates, payments, prepaid top-ups, expiry warnings |
| Planning | Upcoming and recurring transactions, rescheduling, completion, a 90-day recurrence window |
| Debt | Loans payable and receivable, amortized schedules, principal/interest/fee splits |
| Household | Three visibility levels, membership roles, sharing, personal/family context switch |
| Reporting | Dashboard, net worth, 30-day cash-flow forecast, insights |
| Money in | Paste a mobile-money, bank or card SMS and the form fills itself |
| Currency | Multi-currency accounts converted to one base, with rates fetched daily |
| Records | Receipts and proof attached to transactions, household audit trail, JSON backup and restore |
| Interface | Installable PWA, light and dark themes, search and filters |

Not built: CSV import/export, budgets, and the observability and production
work of Phases 30-31. Backup and restore are JSON rather than CSV.

---

## Running it

Requires Docker and Docker Compose.

```bash
cp .env.example .env
docker compose up -d
```

| Service | URL |
|---|---|
| App, through the proxy | http://localhost:8080 |
| Frontend, direct | http://localhost:3000 |
| API | http://localhost:8000/api/v1 |
| OpenAPI docs | http://localhost:8000/api/v1/docs |
| Object storage console | http://localhost:9001 |
| Mail catcher | http://localhost:8025 |

Use the proxy for anything involving attachments: an upload is signed against
the host that issued it, so reaching the frontend and the storage through the
same origin is what makes the signature verify.

Then apply migrations and open the app:

```bash
docker compose run --rm --no-deps api alembic upgrade head
```

`make help` lists the shortcuts.

---

## Architecture

A modular monolith.

```text
browser ──▶ proxy (nginx) ──┬──▶ web (Next.js)
                            ├──▶ api (FastAPI)
                            └──▶ minio         receipts, fetched on a signed URL

api ──┬──▶ postgres   financial source of truth
      ├──▶ redis      queue, cache, rate limiting
      └──▶ minio      issues the signed URLs

worker + scheduler ──▶ postgres, redis
      Celery: recurrence, reminders, expiry warnings, FX rates
```

Queues are `default`, `recurring`, `reminders` and `notifications`. Beat
regenerates the 90-day recurrence window hourly, sweeps due reminders every 15
minutes, promotes due planned items on the hour, warns about expiring cards at
06:30, and refreshes exchange rates at 07:00 — published rates settle
overnight, so the day's totals are current before anyone opens the app.

Every schedule and reminder definition lives in Postgres, never only in the
broker: losing Redis loses no reminders, because the next run re-reads state
from the database.

```text
backend/
  app/
    api/v1/      route handlers, thin: parse, authorize, delegate, serialize
    core/        config, logging, errors, money, security
    db/          engine, session, enums
    models/      SQLAlchemy models
    schemas/     Pydantic request models
    services/    domain logic — posting, accounts, transactions, auth, authz,
                 forecast, insights, currency, sms_parser, attachments, audit
  alembic/       migrations
  tests/         ledger invariants and API behaviour
frontend/
  app/           Next.js routes
  components/    shell, UI primitives, financial components
  lib/           API client, formatting
infra/nginx/     the proxy that fronts the app and the object store
scripts/         security-scan.sh — dependency and container advisories
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

649 tests. The ledger suites
([`test_posting.py`](backend/tests/test_posting.py),
[`test_transfers.py`](backend/tests/test_transfers.py)) are the ones that matter
most — they assert the financial invariants directly: card purchases raise debt,
repayments lower it, transfers preserve net worth, cancelled and deleted entries
leave no trace in a balance, and decimal precision survives repeated postings.
[`test_time.py`](backend/tests/test_time.py) covers the timezone boundaries
where an hours-off bug would otherwise be invisible, and
[`test_cards.py`](backend/tests/test_cards.py) guards the three card
properties the plan singles out: a purchase is an expense that raises debt, a
payment lowers cash and debt together, and a payment is never an expense.
[`test_planning.py`](backend/tests/test_planning.py) holds the line that a
planned transaction is not a ledger entry until it is completed, and that
completing one twice cannot post twice.
[`test_loans.py`](backend/tests/test_loans.py) guards the payment split: a
repayment is not all spending.
[`test_family_authorization.py`](backend/tests/test_family_authorization.py) is
the visibility matrix the plan gates the family work on, and
[`test_transfer_redaction.py`](backend/tests/test_transfer_redaction.py) checks
at the serialization layer that a private counterparty never leaves the API.
[`test_sms_parser.py`](backend/tests/test_sms_parser.py) pins each message
format the parser claims to read, including the ones it must refuse — a
declined card authorisation fills nothing, because prefilling a purchase that
never happened puts it one tap from being posted.
[`test_currency.py`](backend/tests/test_currency.py) covers conversion and the
rule that an unconvertible balance is named rather than added at 1:1, and
[`test_security_hardening.py`](backend/tests/test_security_hardening.py) holds
the password policy, rate limiting and origin checks. Coverage elsewhere is
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
  original transfer instead of posting again. Card payments and prepaid
  top-ups share that mechanism, because both are transfers underneath.
- Reconciliation records the difference as its own ADJUSTMENT entry. It never
  rewrites history or edits the opening balance.
- A planned transaction is not a ledger entry. Creating, rescheduling and
  cancelling touch no balance; only completion posts, and it delegates to the
  posting engine. Completion locks the row `FOR UPDATE` before reading its
  status, so two concurrent completions cannot both post.
- Recurring rules generate planned occurrences inside a 90-day window, never
  actual transactions. `(recurring_rule_id, occurrence_date)` is unique in the
  database, so a concurrent generation cannot duplicate an occurrence.
- A loan payment is up to three ledger entries. Principal posts as a TRANSFER,
  because settling a debt you already carried is not spending; interest and
  fees post as expense (payable) or income (receivable). Cash moves by the
  total, analytics move by interest and fees only. The database enforces
  `principal + interest + fees = total`.
- Loan outstanding principal is derived from the opening figure minus principal
  paid. The original loan amount is never overwritten.
- Visibility has three levels and reading is not writing. PRIVATE is owner-only
  and answers 404 rather than 403, since 403 confirms a record exists.
  FAMILY_VISIBLE lets the household read but only the owner write. SHARED lets
  OWNER and ADULT transact. Child records resolve through their account, never
  through their author.
- Sharing is derived from the caller's own membership, never from a `family_id`
  in the request. Joining a household shares nothing until you say so, and
  leaving returns everything to private.
- Private data is excluded from aggregates before they are summed, and scoping
  is by account, so a shared account counts once rather than once per member.
- A ledger entry is denominated in its account's currency; there is no
  per-transaction currency. Mixed-currency totals are converted first, and a
  balance with no known rate is left out of the sum and named, because adding
  dollars to francs at 1:1 gives a wrong total rather than a rough one.
- Exchange rates are fetched daily into a shared table with two bases. A pair
  neither base covers is crossed through one of them rather than fetched.
- The SMS parser writes nothing. It returns a draft the user submits, so a
  misread message costs a correction rather than a wrong balance. Every field
  is optional: a blank field is obvious on the form, while an invented amount
  looks exactly like a real one.
- Attachments are uploaded and fetched on signed URLs issued by the API; the
  bucket is never public. The signature covers the host as well as the path,
  which is why the proxy passes the original `Host` through unchanged.
- Passwords are checked on length and guessability rather than composition
  rules. Rate limiting is fixed-window in Redis and fails open — an outage
  degrades enforcement rather than locking everyone out.
- Cross-origin writes are refused by comparing `Origin` against the host that
  served the request, not against a fixed allowlist that breaks the moment the
  app is reached by a hostname nobody thought to add.
