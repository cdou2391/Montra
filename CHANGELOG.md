# Changelog

Semantic versioning, still below 1.0: a **minor** bump is a new capability, a
**patch** is a fix, a refinement, or a change to how the app is built.

`backend/app/core/version.py` is the source of truth — it is what the API
serves at `/api/v1/meta` and what App settings shows. `frontend/package.json`
carries the same number so a reader of the repo is not misled, but nothing
displays it.

---

## 0.2.0

**Budgets.** A monthly spending ceiling per category. Progress is derived from
the ledger on every read rather than stored, so a budget cannot disagree with
the transactions underneath it. Transfers do not count as spending, foreign
charges are converted before they are compared, and a currency with no known
rate is named rather than guessed at. Each month stands alone; nothing carries.

**App settings.** Appearance, balance privacy, notifications and exchange
rates move off Profile onto their own page, leaving Profile to what it says:
you, and your records. Adds an About card carrying the app name and this
version.

**Production images.** Both images are multi-stage. The web runtime carries
Next's standalone server, the API runtime a built virtualenv, and neither
keeps a package manager — which is where every container advisory lived. A
production compose publishes only the proxy, runs migrations as a one-shot job
the API waits on, and keeps Postgres, Redis and object storage off the host.

**Fixes.** Loan payments interleave with planned items by date instead of
sitting in a block below them. A card authorisation SMS is parsed, including
the phone-order wording and the foreign-currency conversion a local card needs.
An account can be kept out of the net-worth totals.

## 0.1.0

Everything before the above: accounts, the posting engine, cards, planning and
recurrence, loans, households, reporting and the forecast, attachments, the
audit trail, search, multi-currency, SMS parsing, and the security work.
