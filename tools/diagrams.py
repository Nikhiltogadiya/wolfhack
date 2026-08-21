"""Generate the architecture diagrams as PNGs.

PNG rather than inline Mermaid/SVG because many markdown viewers render neither. Every box is
written to be readable on its own - no bare module names, no acronyms without their meaning -
so the diagram can be understood without the prose underneath it.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

OUT = Path("doc/diagrams")

FOREST, FOREST_MID, FOREST_PALE = "#12402F", "#1C6B4A", "#EAF2ED"
CREAM, CREAM_DEEP, HAIR = "#FAF9F5", "#F3F1EA", "#D9D5CB"
INK, MUTED = "#1B1B19", "#6F6C64"
AMBER_PALE, AMBER_LINE, AMBER_INK = "#FEF6E7", "#E0A93B", "#8A5A08"
ROSE_PALE, ROSE_LINE, ROSE_INK = "#FDF0F3", "#E0919F", "#9F1239"
BLUE_PALE, BLUE_LINE, BLUE_INK = "#EEF5FB", "#9CC0DE", "#1F4E70"

FONT = "DejaVu Sans"

HEAD = f'''digraph {{
  bgcolor="{CREAM}";
  fontname="{FONT}";
  node [fontname="{FONT}", shape=box, style="rounded,filled", penwidth=1.4,
        fontsize=11, margin="0.20,0.13", color="{HAIR}", fillcolor="white", fontcolor="{INK}"];
  edge [fontname="{FONT}", fontsize=9.5, color="{MUTED}", penwidth=1.2,
        arrowsize=0.75, fontcolor="{MUTED}"];
'''


def render(name: str, body: str, *, rankdir="TB", size=None, ratio=None) -> Path:
    attrs = f'  rankdir={rankdir};\n  nodesep=0.34;\n  ranksep=0.46;\n'
    if size:
        attrs += f'  size="{size}";\n'
    if ratio:
        attrs += f'  ratio={ratio};\n'
    src = HEAD + attrs + body + "}\n"
    dot = OUT / f"{name}.dot"
    png = OUT / f"{name}.png"
    dot.write_text(src)
    subprocess.run(["dot", "-Tpng", "-Gdpi=170", str(dot), "-o", str(png)], check=True)
    dot.unlink()
    return png


def box(fill=None, line=None, ink=None, bold=False, **kw) -> str:
    bits = []
    if fill: bits.append(f'fillcolor="{fill}"')
    if line: bits.append(f'color="{line}"')
    if ink:  bits.append(f'fontcolor="{ink}"')
    if bold: bits.append('fontname="DejaVu Sans Bold"')
    bits += [f'{k}="{v}"' for k, v in kw.items()]
    return ", ".join(bits)


P_LLM   = box(BLUE_PALE, BLUE_LINE, BLUE_INK)
P_RULES = box(FOREST_PALE, FOREST_MID, FOREST)
P_FLAG  = box(ROSE_PALE, ROSE_LINE, ROSE_INK)
P_WARN  = box(AMBER_PALE, AMBER_LINE, AMBER_INK)
P_STORE = box(CREAM_DEEP, HAIR, MUTED)
P_HEAD  = box(FOREST, FOREST, "white", bold=True)


# ---------------------------------------------------------------- 1. the two doors
def d1_two_doors():
    return render("01-two-doors", f'''
  landing [label="The front page\\nasks one question:\\nare you looking for work,\\nor are you hiring?", {P_HEAD}];

  subgraph cluster_c {{
    label="Candidate side — open to anyone, no account";
    fontname="{FONT}"; fontsize=11; fontcolor="{FOREST}";
    color="{HAIR}"; style="rounded"; bgcolor="white"; margin=14;
    c1 [label="Browse open roles", {P_RULES}];
    c2 [label="Read our verdict on the advert:\\nhow specific it is, and\\nwhat it does not tell you", {P_RULES}];
    c3 [label="Apply with a CV", {P_RULES}];
    c4 [label="Private link to their own page:\\nwhat we read, what we noticed,\\nquestions, and consent switches", {P_RULES}];
    c1 -> c2 -> c3 -> c4;
  }}

  subgraph cluster_e {{
    label="Employer side — behind a team passcode";
    fontname="{FONT}"; fontsize=11; fontcolor="{FOREST}";
    color="{HAIR}"; style="rounded"; bgcolor="white"; margin=14;
    e1 [label="Create a role by pasting\\nthe advert they already wrote", {P_RULES}];
    e2 [label="Add private hiring preferences\\nthat candidates never see", {P_RULES}];
    e3 [label="Upload CVs", {P_RULES}];
    e4 [label="Ranked list, four separate scores,\\nevidence behind every number", {P_RULES}];
    e1 -> e2 -> e3 -> e4;
  }}

  landing -> c1 [label="  I am looking for work  "];
  landing -> e1 [label="  I am hiring  "];

  note [label="A candidate can never reach the employer pages.\\nThe employer pages never show one candidate another candidate.", {P_WARN}, shape=note];
  c4 -> note [style=invis];
  e4 -> note [style=invis];
''', rankdir="TB")



# ---------------------------------------------------------------- 2. system layers
def d2_layers():
    return render("02-system-layers", f'''
  subgraph cluster_b {{
    label="In the browser"; fontname="{FONT}"; fontsize=11; fontcolor="{FOREST}";
    color="{HAIR}"; style="rounded"; bgcolor="white"; margin=13;
    b1 [label="Plain HTML pages.\\nNo single-page app, no build step.\\nA little JavaScript for the\\ncompare picker and upload progress.", {P_STORE}];
  }}

  subgraph cluster_w {{
    label="Web layer  —  FastAPI + Jinja templates"; fontname="{FONT}"; fontsize=11; fontcolor="{FOREST}";
    color="{HAIR}"; style="rounded"; bgcolor="white"; margin=13;
    w1 [label="Public routes\\n/jobs, /apply, /track", {P_RULES}];
    w2 [label="Employer routes\\n/hiring/...\\nevery one behind the passcode check", {P_RULES}];
    w3 [label="Background worker\\nA CV takes 1-3 minutes, so the\\nupload returns straight away and\\nthe page polls for progress", {P_WARN}];
  }}

  subgraph cluster_p {{
    label="Processing  —  one LangGraph pipeline per CV"; fontname="{FONT}"; fontsize=11; fontcolor="{FOREST}";
    color="{HAIR}"; style="rounded"; bgcolor="white"; margin=13;
    p1 [label="Read the file and strip hidden text", {P_RULES}];
    p2 [label="Fit Engine\\nextract claims, match to the role,\\nwork out the score", {P_RULES}];
    p3 [label="Slop Bouncer\\nthree checks: how it is written,\\nwhether claims add up,\\nwhether answers match the CV", {P_FLAG}];
  }}

  subgraph cluster_x {{
    label="Outside the process"; fontname="{FONT}"; fontsize=11; fontcolor="{FOREST}";
    color="{HAIR}"; style="rounded"; bgcolor="white"; margin=13;
    x1 [label="Language model\\nreads text and pulls out facts.\\nNever decides anything.", {P_LLM}];
    x2 [label="GitHub and OpenAlex\\nonly called if the candidate\\nturned that source on", {P_LLM}];
    x3 [label="Job posting corpus\\nused to show how many adverts\\nare the same job reposted", {P_LLM}];
  }}

  subgraph cluster_s {{
    label="Storage  —  ordinary JSON files on disk, no database"; fontname="{FONT}"; fontsize=11; fontcolor="{FOREST}";
    color="{HAIR}"; style="rounded"; bgcolor="white"; margin=13;
    s1 [label="One folder per role.\\nInside it: the role, one file per\\ncandidate, their consent, answers,\\nstage and rejection reasons.", {P_STORE}];
    s2 [label="Answer cache\\nEvery model reply is saved by the\\nexact question asked, so the same\\nquestion is never paid for twice.", {P_STORE}];
  }}

  b1 -> w1; b1 -> w2;
  w1 -> w3 [label="  new application  "];
  w2 -> w3 [label="  uploaded CVs  "];
  w3 -> p1;
  p1 -> p2 -> p3;
  p2 -> x1 [label="  four jobs only  "];
  p2 -> x2 [label="  with consent  "];
  w2 -> x3 [style=dashed];
  p3 -> s1; p2 -> s1;
  x1 -> s2 [dir=both, label="  check first,\\nsave after  "];
  s1 -> w2 [style=dashed, label="  read back to draw pages  "];
''', rankdir="TB")


# ---------------------------------------------------------------- 3. what happens to a CV
def d3_pipeline():
    return render("03-what-happens-to-a-cv", f'''
  up [label="A CV arrives\\n(uploaded by the employer, or\\nsent by the candidate applying)", {P_HEAD}];

  n1 [label="1. Read the file\\nGet the text out of the PDF, and delete\\nanything hidden in it before anyone reads it", {P_RULES}];
  n2 [label="2. Look at how it is written\\nCount stock phrases, repeated rhythm, dashes.\\nAdvisory only - this can never cause a flag.", {P_FLAG}];
  n3 [label="3. Pull out what it claims\\nSkills, years, employers, dates, certificates", {P_LLM}];
  n4 [label="4. Match each claim to the role\\nStrong, moderate, weak or missing,\\nwith the resume line that supports it", {P_LLM}];
  n5 [label="5. Work out the fit score\\n70% required + 30% preferred.\\nOnly evidence counts. Writing quality cannot move it.", {P_RULES}];
  n6 [label="6. Check the claims add up\\nDates that overlap, expertise older than the\\ntechnology, results too round to be real", {P_FLAG}];
  n7 [label="7. Look outside the CV\\nOnly the sources the candidate switched on.\\nIf none, this step makes no network call at all.", {P_RULES}];
  n8 [label="8. Write the follow-up questions\\nOne per gap and per flag, so the candidate\\ngets to answer instead of being dropped", {P_LLM}];
  done [label="Saved as one file for this candidate.\\nThe employer sees four separate scores\\nand can open the evidence behind each one.", {P_HEAD}];

  up -> n1 -> n2 -> n3 -> n4 -> n5 -> n6 -> n7 -> n8 -> done;

  key [label="Blue = the language model reads text here.\\nGreen = plain code, no model involved.\\nPink = a Slop Bouncer check.", {P_STORE}, shape=note];
  {{ rank=same; n5; key; }}
''', rankdir="TB")


# ---------------------------------------------------------------- 4. the separation
def d4_separation():
    return render("04-two-engines-kept-apart", f'''
  cv [label="The same CV goes into both", {P_HEAD}];

  subgraph cluster_f {{
    label="Fit Engine  —  answers: can this person do the job?"; fontname="{FONT}"; fontsize=11; fontcolor="{FOREST}";
    color="{FOREST_MID}"; style="rounded"; bgcolor="white"; margin=14;
    f1 [label="Reads only facts:\\nskills, years, employers, dates", {P_RULES}];
    f2 [label="Fit score, 0 to 100", {P_RULES}, {box(FOREST_PALE, FOREST_MID, FOREST, bold=True)}];
    f1 -> f2;
  }}

  subgraph cluster_s {{
    label="Slop Bouncer  —  answers: is this application real?"; fontname="{FONT}"; fontsize=11; fontcolor="{ROSE_INK}";
    color="{ROSE_LINE}"; style="rounded"; bgcolor="white"; margin=14;
    s1 [label="Reads how it is written\\nand whether the claims\\ncontradict each other", {P_FLAG}];
    s2 [label="One of three answers:\\nlooks fine  /  cannot tell  /\\na person should look at this", {P_FLAG}];
    s1 -> s2;
  }}

  cv -> f1; cv -> s1;

  wall [label="No wire crosses here.\\n\\nThe Fit Engine's input type has no field for\\nanything the Slop Bouncer produces, so a style\\nsignal cannot reach the score even by mistake.\\n\\nA test changes every Slop Bouncer output and\\nasserts the fit score comes out identical.", {P_WARN}, shape=box];

  f2 -> wall [style=invis];
  s2 -> wall [style=invis];

  dash [label="The employer sees both, side by side,\\nas separate columns - never added together,\\nnever hidden inside one number", {P_HEAD}];
  wall -> dash [style=invis];
  f2 -> dash; s2 -> dash;
''', rankdir="TB")


# ---------------------------------------------------------------- 5. three checkpoints
def d5_checkpoints():
    return render("05-three-checkpoints", f'''
  a [label="The CV as it arrived", {P_STORE}];
  b [label="The claims, once matched to the role", {P_STORE}];
  c [label="The answers the candidate wrote back", {P_STORE}];

  cp1 [label="Check 1 - how it is written\\n\\nCounts stock phrases, the same three-beat rhythm on\\nevery line, dashes, and lines that explain their own\\nimportance.\\n\\nWe tested this on 60 real CVs against machine-written\\nrewrites of those same CVs. It told them apart 0% of\\nthe time. So it is shown as background information and\\nis blocked in code from ever causing a flag.", {P_FLAG}];

  cp2 [label="Check 2 - do the claims add up\\n\\nTwo full-time jobs with overlapping dates. Expertise\\nclaimed from before the technology existed, or before\\nthe person started working. The same line copied under\\ntwo employers. Every number suspiciously round.\\n\\nEach finding names the exact resume line it came from.", {P_FLAG}];

  cp3 [label="Check 3 - do the answers match the CV\\n\\nThe first question is deliberately casual, to capture how\\nthe person writes when they are not trying. Later answers\\nare compared against that, and against the CV.\\n\\nCatches an answer that quietly contradicts the resume.", {P_FLAG}];

  a -> cp1; b -> cp2; c -> cp3;

  rule [label="One odd detail is never enough.\\n\\nBefore anything is called likely made up, there must be two\\nfindings that are independent: a different kind of problem,\\nin a different place in the document. Otherwise the answer\\nstays 'cannot tell'.\\n\\nAnd the strongest answer any check can give is\\n'a person should look at this'. There is no reject.", {P_WARN}];

  cp1 -> rule; cp2 -> rule; cp3 -> rule;
''', rankdir="LR")


# ---------------------------------------------------------------- 6. consent
def d6_consent():
    return render("06-consent-gates-the-fetch", f'''
  subgraph cluster_off {{
    label="Default for every applicant"; fontname="{FONT}"; fontsize=11; fontcolor="{FOREST}";
    color="{HAIR}"; style="rounded"; bgcolor="white"; margin=14;
    o1 [label="GitHub switch: OFF\\nPublications switch: OFF", {P_STORE}];
    o2 [label="No request is sent.\\nNot fetched and hidden -\\nsimply never asked for.", {P_RULES}];
    o3 [label="Their score is exactly the same\\nas someone who has no public code.\\nSaying no costs nothing.", {P_RULES}];
    o1 -> o2 -> o3;
  }}

  subgraph cluster_on {{
    label="After the candidate presses Share this"; fontname="{FONT}"; fontsize=11; fontcolor="{FOREST}";
    color="{FOREST_MID}"; style="rounded"; bgcolor="white"; margin=14;
    n1 [label="GitHub switch: ON", {P_RULES}];
    n2 [label="Now the request goes out,\\nand only for that one source", {P_LLM}];
    n3 [label="Three kinds of result:\\n\\nconfirmed - the CV and the repos agree\\nnot mentioned - real work the CV left out\\nnothing found - no public code either way", {P_RULES}];
    n4 [label="'Nothing found' is never shown as a\\nstrike. Most professional work is\\nprivate. It changes no score.", {P_WARN}];
    n1 -> n2 -> n3 -> n4;
  }}

  subgraph cluster_rev {{
    label="If they change their mind"; fontname="{FONT}"; fontsize=11; fontcolor="{ROSE_INK}";
    color="{ROSE_LINE}"; style="rounded"; bgcolor="white"; margin=14;
    r1 [label="Switch back to OFF", {P_FLAG}];
    r2 [label="What was gathered under that switch\\nis deleted - the saved copy and the\\nrows on the employer's page", {P_FLAG}];
    r1 -> r2;
  }}

  o1 -> n1 [label="  candidate decides  "];
  n4 -> r1 [label="  candidate decides  "];

  note [label="The candidate sees the same findings the employer sees, on their own page,\\nand can download everything held about them as one file.", {P_HEAD}];
  r2 -> note [style=invis];
''', rankdir="LR")


# ---------------------------------------------------------------- 7. one model call
def d7_llm_call():
    return render("07-how-one-model-call-is-made", f'''
  q [label="A step needs the model to read something\\n(only four steps ever do)", {P_HEAD}];

  cache [label="Have we asked this exact question before?", shape=diamond, {box(CREAM_DEEP, HAIR, INK)}, margin="0.12,0.06"];
  hit [label="Yes - reuse the saved answer.\\nNo network call, no cost, instant.", {P_RULES}];

  offline [label="Is offline mode switched on?", shape=diamond, {box(CREAM_DEEP, HAIR, INK)}, margin="0.12,0.06"];
  stop [label="Stop with a clear error.\\nUsed before a demo to prove\\nnothing secretly needs the internet.", {P_WARN}];

  primary [label="Ask the main provider\\nDeepSeek V4 Flash through OpenRouter\\nMeasured: 59 facts from one CV chunk in 14 seconds", {P_LLM}];
  ok [label="Did it answer?", shape=diamond, {box(CREAM_DEEP, HAIR, INK)}, margin="0.12,0.06"];
  fb [label="Ask the backup provider instead\\nNVIDIA NIM - free, slower, and run by\\nsomeone else, which is the point when\\none provider is having a bad day", {P_LLM}];

  save [label="Save the answer under that exact question,\\nso it is never paid for twice", {P_STORE}];
  out [label="Hand the facts back to the step that asked", {P_HEAD}];

  q -> cache;
  cache -> hit [label="  yes  "];
  cache -> offline [label="  no  "];
  offline -> stop [label="  yes  "];
  offline -> primary [label="  no  "];
  primary -> ok;
  ok -> save [label="  yes  "];
  ok -> fb [label="  no  "];
  fb -> save;
  hit -> out; save -> out;

  note [label="Both providers put a reasoning model in front, and each turns that\\noff with different wording. Get it wrong and the model spends its\\nwhole budget thinking and returns nothing - a broken path, not a slow one.\\nThe wording for each lives in one config file, never in the code.", {P_WARN}, shape=note];
  out -> note [style=invis];
''', rankdir="TB")
