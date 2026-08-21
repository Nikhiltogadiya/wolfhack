# Redesign: both sides, walked step by step

Written by walking each journey as the person living it, not as the person who built it.

---

## Recruiter — Maya, a talent partner with more roles than hours

### Step 1 · She opens the site for the first time
**Now:** "Hiring overview", four zeroed stat tiles, an empty state with two buttons.
**Breaks:** She is never told what this is or why it differs from the ATS she already hates.
The actual thesis — *ranks on evidence, not prose; flags but never rejects* — is a paragraph in
a sidebar she will not read.
**Fix:** A first-run screen that says the idea in one line and shows the three things it does.
One primary action: create a role. One secondary: show me with sample data.

### Step 2 · She creates a role
**Now:** One long form. Title, a big textarea, then "Internal criteria" with a dropdown of
eleven developer field names (`start_availability`, `mentoring_capacity`).
**Breaks:**
- "Internal criteria" is our word, not hers. She does not know what it means or why she wants it.
- She pastes an advert and presses Create **having seen nothing of what we extracted**. The
  first time she learns what we understood is after the role exists.
- Everything at once: advert, private preferences, and no CVs.
**Fix:** Three steps, each with a visible result.
1. **The advert** → we parse it → *show her the requirements we found*, editable, before she commits.
2. **Private preferences** → renamed from "internal criteria", explained in her words, with the
   guard live as she types.
3. **Add CVs** → drag and drop → create and start processing in one move.

### Step 3 · She uploads CVs
**Now:** A small "+ Upload CVs" button. No drag and drop, no formats listed, then a 1–3 minute
wait with a spinner.
**Fix:** Drop zone, accepted formats stated, per-file progress, and the ranking usable while
the rest process.

### Step 4 · She reads the ranking
**Now:** Six columns. Four of them are scores whose meaning is nowhere on the page.
**Breaks:**
- A new user cannot know what "CV bluff risk: NOT CORROBORATED" means, and it sounds like an
  accusation.
- No sort, no filter, no search.
- **No way to compare two candidates side by side** — which is the product's entire argument.
- The internal-JD toggle's effect is invisible until pressed.
**Fix:** A one-time explainer for the four scores. Sort on any column. Filters for the three
things she actually wants (needs review, top fit, waiting on the candidate). And a **compare
view**: tick two, see them side by side, requirement by requirement.

### Step 5 · She opens a candidate
**Now:** A dense page with everything at equal weight.
**Breaks:** No hierarchy and no next action. She has to decide what to do from a wall of evidence.
**Fix:** A decision bar at the top — Shortlist / Ask questions / Pass — then a short summary,
then evidence on demand.

### Step 6 · She decides
**Now:** She can only pass. There is no shortlist, no stage, no progression.
**Breaks:** The product models rejection and nothing else. Real pipelines move people forward.
**Fix:** Stages: New → Reviewing → Questions sent → Shortlisted / Passed. Set from one control.

### Step 7 · She wants the candidate to answer
**Now:** She copies a URL by hand from a detail page.
**Fix:** "Ask questions" sets the stage, shows exactly what the candidate will see, and gives
her a copyable link and a ready-written message.

---

## Candidate — applied, waiting, anxious

### Step 1 · The link reaches them
**Now:** There is no mechanism. The recruiter copies a URL.
**Fix:** Covered by Step 7 above.

### Step 2 · They open it
**Now:** Six sections at once — status, consent, evidence, flags, questions, job ad.
**Breaks:**
- **No sense of what to do.** Everything has equal weight.
- Consent comes second, before they have any reason to care.
- "Things we noticed and want to ask you about" lands before the questions that explain it.
- The questions — the only thing they can actually *do* — are near the bottom.
**Fix:** One clear task, above everything: *answer the questions*. Then transparency. Consent
moves down to where it is relevant, and gets a plain-language reason.

### Step 3 · They answer
**Now:** Six textareas, one shot, no draft.
**Breaks:** No sense of length, no saving, and closing the tab loses everything.
**Fix:** Progress ("2 of 5"), drafts saved locally as they type, and a confirmation afterwards
that says what happens next.

---

## What is actually being built

| # | Item | Side |
|---|---|---|
| R1 | First-run screen explaining the product | recruiter |
| R2 | Role creation as three steps, with a requirements preview | recruiter |
| R3 | Drag-and-drop upload, formats stated, per-file progress | recruiter |
| R4 | Dismissible explainer for the four scores | recruiter |
| R5 | Sort and filter on the ranking | recruiter |
| R6 | **Compare two candidates side by side** | recruiter |
| R7 | Decision bar: Shortlist / Ask questions / Pass | recruiter |
| R8 | Stages, and progression not just rejection | recruiter |
| R9 | "Ask questions" produces a link and a written message | recruiter |
| C1 | One clear task at the top of the portal | candidate |
| C2 | Reorder: action first, then transparency, then consent | candidate |
| C3 | Answer progress, local drafts, confirmation | candidate |

## Principles held throughout

- **Nothing gains a control that does nothing.** Three times now a decorative element has
  shipped — a consent toggle, two buttons — and each one undermined the exact claim it sat next
  to. Every new control does something or is not added.
- **Plain words over ours.** "Private preferences", not "internal criteria". "Claims we could
  not verify", not "bluff risk" where a candidate can see it.
- **The candidate never sees a number.** Evidence and questions, yes. A score they could
  optimise against, no.
