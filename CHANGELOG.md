# Changelog

Semantic versioning, still below 1.0: a **minor** bump is a new capability, a
**patch** is a fix, a refinement, or a change to how the app is built.

`backend/app/core/version.py` is the source of truth — it is what the API
serves at `/api/v1/meta` and what App settings shows. `frontend/package.json`
carries the same number so a reader of the repo is not misled, but nothing
displays it.

---

## 0.4.3

**A UAT environment.** The production images and topology, running on plain
HTTP so they can be used locally without a certificate.

MONTRA_ENV is what separates them, and it governs exactly three things:
production refuses to start on an unsafe setting, sends HSTS, and forces the
session cookie to Secure whatever the file says. On http:// that last one
means the browser never keeps a session, which is why the earlier attempt
started but could not sign in.

HSTS is the reason this is not simply "production with a self-signed cert on
localhost": it pins a hostname, not a port, so a production stack on localhost
would send the development stack on :8080 to HTTPS for a year.

The production compose no longer fixes its container names, so UAT and
development run side by side under different project names.

## 0.4.2

**Reconciliation tests.** Whole scenarios played through the real services,
checked against arithmetic written out in the test so a reader can verify the
expected numbers without running anything. The plan's reference sequence is
there verbatim, alongside fees, a loan payment's three-way split, foreign
balances, an excluded account, and a realistic month that exercises all of it
at once.

Every other suite asserts one behaviour in isolation. These exist because the
bugs that got through — a backup dropping a recurring transfer's destination,
a reset a goal blocked — were interaction bugs that passed 717 isolated tests.

Verified by breaking the code on purpose: inverting the card-purchase
direction fails three of them, removing currency conversion fails two.

## 0.4.1

**The backup had fallen behind, in one place since before this release.**
Backup format version 2.

Missing entirely: budgets, goals, and your own exchange-rate overrides.
Missing from things it did export: an account's excluded-from-totals flag, the
goal tag on transfers, rules and planned items, the link from a fee to what it
was charged on, and — the oldest and worst — the destination account of a
recurring or planned transfer. A restored recurring transfer had nowhere to
send the money, and the restore side was already reading a field the export
never wrote.

A backup that silently drops things is worse than none: accounts and balances
come back, so it looks like it worked.

Two guards now hold it in step. One fails when a table is neither exported nor
on a list of deliberate exclusions with a reason; the other fails when an
account gains a column the backup does not carry. Both were checked by
breaking them on purpose.

**Profile reset was broken for anyone with a goal.** A goal holds its account
with RESTRICT, and the reset never deleted goals, so it failed at the database
after the password had already been accepted. Found by the backup round-trip
test, not by the reset's own suite.

## 0.4.0

**Recurring contributions to a goal.** A recurring transfer can now name the
goal it is for. The tag travels from the rule to each occurrence it generates,
and from there onto the transfer that completing one posts — so a monthly
standing contribution counts towards the goal instead of merely moving money
into the account it sits in.

Without it the failure was quiet: the balance would rise every month while the
goal sat at zero, and nothing would say why. A one-off planned transfer can
carry the tag too.

The picker appears only on a transfer, and only lists goals saving into the
account the money is going to — a contribution has to land where the goal
lives. A goal card links straight to the form.

## 0.3.1

**Shared budgets and goals.** Both create forms now offer who can see it, where
there is a household to share with. A goal can also be shared after it is made,
which budgets could already do.

The household scoping itself was already working — it simply had no tests and
no way to reach it from the interface. It has thirteen tests now, covering
each visibility level, the member who should see it, the outsider who should
not, and the refusal to share when there is no household to share into.

## 0.3.0

**Goals.** An amount to save into an account, optionally by a date. A goal
keeps no tally: a contribution is a real transfer tagged with the goal, so
progress is summed from movements that actually happened and cannot drift from
the ledger. That is also what lets several goals share one savings account.

A dated goal reports what it takes each month to arrive on time; an undated one
says nothing about pace rather than inventing a deadline. Reaching the target
marks the goal achieved and notifies, and the money stays where it is until you
move it — taking it back out un-marks it.

Spending from a goal's account without tagging it cannot be prevented on the
write path, so it is measured daily instead: at 06:45 every goal's status is
brought in line with the ledger, and an account whose goals claim more than it
holds raises a notification. Once, not every morning.

The screen shows progress, what is left, and — where a date was set — what to
put aside each month. Adding money posts the tagged transfer, so contributing
from the goal card and transferring by hand are the same operation underneath.

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
