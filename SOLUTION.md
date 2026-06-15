# FlexTime — Solution

My notes on how I built FlexTime: the choices I made, the assumptions I took
where the brief stayed quiet, the trade-offs, and what's done versus still to
do. The assignment itself is in [README.md](README.md) and
[specifications.md](specifications.md).

>  Still in progress — I update this file as I go.

---

## How to run it

> _I'll finalize this once the app runs end-to-end._

```bash
# 1. Create and activate a virtual environment
python -m venv venv
source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt   # (requirements file to be added)

# 3. Apply migrations
python manage.py migrate

# 4. (Optional) create an admin account to look at the data
python manage.py createsuperuser

# 5. Start the dev server
python manage.py runserver
```

**Email setup (magic links).** Sign-in emails go out over SMTP. You set it up
with environment variables:

| Variable | What it's for |
| --- | --- |
| `EMAIL_HOST` | SMTP server host |
| `EMAIL_PORT` | SMTP port (default `587`) |
| `EMAIL_HOST_USER` | SMTP username |
| `EMAIL_HOST_PASSWORD` | SMTP password |
| `EMAIL_USE_TLS` | `true`/`false` (default `true`) |
| `DEFAULT_FROM_EMAIL` | The "from" address on sign-in emails |
| `SITE_URL` | Base URL used to build the magic links |

---

## Main choices

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

## Done so far

- Custom passwordless user + its manager.
- A shareable calendar link per user (token + slug), generated automatically and
  impossible to guess.
- Users show up in the Django admin, with their share link visible.

---

## Not done yet

- The magic-link login/logout pages and emails.
- Slots, activities, interest, and the status rules between them.
- Calendar access: sharing, archiving, blocking.
- The calendar pages (My Calendar, Other Calendars, Consolidated, Dashboard).
- Tests.

---

## What I'd do next

- Tests, especially for the status rules and the access rules.
- Cancel links one by one (a token table) if it's ever needed.
- A nicer calendar-style UI that works well on mobile.
- Docker for easy deployment.
