# Plan: the candidate side

## Why this is one build, not four

The four gaps look separate. They are not:

- **User-controlled sharing** needs a place the candidate can say yes or no.
- **CP3 response scan** needs the candidate to actually answer something.
- **Candidate transparency** needs somewhere to show them what we hold.

All three need the same missing thing: **a surface the candidate logs into.** Build that once
and three gaps close together. It also turns the product into the two-sided marketplace the
challenge asks for, rather than an employer tool with a candidate story attached.

## The candidate surface

A tokenised link, no account. `/apply/{token}` - the recruiter's system would email it. Five
things live there, in order of how much they matter to the judging rubric:

### C1. Consent - "what may we look at?" (closes Responsible AI 6/6)
Toggles, default OFF for everything except the CV they submitted:
- the CV they sent (always on - they sent it)
- public GitHub, if a handle is on the CV
- publications and conference talks
- professional community activity

Nothing is fetched before the toggle is on. Turning one off deletes what was fetched under it
and removes it from the recruiter's view. The audit trail records every change, with a time.

**This is the sixth Responsible-AI bullet, the only one we currently fail.** It is also the
cheapest of the four to build, and the most defensible on stage: *the candidate decides, and
here is the record of what they decided.*

### C2. Status - "where am I?" (the transparency pain)
What stage, what happens next, and by when. Today a candidate applies into silence; this is
the moment the VW board also calls out, and it costs almost nothing because we already hold
every timestamp in the audit trail.

### C3. Your evidence - "what did they see?" (transparency + fairness)
The same skill-to-role map the recruiter sees, from the candidate's side: which requirements
we found evidence for, which we did not, and the exact lines we read it from. If we got
something wrong, they can see that we got it wrong.

Deliberately NOT shown: the fit score itself, and any slop or authenticity flag. Showing a
number invites gaming; showing an unconfirmed flag is an accusation. They see the evidence,
not the verdict.

### C4. Answer the questions -> feeds CP3
The follow-up questions we already generate, answerable inline. Their answers become CP3's
input, which is what "Response authenticity - PENDING" has been waiting for.

### C5. About this role - partial credit on the candidate pains
The job-ad clarity score we already compute, shown to the candidate: what this advert does not
tell you (no salary band, no team size, no reporting line). Honest, already built, and it is
the only candidate pain we can answer without pulling external employer data.

## CP3 - response scan

Runs the same two checks on the candidate's answers, plus one that only exists here:

1. **Style** - the same CP1 patterns. Same caveats, same refusal to flag on style alone. Our
   own calibration says this signal is weak; it stays advisory.
2. **Consistency with the CV** - this is the real signal, and it is deterministic. The answer
   is checked against the claims we already extracted: a date that contradicts the employment
   history, a duration that contradicts a stated one, a technology that predates its release.
   `check_claims` from ai-CV-cover-letter fits natively here, because CP3 finally gives us the
   two-document pair its contract needs (answers vs CV) - the thing it lacked recruiter-side.
3. **Style consistency** - from the whiteboard: the deliberately casual question fingerprints
   how they actually write, and the polished answers are compared against that baseline.
   Cheap, and it is the only place the "off-guard voice" idea has ever had somewhere to live.

Same rules as everywhere: flag for human review is the ceiling, two independent flags before
anything is called likely fabricated, style alone is never enough.

## Publications and community evidence

Only if it stays cheap. **OpenAlex** (free, no key, no rate limit worth worrying about)
resolves an author name to publications with dates and venues. That is a real, verifiable
external signal and it fits the existing three-state model exactly: corroborated / unsupported
/ undersold. Anything requiring a scraped or paid source is out.

Gated behind the C1 consent toggle, like everything else external.

## Order of work

Built in this order deliberately, so that whenever we stop, the most valuable thing is done:

| # | Item | Closes | Rough cost |
|---|---|---|---|
| 1 | C1 consent + audit | Responsible AI 6/6 | small |
| 2 | CP3 response scan + C4 answers | the empty 4th column | medium |
| 3 | C2 status + C3 evidence | candidate transparency | medium |
| 4 | C5 about this role | one candidate pain | small |
| 5 | Publications via OpenAlex | "CVs miss publications" | small-medium |

## What stays out, and why

**Employer research aggregation** - Glassdoor-style reviews, financial performance, news.
This is the "fragmented signals" pain and it needs paid or scraped sources we do not have.
Saying so is better than a fake version of it.

**Role discovery across postings** - "blind discovery" needs a corpus of live job ads. We have
one JD. A near-duplicate detector over one posting is theatre.
