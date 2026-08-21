# The missing half: how a candidate gets in

Found by opening the site as a candidate instead of curling it.

## What I saw

I landed on `/` and was looking at **the recruiter's dashboard**. Four other applicants by
name, their fit scores, who needs review. Every recruiter page answered 200 with no
credentials: I could open `/role/demo/c/priya_raman` and read another applicant's evidence,
their flags, and the questions being asked of them.

Then I looked for a way to apply. There is none. `/jobs`, `/apply`, `/careers` are all 404.
The only candidate surface needs a secret token the recruiter has to send by hand.

So the product has no candidate entry at all, and leaks every applicant's file to anyone with
the URL. For something the challenge calls a *marketplace*, that is the whole missing half.

## What has to exist

### A. Two surfaces, actually separated
The recruiter dashboard cannot be the front door.

- `/` and `/jobs/*` — public, for candidates
- `/hiring/*` — the recruiter side, behind a gate

The gate is a shared team passcode in `FIT_HAPPENS_TEAM_PASSCODE`, held in a signed cookie.
**This is not production auth and is not pretending to be** — real deployment needs per-user
accounts, SSO and an audit of who viewed which application. It is enough to stop a candidate
walking into the hiring team's dashboard, which is the actual defect.

### B. A candidate can find work
1. `/` — open roles, searchable, with the honest things we know: how specific the advert is,
   and what it does not tell you.
2. `/jobs/{slug}` — the advert itself, what we look for, and **our own clarity critique of it**.
   Nobody else shows a candidate that the advert they are reading is vague.

### C. A candidate can apply
3. `/jobs/{slug}/apply` — name, email, CV. That is all.
4. On submit: we process it, and hand them **their own private link** immediately, with the
   evidence we read and any questions. No waiting in silence, which is the thing candidates
   hate most and the thing the VW board also singled out.

### D. A candidate can come back
5. `/track` — "I applied before". Enter the email, get the link again. A link in an email
   people lose is not a system of record.

### E. Names
Uploaded CVs are currently named after the file, so an applicant shows in the dashboard as
`15118506`. An application carries a name and an email, because a person applied rather than a
file being processed.

## Order

| # | Item |
|---|---|
| 1 | Move the recruiter surface to `/hiring`, behind a passcode gate |
| 2 | Public job board at `/` |
| 3 | Job detail with the advert and our clarity read |
| 4 | Apply: name, email, CV → their private link |
| 5 | `/track` to recover a lost link |
| 6 | Applications carry a real name, not a filename |
