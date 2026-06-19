# FlexTime — Solution

My notes on how I built FlexTime: the choices I made, the assumptions I took
where the brief stayed quiet, the trade-offs, and what's done versus still to
do. The assignment itself is in [README.md](README.md) and
[specifications.md](specifications.md).

>  Still in progress — I update this file as I go.

---

## Setup instructions

```bash
# 1. Create and activate a virtual environment
python -m venv venv
source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set up your email credentials (see "Email setup" below)
cp .env.example .env   # then edit .env with your SMTP details

# 4. Generate the migrations from the models, then apply them.
#    Migration files are intentionally not committed to the repo, so you
#    regenerate them from the current models here before applying.
python manage.py makemigrations
python manage.py migrate

# 5. (Optional) create an admin account to look at the data
python manage.py createsuperuser

# 6. Start the dev server, then open http://127.0.0.1:8000/sign-in/
python manage.py runserver

# Run the tests
python manage.py test
```

**Email setup (magic links).** Sign-in emails go out over SMTP. Copy
`.env.example` to `.env` (it's gitignored) and fill in your values — the app
loads them automatically with `python-dotenv`:

| Variable | What it's for |
| --- | --- |
| `EMAIL_HOST` | SMTP server host (e.g. `smtp.gmail.com`) |
| `EMAIL_PORT` | SMTP port (default `587`) |
| `EMAIL_HOST_USER` | SMTP username |
| `EMAIL_HOST_PASSWORD` | SMTP password (for Gmail, an App Password) |
| `EMAIL_USE_TLS` | `true`/`false` (default `true`) |
| `DEFAULT_FROM_EMAIL` | The "from" address on sign-in emails |
| `SITE_URL` | Base URL used to build the magic links |

> For Gmail you need 2-Step Verification on and an
> [App Password](https://myaccount.google.com/apppasswords) (your normal Gmail
> password won't work over SMTP).

---

## Architecture decisions

- **Django templates, not React.** The brief prefers it, and it means I don't
  need a separate REST API. Less code, more focus.
- **Two apps.** `accounts` handles login and the user. `core` handles the rest:
  calendar, slots, activities, interest, access. Keeping login separate from the
  business logic keeps things tidy.
- **A custom user instead of Django's default.** I extended `AbstractBaseUser`,
  not `AbstractUser`. `AbstractUser` forces a `username` field I don't need.
  `AbstractBaseUser` gives me just the login plumbing and lets me pick my own
  fields: email, first name, last name. Email is the login. No dead `username`
  column left behind.
- **I set up the custom user on day one.** Switching the user model later, after
  migrations exist, is a real pain. Easier to do it first.
- **SQLite.** Nothing to set up for whoever reviews this. Moving to PostgreSQL
  later would be easy thanks to the ORM.

---

## Login (passwordless)

No passwords, and no extra library — plain Django does the job:

- `django.core.signing` builds and checks the magic-link token. The token is
  signed and time-stamped, so I can check it's valid and not expired **without
  saving it in the database**.
- `django.contrib.auth` (`login` / `logout`) handles the session once the link
  checks out.

A normal user never has a real password — the manager calls
`set_unusable_password()`, so the only way in is the magic link. The one
exception is the admin superuser, who keeps a password so I can use the Django
admin.

There are two flows, like the brief asks, and I keep them on **two separate
pages** so each only asks for what it needs (rather than one combined form that
shows name fields to everyone):

- **Sign up** (`/sign-up/`): first name, last name, email → the account is
  created (its shareable calendar link is generated at the same time) → a magic
  link is emailed. Submitting an email that already exists is refused with a
  pointer to sign in. On top of the format check, the email is run through a
  validator that rejects **disposable / throwaway domains** (mailinator, yopmail,
  …) — an account should be tied to a lasting address, since that's where every
  magic link goes. The denylist (`accounts/validators.py`) is small and
  representative; a production app would use a maintained list.
- **Sign in** (`/sign-in/`): email only → a fresh magic link is emailed. No new
  account. An unknown email is refused with a pointer to sign up.

Each page links to the other (carrying any `?next=`), so a visitor who lands on
the wrong one is one click away from the right one. The trade-off: splitting the
flows makes the pages tell you whether an email is registered (a mild
user-enumeration signal). Acceptable here, and the rate limit blunts probing.

**Sending you back where you came from.** If you click a shared calendar link
while logged out, `@login_required` sends you to sign-in with a `?next=` URL
(Django's standard mechanism). The magic-link email doesn't carry that `next`,
so I stash it in the session and, after the link is verified, redirect you to
it — back to the calendar you originally clicked. The target is checked with
`url_has_allowed_host_and_scheme` (against the current host) so it can only ever
be a page on our own site, never an outside redirect.

**Rate limiting the magic-link request.** Both forms email a link on every
submit (and sign-up also creates an account), so without a guard anyone could
flood a victim's inbox (email bombing) or create accounts in bulk. I cap
requests at `MAGIC_LINK_RATE_LIMIT` per
`MAGIC_LINK_RATE_WINDOW` seconds (defaults: 3 per 10 minutes), counted **per
email address and per client IP** — the email key protects a specific victim's
inbox, the IP key stops an attacker who just varies the email. The IP is read
from `REMOTE_ADDR` (the actual connection), **not** `X-Forwarded-For`: with no
trusted proxy in front, a client could set that header freely and reset its own
counter on every request. The counter lives
in Django's cache: `cache.add` creates it (with its expiry) only when absent, so
the window starts on the first hit and isn't pushed back by later ones; a later
`cache.incr` tells me how many hits have landed. The check runs **before** the
account is created, so a blocked request creates neither an email nor an
account. No extra dependency — plain Django cache. (In production with multiple
processes the default per-process `LocMemCache` won't share counts, so this
needs a shared backend like Redis — noted under Future improvements.)

---

## Data model

The brief's hierarchy is User → Calendar → Slot → Activity → Interest. Done so
far:

- **User** (`accounts.User`): email (the login), first name, last name. No
  password. The user also carries the calendar's shareable link directly:
  `share_token` (a random, URL-safe string from `secrets.token_urlsafe`) and
  `share_slug` (`first-last-token`). There is no separate Calendar model — see
  the assumption below. The name part of the slug is just for readability; the
  part that makes the link impossible to guess is the random token.

---

## Calendar access & sharing

Opening someone's shared link is what grants access — there's no approval step.
The flow, in short:

- The link is `/calendar/<share_slug>/`, behind `@login_required`. So a visitor
  is always a known, signed-in user (a brand-new person just signs up first,
  then lands back on the link).
- The view looks the owner up by `share_slug`, and the first time a visitor
  opens it, a `CalendarAccess` record is created (`get_or_create`, so re-opening
  never duplicates it). The owner then shows up in the visitor's "Other
  Calendars".
- Opening your *own* link just shows your calendar — no access record, and the
  database's "no self-access" rule backs that up.

Blocking and archiving are reversible flags on that record (each with its own
timestamp); nothing is ever deleted:

- A **visitor** can archive a calendar — it leaves their "Other Calendars" for a
  separate "Archived" section they can restore from. Archiving only *hides* it
  from the list (the brief: it "removes the calendar from their own visible
  list"); it does not revoke access. So the archived entry deliberately has **no
  link to the calendar** — you Restore it first, then open it. The brief says
  nothing about the *direct* share URL, so that link still works for an archived
  calendar; making "archived = not openable even by its link" would be a stricter
  opt-in, but it's beyond what the brief asks, so I left it out.
- An **owner** can block a visitor from their list of visitors.

Both run as POST-only actions (`@require_POST` + CSRF token), and each view
fetches the record scoped to `request.user` — so you can only ever archive your
*own* access, or block a visitor on your *own* calendar; touching anyone else's
relationship gives a 404. The *effect* of blocking — hiding newly created slots
from the blocked user — will land with the slots themselves; for now the flag
and its timestamp are in place.

---

## Slots & activities: the state machine

Slots and activities share four states (Open, Confirmed, Closed, Cancelled),
and confirming or closing one thing automatically updates the others. I keep all
of this logic **in the models** (as `confirm()`, `close()`, `reopen()`,
`cancel()` methods), so views just call a method and the rules live in one
place.

The automatic transitions, straight from the brief:

- **Confirm an activity** → its slot becomes Confirmed, and every *other*
  activity in that slot becomes Cancelled. I cancel the competitors *before*
  confirming the chosen one, so there's never even a brief moment with two
  confirmed activities (which the database constraint would reject).
- **Close the confirmed activity** → its slot becomes Closed. The owner can't
  close a slot directly; a slot only closes as a side effect of its confirmed
  activity closing.
- **Cancel a slot** → all its activities become Cancelled.

The activity and its slot always move together: `confirm`, `close`, and
`reopen` each update both, so the slot never points at an activity in a
contradictory state.

Two edge cases the brief leaves open, and how I resolved them:

- **Reopen.** The brief mentions a closed activity's access being restored "if
  the owner reopens it", but doesn't list a Reopen action. I added `reopen()` as
  the exact inverse of `close()` (activity and slot go Closed → Confirmed) — it
  re-opens the joining gate that closing had shut. Reopening to Confirmed (not
  Open) is deliberate: closing only sealed new joins, it didn't un-select the
  activity, so the inverse shouldn't either.
- **Cancelling the confirmed activity** is refused. The transition table never
  says what happens to a slot if its *confirmed* activity is cancelled, and
  doing it naively would leave the slot Confirmed with nothing confirmed. Since
  "Cancelled" is a terminal state in the brief, I forbid it: `activity.cancel()`
  is only for pruning still-open proposals; to undo a confirmation you cancel
  the whole slot.

**When can you propose activities?** Only while the slot is **Open** — proposing
is the "still deciding" phase. Once an activity is confirmed (the slot becomes
Confirmed), the choice is made, so no new activity can be added; the same holds
once the slot is Closed or Cancelled. This is enforced both in the UI (the
"Propose an activity" button only shows on an Open slot) and in the view (a
direct POST to a non-Open slot is rejected). Cancelling a single *open* activity
is different — it just prunes one proposal and leaves the slot Open, so you can
keep proposing others; only a *confirmation* ends the proposing phase.

**Concurrency.** Confirming touches several rows at once, so each transition runs
in a single transaction (`@transaction.atomic`) — all of it happens, or none of
it. On top of that, `confirm()`/`close()` take a row lock on the parent slot
(`select_for_update`): if two people try to confirm two different activities of
the same slot at the same moment, the second one waits for the first to finish,
so "only one confirmed activity per slot" holds even under load. (SQLite doesn't
do row-level locks, so the lock is a no-op there; it's the real safeguard on
PostgreSQL in production. The database constraint is the backstop either way.)

---

## Expressing interest & visibility

A visitor expresses interest from the shared calendar page. Interest itself is
just the existence of an `Interest` row, so "I'm in" creates one and "Remove
interest" deletes it. The guards on joining:

- You can't express interest in **your own** activity (the brief: interest is in
  *other* users' activities).
- You need an existing **calendar access** to the owner.
- You can only join an **Open or Confirmed** activity — not a Cancelled one, and
  not a Closed one you weren't already in.

**What a visitor sees** (the visibility rules, which are the subtle part):

| Activity status | Visible to a visitor? | Can newly join? |
| --- | --- | --- |
| Open | yes | yes |
| Confirmed | yes | yes (may still join) |
| Cancelled | hidden from everyone | no |
| Closed | only if they **already** expressed interest | no (sealed to newcomers) |

So confirmation hides the *losing* activities from everyone, and closing keeps
the *winning* one visible to those already in but sealed to newcomers — exactly
the brief's two rules. Removing interest from a *closed* activity is a one-way
door (it then disappears for you), so the UI asks for a confirmation first.

**Blocking.** A blocked visitor stops seeing slots created *after* they were
blocked, but keeps the ones they could already see. To tell "new" from "old", a
slot records a `created_at`, which is compared against the access's `blocked_at`.
Nothing is deleted — blocking just narrows what's shown. The same
`created_at` vs `blocked_at` check also guards the *join* path (expressing
interest), not only the display: since activity ids are sequential, hiding a
post-block slot from the page isn't enough — a blocked visitor could otherwise
guess an id and join an activity they shouldn't even see, so `interest_add`
re-checks the block before letting them in.

A few calls the brief left open here (decided and kept simple):

- **Interest rows are never deleted by status changes.** When an activity is
  cancelled or hidden, the interest stays in the database (consistent with the
  brief never deleting data); the activity just becomes invisible.
- **The "are you sure?" before leaving a closed activity** is a lightweight
  browser confirmation, since it's a single yes/no with no extra data to collect.

---

## Assumptions

Calls I made where the brief didn't say:

1. **The shareable link is generated automatically with the user.** The brief
   says one calendar per user, but not when it comes to life. Since the link
   (`share_token` / `share_slug`) lives on the user itself, it is filled in the
   moment the user is saved. It's the same database row, so a user can never
   exist without a calendar link — no extra step, no risk of a half-created
   state.
2. **The name in the calendar link is just for looks.** All the security comes
   from the random token, never the name. Renaming isn't supported (names are
   fixed at sign-up).
3. **Magic links last 30 minutes (a security choice).** The brief doesn't give a
   number, so I picked 30 minutes: long enough to be handy, short enough that an
   old or forwarded link won't keep working. It's a setting, so easy to change.
4. **I clean up email addresses before saving them.** The same inbox can be
   typed different ways (`John@Gmail.com` vs `john@gmail.com`). Since the email
   is both the login and where the magic link goes, I lower-case the domain so
   these count as the same account — otherwise I'd get duplicate users and
   calendars.
5. **I kept the Django admin** as a handy way to inspect data. It's behind a
   password-protected superuser, separate from the passwordless user login.
6. **No separate Calendar model — the link lives on the user.** The brief's
   suggested schema has no Calendar table; it hangs everything off the user, so
   I followed that and kept the shareable link (`share_token` / `share_slug`) as
   two fields on `User`. It's the simplest thing that works and means no extra
   table or join for what is, today, just two fields.

   I did consider a separate `Calendar` model, and it has two real advantages:
   (1) a clean separation — the User stays about *identity* (email, name) while
   the Calendar holds the *shareable agenda*; and (2) room to grow — things like
   regenerating a leaked link, calendar settings, or a sharing audit would have
   a natural home, without touching the user model. For the current scope the
   simplicity wins, but if these features came up, promoting the link into its
   own `Calendar` model is the upgrade path.
7. **Activity design choices (a few calls beyond the brief).**
   - **Participant limit.** I added an optional `max_participants` on each
     activity: blank = no limit, a number caps how many people can express
     interest. It lives on the **activity**, not on the `Interest` relationship
     — the limit is a single attribute of the activity (like its title), while
     `Interest` rows only record *who* joined. "Is it full?" is the count of
     interests compared against that one number, so the limit is stored once and
     can't drift out of sync.
   - **Categories are a fixed code list, not a database table.** The ~20
     categories are a `TextChoices` enum, not a managed `Category` table. The
     list is static and not user-editable, so an enum keeps validation and
     readable labels without an extra table or join. Trade-off: changing the
     list means a code change + migration; if categories ever became
     admin-managed, a table would be the upgrade path.
   - **"One confirmed activity per slot" is enforced in the database.** The
     brief's rule is backed by a conditional `UniqueConstraint` (unique `slot`
     where `status='confirmed'`), so the database itself refuses a second
     confirmed activity — not just the app logic.
   - **Interest is an explicit model, not a plain `ManyToManyField`.** A bare
     many-to-many would auto-create a hidden join table, which is fine for a
     "nude" link. But the brief models Interest as a first-class entity with a
     `createdAt`, and I want room to add fields/logic to the relationship later
     — and the moment you need data *on* the link, a many-to-many needs a
     "through" model anyway, which is exactly this `Interest` class. Interest is
     a simple boolean modelled by the row's existence (a row = interested, no
     row = not interested), with a `unique(user, activity)` constraint so a user
     can be interested at most once per activity.
8. **Two sanity rules on slots the brief leaves implicit.** The brief never
   spells these out, but they keep the data sensible:
   - **A slot must start in the future.** Creating availability for a time that
     has already passed makes no sense, so I reject it at creation. (This is a
     creation-time check only — a slot that *becomes* past is normal and still
     shows for 7 days, as the brief's display rule requires.)
   - **A slot must be shorter than 24 hours.** Availability is "an evening", "an
     afternoon" — not a whole week. I cap the duration; the limit lives in
     `settings.SLOT_MAX_DURATION_HOURS` (a business rule, so it's a named
     setting rather than a magic number or an env secret). Both checks live in
     the model's `clean()` so the form shows a clear message; they're UX rules,
     not data-integrity invariants, so they don't need a database constraint.
9. **When editing (Update) is allowed — and what stays locked.** The brief lists
   `Update` for slots and activities but doesn't say *when* it's permitted, so I
   tied it to the state machine, on one principle: **never let an edit betray
   people who are already counting on something, and never edit a settled state.**
   - **A slot's time is editable only while it's Open.** Once an activity is
     Confirmed, friends have positioned themselves on that time — silently moving
     it would mislead them. Closed/Cancelled are settled, so no edit either. To
     reschedule a confirmed slot, you cancel it and make a new one.
   - **An activity is editable while Open or Confirmed, but not once Closed or
     Cancelled.** A closed activity is sealed and people joined it as-is; a
     cancelled one won't happen. To edit a closed one, the owner uses the
     existing **Reopen** transition first (Closed → Confirmed), which is the
     explicit "un-seal" step — then edits.
   - **A Confirmed activity's category is locked.** Title and description stay
     editable (fixing a typo, adding details), but the *category* is the essence
     of "what we're doing" — people expressed interest **for that category**, so
     turning a confirmed "Tennis" into "Cinema" would be a bait-and-switch. I
     enforce it by disabling the form field (Django then also ignores any value
     smuggled in via POST, so it's a real guard, not just a UI hint).
   - **Two honest limits, both softened by a warning.** (1) On a Confirmed
     activity the title/description stay editable while only the category is
     locked — the intent is *refinement* (e.g. adding "bring your racket"), not
     *redefinition*, though nothing technically stops a misleading rename;
     locking the category (the structural "what") covers the main bait-and-switch
     risk. (2) People can express interest as soon as an activity is Open, so
     editing a slot's time *or* an activity's content can affect those already
     interested — the same concern that locks a *confirmed* slot. Since the app
     has no notifications, I don't block these edits, but **both the slot- and
     activity-edit forms warn the owner** ("N people have already shown
     interest…") and ask for confirmation before saving.

---

## Trade-offs

- **Signed tokens instead of a token table.** Signed tokens need no storage and
  no cleanup, but I can't cancel a single link before it expires. Fine for a
  link that only lives 30 minutes. If I ever needed to revoke links one by one,
  a token table would be the way.
- **No retry if a calendar token collides.** Tokens are unique in the database.
  A clash is astronomically unlikely with 12 random bytes, so I let it raise an
  error rather than add retry code that would basically never run.

---

## Completed features

- Custom passwordless user + its manager.
- A shareable calendar link per user (token + slug), generated automatically and
  impossible to guess.
- **Full magic-link auth**: separate sign-up and sign-in pages, the emailed
  link, token verification, and sign-out. New users sign up in one step;
  returning users just enter their email.
- **Rate limiting on magic-link requests** (per email + per IP, via the cache),
  so the sign-in form can't be used for email bombing or bulk account creation.
- **`SECRET_KEY` read from the environment** (with a dev-only fallback), so the
  key that signs sessions and magic-link tokens never lives in the public repo.
- Sign-in / "check your email" / My Calendar pages (Pico.css), with a sign-out
  button and flash messages.
- SMTP email loaded from a gitignored `.env`.
- **`CalendarAccess` model** linking a visitor to a creator's calendar, with
  independent block/archive flags (each with its own timestamp), a one-record
  per-pair rule, and a "no access to your own calendar" guard — all enforced at
  the database level.
- **Sharing flow**: opening a `/calendar/<slug>/` link auto-grants access; a
  "My Calendar" page listing the calendars you can access (with an archived
  section) and the visitors who can see you.
- **Archive / block actions** (POST-only, CSRF-protected, scoped to the current
  user): a visitor archives/restores a calendar; an owner blocks/unblocks a
  visitor.
- **Availability slots**: create / edit / list / cancel, shown on My Calendar
  (last 7 days + future), with validation (future start, end after start, under
  24h) and a date picker that blocks past dates and end-before-start.
- **Activity suggestions** managed from a slot's page: propose (only while the
  slot is Open), edit, confirm, close, reopen, cancel — driven by the model state
  machine, with status badges and a clean card layout.
- **Expressing interest**: a visitor joins/leaves another user's Open or
  Confirmed activities from the shared calendar, with the full visibility rules
  (cancelled hidden, closed visible only to those already in) and the blocking
  effect (slots created after a block are hidden).
- **Creator Dashboard**: a drill-down (slot → activity → interested users)
  showing only first/last names — never emails (enforced and tested).
- **Consolidated Calendar** ("Agenda"): a **month grid** merging your own slots
  with the visible slots of every calendar you can access (archived excluded,
  blocking respected). The brief describes this view as a compact list whose
  purpose is to "grasp what's happening on a given day without being overwhelmed
  by detail" — I took that goal literally and rendered it as a **calendar-style
  grid** (the bonus UI), since a whole month at a glance serves that purpose even
  better than a list. Each day cell lists its slots compactly as
  `start–end · owner`, with the status shown as a colour and the full
  `start–end · owner · status` in a hover tooltip; clicking a slot opens its
  detail. Slots stay in chronological order within each day.
- All four brief views are in place (My Calendar, Other Calendars, Creator
  Dashboard, Consolidated Calendar).
- Tests across the whole app (76): the two sign-in/sign-up flows (including the
  disposable-email block), the magic-link rate limit (per email and per IP),
  calendar access, slots, activities, editing (Update) with its state-machine
  rules and the confirmed-category lock, the state machine, interest (including
  that blocking guards the join path, not just the display), visibility,
  dashboard privacy, and the consolidated view.
  - **Mostly integration tests**: they drive real requests through Django's test
    client (URL → view → form → ORM → rendered HTML) — e.g. posting the sign-in
    form and following the emailed link, expressing interest and checking both
    the database and what the page shows, or asserting an email never appears in
    the dashboard's HTML.
  - **Plus unit tests** for the pieces worth testing in isolation: the model
    state machine (`confirm`/`close`/`reopen`/`cancel` called directly) and the
    magic-link token (`make`/`read_login_token`).
  - No browser/end-to-end tests (Selenium/Playwright) — out of scope; the test
    client covers the request/response layer without a real browser.
- Users, calendar-access records, slots, activities, and interests all show up
  in the Django admin.

---

## Omitted features

The core flow and all four views are done; what's left is deliberately scoped
out for now:

- **Capacity enforcement** (`max_participants`). The field exists but isn't
  enforced yet — see Future improvements.
- **Full mobile polish.** The Agenda already uses a calendar-style month grid
  (with a small-screen breakpoint), but I didn't do a thorough mobile-first pass
  across every page — a bonus, not core.

---

## Future improvements

- **Enforce the `max_participants` capacity.** The field exists on the activity;
  enforce it by treating "full" as a derived condition (interest count vs. the
  limit) — block new interest when full, but leave the activity Confirmed and
  never auto-close it, keeping capacity orthogonal to status.
- **Notify interested users on changes.** Right now, editing a slot or activity
  that people are interested in only *warns the owner* (the app has no
  notifications). The natural next step is to actually notify the interested
  users — e.g. email them when a slot they're in is rescheduled, or an activity
  they joined is edited or cancelled — turning today's owner-side warning into a
  real heads-up for the people affected.
- More tests, especially around the visibility rules and concurrency.
- Move `DEBUG` (and `ALLOWED_HOSTS`) into the `.env` too, and add the
  HTTPS-only cookie / HSTS settings for production. (`SECRET_KEY` already comes
  from the environment.)
- Cancel links one by one (a token table) if it's ever needed.
- **A shared cache backend (e.g. Redis) for the magic-link rate limit.** The
  default `LocMemCache` is per-process, so with several workers each keeps its
  own counter and the real limit becomes `workers × MAGIC_LINK_RATE_LIMIT`. Fine
  for the single-process dev server; production needs a shared backend.
- A nicer calendar-style UI that works well on mobile.
- Docker for easy deployment.
