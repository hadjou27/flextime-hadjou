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

# 4. Apply migrations
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

There are two flows, like the brief asks:

- **New user:** gives first name, last name, email → the account is created
  (its shareable calendar link is generated at the same time) → a magic link is
  emailed.
- **Coming back, logged out:** gives just the email → a fresh magic link is
  emailed. No new account.

**Sending you back where you came from.** If you click a shared calendar link
while logged out, `@login_required` sends you to sign-in with a `?next=` URL
(Django's standard mechanism). The magic-link email doesn't carry that `next`,
so I stash it in the session and, after the link is verified, redirect you to
it — back to the calendar you originally clicked. The target is checked with
`url_has_allowed_host_and_scheme` (against the current host) so it can only ever
be a page on our own site, never an outside redirect.

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

- A **visitor** can archive a calendar (it drops out of their "Other Calendars",
  into a collapsible "Archived" section they can restore from).
- An **owner** can block a visitor from their list of visitors.

Both run as POST-only actions (`@require_POST` + CSRF token), and each view
fetches the record scoped to `request.user` — so you can only ever archive your
*own* access, or block a visitor on your *own* calendar; touching anyone else's
relationship gives a 404. The *effect* of blocking — hiding newly created slots
from the blocked user — will land with the slots themselves; for now the flag
and its timestamp are in place.

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
- **Full magic-link auth**: sign-up/sign-in form, the emailed link, token
  verification, and sign-out. New users sign up in one step; returning users
  just enter their email.
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
- Tests for the sign-in flow and for calendar access (auto-grant, no duplicate,
  own-link, 404s, archive/block, POST-only).
- Users and calendar-access records show up in the Django admin.

---

## Omitted features

These are left out **for now**, on purpose. I prioritized the foundations
(auth, user, access relationship) first, as the brief suggests, so the parts
above are solid before adding more.

- **Slots, activities, interest, and the status rules.** This is the core
  domain and the most involved part (the automatic status transitions need
  care). I'm building it next rather than rushing it half-done.
- **Blocking's effect on slot visibility.** The block flag and the action exist,
  but actually hiding newly created slots from a blocked user only matters once
  slots exist — so it ships with them.
- **The remaining calendar pages** (My Calendar contents, Consolidated view,
  Creator Dashboard). Left until the slots/activities exist, since there'd be
  nothing to show without them.
- **A calendar-style (grid) UI and full mobile polish.** A bonus, not core, so
  it waits until the functionality is in place.

---

## Future improvements

- The core flow: slots → activities → interest, with the status rules.
- Calendar access (sharing/archiving/blocking) and the visitor pages.
- More tests, especially for the status rules and the access rules.
- Move `SECRET_KEY` (and `DEBUG`) into the `.env` too, instead of hard-coding
  them in settings — fine for local dev, not for production.
- Cancel links one by one (a token table) if it's ever needed.
- A nicer calendar-style UI that works well on mobile.
- Docker for easy deployment.
