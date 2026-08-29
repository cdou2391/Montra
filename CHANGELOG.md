# Changelog

Semantic versioning, still below 1.0: a **minor** bump is a new capability, a
**patch** is a fix, a refinement, or a change to how the app is built.

`backend/app/core/version.py` is the source of truth — it is what the API
serves at `/api/v1/meta` and what App settings shows. `frontend/package.json`
carries the same number so a reader of the repo is not misled, but nothing
displays it.

---

## 0.4.18

**Switching to the household flashed the personal net worth first.** For a
frame or two the old figure sat under the new heading, then jumped. It read
like the household total settling on an answer, which is the worst possible
reading of a number that was simply the wrong one.

Nothing cleared the previous context's data. The fetch went out, the old
accounts stayed in state, and the render in between used them. Doing the
clearing in the effect would have been worse, not better: an effect runs after
a paint, so the stale figure shows, then the skeleton, then the answer — two
changes instead of one. The reset happens during render, which is React's own
answer to this, and the stale value never reaches the screen at all.

The same fix applies to Accounts, Transactions, Budgets and Goals, which all
had the identical flash — the previous context's rows are not a preview of
this one's.

---

## 0.4.17

**The More button says which way it goes.** Three dots is a symbol you have
to have learned; a chevron is a direction you can read. Up while the panel is
shut — there is more above this — and down while it is open, which is also
the way you would swipe it away.

It is one chevron rotated rather than two icons swapped, so the change is a
movement the eye follows rather than a substitution it has to notice, and
reduced motion turns the rotation off without losing the direction.

It is also a toggle now. Tapping More while the panel was open called
`setMoreOpen(true)` on something already true and did nothing — invisible
before 0.4.16, because the panel's backdrop covered the button; visible as
soon as the bar started sitting above it.

---

## 0.4.16

**More is part of the bar now, not a menu over it.** It opened as a
full-width sheet with its own surface, its own rounding and rows of
icon-in-a-circle plus a line of explanatory text — a different kind of object
that happened to appear when you tapped the bar.

The panel now matches the bar exactly: same width, same radius, same
elevated surface, sitting directly above it. The bar keeps its own colour
while the panel is open rather than dimming behind the backdrop, so the two
read as one stack — which is what the code always claimed, since the comment
on that button has said "expands the bar in place" from the start.

The destinations are the bar's own tile: icon over an 11px label, four
across, one accent colour for the current page. Sign out is the last tile
rather than a row of its own; it is the same kind of thing, and the colour
already says which one it is.

The hints went with the rows. Ten one-line descriptions is a lot of reading
for a menu whose entries are called Profile, Loans and Budgets.

---

## 0.4.15

**Nothing in the production stack had a ceiling.** On a single host that means
any container can take the database down with it, and the database is the one
process whose death costs data rather than uptime. Every service now has a
memory limit, a CPU limit and a process cap, sized for a shared 2-core 4 GB
box. They are ceilings, not reservations, so they deliberately sum to more
than the machine has; Postgres additionally gets a soft reservation so the
kernel reclaims from something else first.

**The worker was forking once per CPU.** Celery's prefork pool defaults to the
core count, so the same image used 606 MB on a sixteen-core machine and 120 MB
on a two-core one — and, less visibly, multiplied its database connection pool
by the same factor. Concurrency is now pinned at 2. Five scheduled jobs a day
do not need more.

**The connection arithmetic did not add up.** The engine held pool_size=10 with
max_overflow=20 — thirty connections per process — and a Celery fork is a
process. Sixteen forks could demand 480 connections from a server configured
for 100. It never happened because the jobs are short and daily, but it was
latent and it got *worse* on a bigger host. Pool size is now configurable, and
the worker and scheduler set it far below the API's: two forks at 2+3 is ten
connections rather than sixty.

**Redis had no memory bound.** It is Celery's broker, so the policy is
noeviction rather than an LRU: evicting a key under pressure silently discards
a queued task, and refusing the write surfaces the problem where it can be
seen.

Log rotation tightened from 10 MB x 5 to 5 MB x 3 per service — the old
setting allowed 400 MB across the stack, which is real money on a 20 GB disk.

---

## 0.4.14

**A denser layout.** Spacing and type were both a step roomier than the app
needed, and on a phone that cost a visible row of content on most screens.

Density is now a single number. `TIGHTEN` in `tailwind.config.ts` scales the
whole spacing scale — currently 0.875, so `p-4` is 14px rather than 16 and
`gap-3` is 10.5 rather than 12 — which means `p-4` still means the same thing
in every file and one edit moves the entire app. The type scale is re-cut on
the same basis, trimming line height harder than glyph size: leading is where
the airiness sits and it costs less legibility to take back. `text-xs` stops
at 11px, which is the floor for a hint on a phone.

Touch targets deliberately sit outside that scale. They are written as pixel
values, so density cannot shrink a thumb target: full-width controls moved
from 48px to 44px, which is the floor from the UI/UX spec rather than a
compromise against it, and nothing else moved at all.

Two things had been written as fixed pixels against the old scale and would
have drifted: the toggle knob travelled a hard-coded 22px along a track that
now measures 38.5, and the skeleton blocks were measured against the old
padding. The knob now travels by its own width — the track is exactly two
knobs wide between its insets, at any density — and the skeletons were
re-cut to match what they stand in for.

---

## 0.4.13

**Recurring payments left out your loan instalments.** The figure counts what
leaves every month "before anything else", and it was reading only recurring
rules. Loan instalments come from each loan's own schedule and never become
rules, so the two largest fixed payments were missing. On real data it read
RWF 292,500 where the answer was 1,049,513.

Payable instalments now count, receivables do not, and the detail line says
how many are loans — the number jumps otherwise and a loan is not something
most people file under subscriptions.

The same figure also added foreign amounts raw, so a ten dollar subscription
counted as ten francs. It converts now.

## 0.4.12

**The More sheet can be dragged shut.** The handle at the top has always looked
draggable and was decorative; now it is the thing it looked like.

It closes on a long drag or a quick flick, and springs back on a short one.
Both, because distance alone refuses a fast short flick and speed alone closes
on a twitch. The strip around the line is the target rather than the line
itself, which is too thin for a thumb.

Escape, the backdrop and the links inside all still work.

## 0.4.11

**A signing-out screen.** Clearing the session is a request and a navigation,
and for two or three seconds neither had shown anything — the screen sat there
still displaying the account being signed out of, which reads as a tap that
did not land.

The overlay goes up the moment the button is pressed and stays until the login
page replaces it. Shared by all three ways out — the profile card, the desktop
sidebar and the More sheet — which all had the same pause.

A failed request still lands on the login page. The session may be gone at the
server regardless, and staying put is the worse guess.

## 0.4.10

**A make target for UAT, because deploying half of it showed a stale version.**
The version the app displays comes from the API image, so rebuilding only the
service that changed left About reporting whatever the API was last built at —
0.4.8 while the repository said 0.4.9.

`make uat` builds and starts the whole stack, names no service, restarts the
proxy so it does not hold a stale upstream, waits for health, and prints the
version it ends up serving. `make uat-down` and `make uat-logs` alongside it.

## 0.4.9

**Sign in.** The password can be revealed, the fields freeze while the request
is in flight, and the button keeps saying "Signing in…" until Home actually
appears.

It used to stop early: the busy flag was cleared in a finally block that ran
the moment navigation was requested, not when it finished, so the button went
back to "Sign in" while the next screen was still loading — a dead pause that
invites a second tap.

Register had all three of the same faults and gets the same fixes. A failed
submit still re-enables the form.

## 0.4.8

**One loading state on refresh, not two.** The session guard replaced the whole
app with three grey slabs while it restored the session, and only then let the
page mount and show its own, differently shaped placeholder. A refresh went
slab, then skeleton, then content.

The page now renders while the session is still being restored. Every page
already handles its data not having arrived, so there is nothing for a second
placeholder to do. A refresh of Home now holds one shape throughout.

Nothing is exposed by rendering early: without a session the requests come
back empty and the redirect fires when /me resolves, no later than the block
used to lift. Verified on four guarded pages with no cookie.

## 0.4.7

**The last of the loading states, and an empty dropdown.** Settings, the reset
warning and Household lose their inline slabs for toggle rows and count rows.

The form pages keep no skeleton, deliberately: they render whole and only
their pickers fill in a moment later, so replacing them would take away fields
that were already usable. But six account pickers rendered with no options at
all while their fetch was in flight — a select that opens onto nothing. They
now say "Loading accounts…" until the list arrives.

## 0.4.6

**The rest of the loading states.** Planning, Recurring, Forecast,
Transactions, Loans, Notifications, the detail screens and the forms all
preview their own structure now, on four shapes: grouped rows, a form's
labelled fields, a record's figure over its detail, and a headline over a
chart.

Planning also joins Accounts in rendering one header across every state, so
its Add, Forecast and Recurring controls no longer appear only once the data
does.

## 0.4.5

**Loading states shaped like what replaces them.** Every page showed a single
grey slab of an arbitrary height — h-32, h-48, h-64, picked by eye — and then
rearranged into something structurally unrelated. Home stood one 128px block
in for a net-worth card, a two-column metric grid, an account carousel, a
chart and two lists.

Home, Accounts, Budgets and Goals now preview their real structure: a card
where a card goes, a scrolling row where tiles go, repeated lines where a list
goes.

The header was part of it. Accounts rendered a bare title while loading and
then grew an Add button and the privacy toggle, so the top bar moved too.
Neither depends on the data, so every state now renders the same header.

## 0.4.4

**Restore rejected the backups this version produces.** The client checked the
format version against a hardcoded 1 before letting the file through, and 0.4.1
moved the format to 2 without updating it. Every fresh backup was refused with
"that file is not a Montra backup this version can read" — a file the server
would have accepted.

The client no longer holds a copy of the number. It checks only that the file
is a Montra backup at all, so an obviously wrong one is still rejected before
a password is typed, and leaves whether the version is readable to the server,
which owns it.

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
