# FlexTime — Full-Stack Technical Assignment

A shared availability & activity coordination platform.

---

## The scenario

Imagine you have a hundred friends and, most evenings, you'd like to do
*something* with *someone* — tennis, a coffee, a movie, a board-game night.
The problem is you never know who is free or what they feel like doing, and you
are not going to message a hundred people every single day.

**FlexTime** solves this. You publish a calendar of the time slots when you are
available, and for each slot you propose one or more activities. You share a
single private link with your friends (over WhatsApp, email, anywhere). They
open it, see your availability, and tell you which activities they're interested
in. Everything else happens offline.

Your task is to build this product end-to-end.

---

## What you will build

A web application that lets a user:

- Manage their own **availability calendar**.
- Propose **activities** during their available time slots.
- Share their calendar with other users via a private link.
- Browse calendars that others have shared with them.
- **Express interest** in activities proposed by others.
- Coordinate activities through a simple, intuitive interface.

The full functional brief — domain model, business rules, statuses, views, and
API — lives in **[specifications.md](specifications.md)**. Read it carefully; it
is the source of truth for *what* to build.

---

## What we are evaluating

This is a deliberately open-ended, scenario-based assignment that mirrors
real-world work. We are interested not only in *what* you build, but in *how*
you decide what to build. We will look at:

- **Product thinking** — turning business needs into a working product.
- **Handling ambiguity** — making and documenting reasonable assumptions.
- **Full-stack architecture** — backend, frontend, and the seams between them.
- **Data modeling** — translating the domain into a clean schema.
- **API design** — clear, consistent, RESTful endpoints.
- **Authentication & authorization** — a passwordless flow and correct access control.
- **Frontend UX/UI** — usable, sensible interfaces and workflows.
- **Code quality & maintainability.**
- **Documentation & testing strategy.**

> A smaller but well-designed solution is strongly preferred over a larger but
> poorly structured one.

---

## Working with ambiguity

This specification focuses on the core business requirements. As in any real
project, **some requirements are intentionally left unspecified** — screens,
edge cases, validation rules, and minor workflows.

You are expected to:

- make reasonable assumptions and use your own product and UX judgment,
- design sensible workflows and handle edge cases appropriately,
- and **document the important assumptions** in your project README.

Part of the evaluation is seeing how you transform high-level requirements into
a coherent, working product — and how you decide what *not* to build.

---

## Technical requirements

| Layer        | Choice                                                |
| ------------ | ----------------------------------------------------- |
| **Backend**  | **Django** — mandatory.                               |
| **Frontend** | Django Templates (DTL) — *preferred* — or React.      |
| **Database** | SQLite or PostgreSQL.                                 |
| **API**      | Only needed for a decoupled frontend. See note below. |

> **About the API:** if you build a full-stack Django app with DTL templates,
> you do **not** need a separate REST API — plain Django URLs and views are
> enough. A REST API is only expected if you decouple the frontend (e.g. React).
> See [specifications.md](specifications.md#api-requirements).

You may use any other modern, well-justified libraries on top of this.

### Security expectations

Reasonable security practices are expected. In particular:

- Calendar URLs must **not be enumerable**.
- A user may only access a calendar through a valid shared URL or an existing
  Calendar Access relationship.

---

## Getting started

Start by **cloning this repository and making it your own**, so the assignment
docs travel with your code. There is no starter application — you build the
Django project yourself.

1. Clone this repo, rename it as `flextime-<your-name>`, and point it at a new public repo of your own
   (see **[SUBMISSION.md](SUBMISSION.md)** for the exact steps).
2. Scaffold a Django project inside it and commit early and often.
3. Build toward the brief in **[specifications.md](specifications.md)**,
   prioritizing the core flow first.
4. Document your decisions in a `SOLUTION.md` (see SUBMISSION.md).

---

## Expected effort and timeline

This assignment is intentionally **larger than most candidates can fully
complete** in the time available. We estimate roughly **10–20 hours of work**,
to be submitted within **one week**. If you need more time, just ask for an
extension.

You are **not** expected to implement every feature. The goal is not to measure
hours invested, but to evaluate technical skill, prioritization, product
thinking, and implementation quality. We encourage you to:

- prioritize the important functionality first,
- make reasonable assumptions and document your trade-offs,
- and clearly explain what you completed, what you left out, and what you would
  build next.

---

## Documentation

- **[specifications.md](specifications.md)** — the full functional brief.
- **[SUBMISSION.md](SUBMISSION.md)** — how to set up your repo and submit.

When you submit, add a `SOLUTION.md` (or a marked section in the README)
explaining your architecture decisions, assumptions, trade-offs, completed and
omitted features, and future improvements.
