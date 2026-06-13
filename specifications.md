# FlexTime — Functional Specifications

This document is the functional brief for the **FlexTime** assignment: a shared
availability & activity coordination platform. For the overview, evaluation
criteria, tech requirements, and timeline, see **[README.md](README.md)**. For
how to set up your repository and submit, see **[SUBMISSION.md](SUBMISSION.md)**.

This brief describes *what* to build. It does not prescribe every screen,
workflow, validation rule, or edge case — those are yours to design and to
document.

---

## Table of contents

- [Core concept](#core-concept)
- [Users & authentication](#users--authentication)
- [Calendars & sharing](#calendars--sharing)
- [Calendar access](#calendar-access)
- [Visibility management: archiving & blocking](#visibility-management-archiving--blocking)
- [Availability slots](#availability-slots)
- [Activity suggestions](#activity-suggestions)
- [Activity categories](#activity-categories)
- [Statuses & state transitions](#statuses--state-transitions)
- [Expressing interest](#expressing-interest)
- [Visibility rules](#visibility-rules)
- [Privacy rules](#privacy-rules)
- [Views](#views)
- [Suggested data model](#suggested-data-model)
- [API requirements](#api-requirements)
- [Security expectations](#security-expectations)

---

## Core concept

The model has a clean, four-level hierarchy. Each level answers a different
question:

```
User
 └─ Calendar                  (each user owns exactly one)
     └─ Availability Slot      → "When am I available?"
         └─ Activity Suggestion → "What could we do during that time?"
             └─ Interest        → "Who wants to do that activity?"
```

Keeping these concerns separate is central to the design and strongly
influences the schema, the API, and the frontend:

- A **slot** is just a container of time. It carries no category, title,
  description, or interest of its own.
- An **activity** carries all the semantic content (category, title,
  description) and is the thing users express interest in.
- An **interest** is a single user's "I'm in" for a single activity.

---

## Users & authentication

There is only **one type of user**. Every user can manage their own calendar,
browse calendars shared with them, and express interest in others' activities.

**Required fields:** First Name, Last Name, Email Address.

Authentication must be **passwordless**. The implementation is left to you, but
it should support the following flows:

- **New user** — identifies themselves once with first name, last name, and
  email, and is signed in via an email link (e.g. a magic link / one-time login
  link / email verification link).
- **Returning user who is signed out** — can request a fresh sign-in link by
  email; no password is ever involved.

Examples of acceptable mechanisms: magic links, one-time login links, email
verification links.

---

## Calendars & sharing

Each user owns **exactly one** calendar.

Each calendar has a single **shareable URL** that grants access to *all* of the
owner's availability slots. (Finer-grained or per-audience links are explicitly
out of scope for this version.)

The URL contains the owner's first name, last name, and a **sufficiently random
token**, for example:

```
/calendar/john-smith-c8d3f7a1b2
```

The random token makes the URL **effectively unlisted** — it must not be
possible to discover a calendar by guessing names or URLs. Users are expected to
share their calendar URL outside the application (WhatsApp, email, etc.).

---

## Calendar access

When **User B** opens **User A**'s calendar URL:

- access is **automatically granted** — there is no approval workflow,
- a **Calendar Access** record is created linking the two users,
- and User A then appears in User B's list of accessible calendars.

---

## Visibility management: archiving & blocking

### Archiving (visitor → calendar)

A visitor may **archive** a calendar they have access to. Archiving:

- removes the calendar from *their own* visible list,
- does **not** notify the owner,
- and preserves all historical records.

### Blocking (owner → visitor)

A calendar owner may **block** a visitor. Blocking:

- is **silent** — the blocked user is not notified,
- preserves all historical records,
- and means the blocked user **no longer sees newly created availability slots**.
  (Historical data they could already see remains preserved.)

Both archiving and blocking are reversible state changes on the Calendar Access
relationship; they never delete data.

---

## Availability slots

An availability slot represents a period of time during which the owner is
available. A slot is **only** a container of time plus a status:

- Owner
- Start Date/Time
- End Date/Time
- Status

A slot **does not** carry a category, title, description, or interest — those
belong to its activity suggestions. A slot acts as a **container for one or more
activity suggestions**.

**Example**

> Owner: John Smith · Start: Saturday 14:00 · End: Saturday 18:00 · Status: Open

---

## Activity suggestions

An activity suggestion is a possible activity that could take place during a
slot. Each one contains:

- Category
- Title
- Description
- Status

**Example**

> Category: Tennis · Title: Friendly Tennis Match
> Description: Looking for one or two players for a casual match. · Status: Open

Participant interest is attached to **activities**, never to slots.

---

## Activity categories

Provide a predefined list of **approximately twenty** categories. Suggested set:

Tennis · Running · Hiking · Cycling · Swimming · Football · Basketball · Yoga ·
Fitness · Board Games · Video Games · Cinema · Museum · Restaurant · Coffee ·
Drinks · Language Exchange · Networking · Volunteering · Other

---

## Statuses & state transitions

Both slots and activities use the same four-state vocabulary. Their meanings
differ slightly, and the two are linked by automatic transitions.

### Slot status

| Status        | Meaning                                                          |
| ------------- | ---------------------------------------------------------------- |
| **Open**      | No activity selected yet. Users may express interest.            |
| **Confirmed** | One activity has been selected. Users may still express interest.|
| **Closed**    | The confirmed activity is happening but no longer accepts new participants. |
| **Cancelled** | Nothing will happen during this time slot.                       |

### Activity status

| Status        | Meaning                                                          |
| ------------- | ---------------------------------------------------------------- |
| **Open**      | Under consideration. Users may express interest.                 |
| **Confirmed** | Selected for the slot. Users may still express interest.         |
| **Closed**    | Confirmed but no longer accepts new participants.                |
| **Cancelled** | Will not happen.                                                 |

### Selection rule

A slot may hold multiple activity suggestions, but **only one activity may be
Confirmed**.

- ✅ Valid: Tennis → Confirmed, Running → Cancelled, Coffee → Cancelled
- ❌ Invalid: Tennis → Confirmed, Running → Confirmed

### Automatic transitions

| When…                                  | Then…                                          |
| -------------------------------------- | ---------------------------------------------- |
| an activity becomes **Confirmed**      | the parent slot becomes **Confirmed**, **and every other activity in that slot becomes Cancelled** |
| a confirmed activity becomes **Closed**| the parent slot becomes **Closed**             |
| a slot becomes **Cancelled**           | all activities in the slot become **Cancelled**|

So confirming one activity resolves the whole slot in a single step: the chosen
activity and its slot become Confirmed, and the competing activities are
automatically Cancelled (the same end state as the [selection rule](#selection-rule)
example above, reached automatically rather than by hand).

The owner **may not directly close a slot**. A slot becomes Closed only as a
side effect of its confirmed activity becoming Closed.

---

## Expressing interest

Users may express interest in activities belonging to *other* users. Interest is
a simple boolean — **Interested** / **Not Interested**.

A user may express interest in multiple activities and across multiple slots,
but **only once per activity**.

---

## Visibility rules

These two rules govern which activities a visitor can see. They apply to
*different* activities, so read them together:

### On confirmation — non-selected activities disappear

When an activity in a slot is **Confirmed**, every other activity in that slot
is automatically **Cancelled** (see [automatic transitions](#automatic-transitions)).
As a result:

- the confirmed activity remains visible,
- **all the now-cancelled activities become hidden** — even to users who had
  expressed interest in them.

> Before: Tennis, Running, Coffee → After Tennis is confirmed: only **Tennis**
> is visible; Running and Coffee are hidden.

### On closing — the confirmed activity stays visible to those already in

When the **confirmed** activity becomes **Closed**:

- users who **previously expressed interest** can still see it and can still
  remove their interest,
- **new users cannot see it** and cannot join.

If an already-interested user goes to remove their interest in a closed
activity, show a warning first, e.g.:

> "This activity is closed. If you remove your interest, you will no longer have
> access to it."

After removal, the activity becomes hidden for that user and access cannot be
restored unless the owner reopens it.

> **In short:** confirmation hides the *losing* activities from everyone;
> closing keeps the *winning* activity visible to those already in, but seals it
> to newcomers.

---

## Privacy rules

Users may see other users' **first name** and **last name**.

Users may **not** see other users' **email addresses** — emails are used only
for authentication.

---

## Views

All calendar views — **My Calendar**, **Other Calendars**, and the
**Consolidated Calendar** — list slots in **chronological order** and show only
the **last 7 days plus all future dates**. Older slots are not displayed.

### My Calendar

Lets the owner manage their availability slots, activities, participant
interest, and calendar access.

### Other Calendars

Lets a user browse the calendars they have access to, archive a calendar, and
view another user's calendar.

### Consolidated Calendar

A single view combining the user's **own** slots with the **visible** slots from
calendars they have access to. Slots appear in a **compact format**, for example:

> owner name · date · start time · end time · slot status

The detailed view is shown only when a slot is selected. The purpose is to let
users quickly grasp what is happening on a given day without being overwhelmed
by detail.

### Creator Dashboard

Lets the owner drill down:

```
Availability Slot
 └─ Activity
     └─ Interested Users   (First Name, Last Name only — never email)
```

---

## Suggested data model

This is a suggestion, not a mandate — adapt it as your design requires.

### User
`id` · `firstName` · `lastName` · `email`

### CalendarAccess
`creatorUserId` · `visitorUserId` · `blockedByCreator` · `archivedByVisitor` ·
`firstAccessedAt` · `blockedAt` · `archivedAt`

> `blockedByCreator` and `archivedByVisitor` are two **independent booleans**: a
> visitor can archive a relationship the owner has not blocked, and an owner can
> block a visitor who has not archived. Each flag has its own timestamp
> (`blockedAt`, `archivedAt`).

### AvailabilitySlot
`id` · `ownerUserId` · `startDateTime` · `endDateTime` · `status`

### ActivitySuggestion
`id` · `slotId` · `category` · `title` · `description` · `status`

### Interest
`userId` · `activityId` · `createdAt`

---

## API requirements

A REST API is **only required if you build a decoupled frontend** (e.g. React).
If you build a full-stack Django app with DTL templates, you do **not** need a
separate REST API — plain Django URLs and views are sufficient.

Whichever path you choose, the same operations need to exist. The list below is
phrased as REST endpoints; map them onto Django views as appropriate:

**Authentication** — Sign In · Verify Token · Sign Out

**Calendar Access** — Get Accessible Calendars · Archive Calendar · Block User

**Availability Slots** — Create · Update · Cancel · List

**Activities** — Create · Update · Confirm · Close · Cancel

**Interest** — Add Interest · Remove Interest · List Interested Users

---

## Security expectations

Reasonable security practices are expected. In particular:

- Calendar URLs must **not be enumerable** (hence the random token).
- A user may only access a calendar through a **valid shared URL** or an
  **existing Calendar Access relationship**.
- Email addresses must never be exposed to other users through the API or UI.

---

## Bonus points

Optional enhancements, in no particular order:

- A calendar-style UI.
- Mobile-first, responsive design.
- Automated tests.
- Docker-based deployment.
- An audit trail of state changes.
- Advanced filtering.
- Email-based magic-link authentication (fully wired up).
