"""Protected-characteristic guard for the internal JD.

The internal JD is the product's sharpest differentiator and its sharpest legal edge. An
employer's real, unpublished preferences are often perfectly legitimate operational
constraints - *must start within three weeks*, *the team is junior so we need a mentor*. But
the same free-text box will happily accept an unlawful one, and scoring candidates against a
criterion that was omitted from the public advert *because publishing it would be unlawful*
creates a durable, auditable record of discrimination applied at scale. NYC Local Law 144 and
the EU AI Act's employment provisions both bite here, as does the German AGG.

So the internal JD is not a free-text box. It is an allowlist of operational constraint types,
and every value passes this guard before it can reach the scorer. Blocked entries are recorded
in the audit trail rather than silently dropped - "we checked and refused" is the defensible
position; "we never looked" is not.

Deterministic by design (house rule 6). A recruiter is entitled to know exactly why their input
was refused, and an LLM that changes its mind between runs cannot give them that.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

# Constraint types an employer may legitimately hold privately. Anything not on this list
# cannot be expressed at all, which is the point - the schema is the first line of defence and
# the lexicon below is the second.
ALLOWED_FIELDS = {
    "start_availability": "When the role must be filled by",
    "seniority_band": "Level the role is pitched at",
    "budget_band": "Compensation range actually available",
    "mentoring_capacity": "Whether this hire must mentor, or needs mentoring",
    "onsite_days": "Days per week on site",
    "team_context": "Size, shape and maturity of the team",
    "tooling": "The stack actually in use, versus the advert's wish list",
    "travel_requirement": "Travel the role genuinely involves",
    "language_requirement": "Working language, with an operational justification",
    "security_clearance": "Clearance the work legally requires",
    "shift_pattern": "Hours or on-call the role genuinely involves",
}

Category = Literal[
    "age", "sex_gender", "pregnancy_family", "race_ethnicity_origin", "religion_belief",
    "disability_health", "sexual_orientation", "marital_status", "union_political",
    "socioeconomic_proxy", "appearance",
]


@dataclass(frozen=True)
class Rule:
    category: Category
    pattern: re.Pattern
    why: str


def _r(cat: Category, expr: str, why: str) -> Rule:
    return Rule(cat, re.compile(expr, re.IGNORECASE), why)


# Direct protected characteristics, and the proxies that do the same work while sounding
# innocuous. The proxies matter more in practice: nobody writes "no women", but "cultural fit"
# and "no career gaps" get typed into boxes like this every day.
RULES: list[Rule] = [
    # NOTE ON PATTERN STYLE: word STEMS are followed by \w* rather than \b. A trailing \b after
    # a stem silently fails on every inflection - "pregnan\b" never matches "pregnant",
    # "union member\b" never matches "union members" - and the failure is invisible because the
    # rule still compiles and still matches the one example you tested it on.
    _r("age", r"\b(age[ds]?\s*(under|over|below|above|\d)|aged?\s+\d{2}|under\s*\d{2}\s*years?\s*old|born\s+(after|before))", "explicit age criterion"),
    _r("age", r"\b(young\w*|youthful|recent\s+grad\w*\s+only|new\s+grad\w*\s+only|digital\s+native\w*|fresh\s+out\s+of|no\s+one\s+over)", "age proxy"),
    _r("age", r"\b(\d{1,2}\s*[-\u2013]\s*\d{1,2}\s*years?\s*old|generation\s*[zy]\b|millennial\w*)", "age proxy"),
    _r("sex_gender", r"\b(male|female|man|woman|men|women|gentlem\w+|lad(y|ies))\s+(only|preferred|candidate\w*|applicant\w*)", "explicit sex criterion"),
    _r("sex_gender", r"\b(he|she)\s+(must|should|will)\b|\b(salesm\w+|saleswom\w+|handym\w+|waitress\w*|steward(ess)?\w*)\b", "gendered requirement"),
    _r("sex_gender", r"\b(prefer\w*|want|need|seeking)\s+(a\s+)?(male|female|man|woman|guy|girl)\b", "explicit sex preference"),
    _r("pregnancy_family", r"\b(pregnan\w*|maternity|paternity|childcare|no\s+(kids|children)|childless|family\s+plan\w*|planning\s+(a\s+)?family|of\s+childbearing)", "pregnancy or family status"),
    _r("race_ethnicity_origin", r"\b(rac(e|ial)|ethnic\w*|caucasian\w*|black|asian|hispanic\w*|latino\w*|skin\s+colou?r)\b", "race or ethnicity"),
    _r("race_ethnicity_origin", r"\b(native\s+\w*\s*speaker\w*|mother[- ]tongue|national\w*\s+only|must\s+be\s+(a\s+)?(citizen|national)\w*\s+of)", "national-origin proxy - specify a proficiency level and its operational reason instead"),
    _r("race_ethnicity_origin", r"\b(no\s+(visa|sponsorship)\s*\w*|western\s+(name\w*|background)|foreign[- ]sounding)", "national-origin proxy"),
    _r("religion_belief", r"\b(religio\w*|christian\w*|muslim\w*|jewish|hindu\w*|buddhist\w*|catholic\w*|atheist\w*|church|mosque|synagogue|halal|kosher|sabbath)", "religion or belief"),
    _r("disability_health", r"\b(disabilit\w*|disabled|handicap\w*|able[- ]bodied|wheelchair\w*|blind|deaf|mental\s+health|medical\s+(condition\w*|histor\w+)|BMI|physically\s+fit|no\s+health\s+issue\w*|sick\s+(day|leave)\w*\s+histor\w+)", "disability or health status"),
    _r("sexual_orientation", r"\b(sexual\s+orientation|gay|lesbian\w*|straight|heterosexual\w*|homosexual\w*|LGBT\w*)", "sexual orientation"),
    _r("marital_status", r"\b(marital\s+status|married|single,|unmarried|divorced|widow\w*|spouse\w*|no\s+dependent\w*)", "marital status"),
    _r("union_political", r"\b(union\s+\w*(member|membership|activity)\w*|no\s+union\w*|works\s+council|trade\s+union\w*|political\s+(affiliation\w*|part(y|ies)|view\w*)|voted?\s+for)", "union or political affiliation"),
    _r("socioeconomic_proxy", r"\b((no|without|zero)\s+(\w+\s+){0,2}(career\s+|employment\s+)?gaps?|continuous\s+employment\s+(only|required)|unexplained\s+(\w+\s+){0,2}gaps?)", "career-gap screening - a proxy for parental leave, illness and disability"),
    _r("socioeconomic_proxy", r"\b(cultur(e|al)\s+fit|culture[- ]add\s+only|our\s+kind\s+of\s+people|fit\s+with\s+the\s+lads|beer\s+test)", "'culture fit' - unmeasurable and a documented vector for affinity bias; describe the working style the role needs instead"),
    _r("socioeconomic_proxy", r"\b(postcode\w*|zip\s*code\w*|neighbou?rhood\w*|from\s+a\s+good\s+(area|school)|elite\s+(universit\w+|school\w*)\s+only|(oxbridge|ivy\s+league)\s+only)", "socioeconomic proxy for race and class"),
    _r("appearance", r"\b(attractive|good[- ]looking|presentable\s+appearance|photo\s+(required|attached)|headshot\w*\s+required|well[- ]groomed|height|weight)", "appearance requirement"),
]


@dataclass
class GuardResult:
    allowed: bool
    field_name: str
    value: str
    violations: list[tuple[Category, str]] = field(default_factory=list)

    @property
    def reason(self) -> str:
        if self.allowed:
            return ""
        return "; ".join(f"{cat.replace('_', '/')}: {why}" for cat, why in self.violations)


def check_value(field_name: str, value: str) -> GuardResult:
    if field_name not in ALLOWED_FIELDS:
        return GuardResult(
            False, field_name, value,
            [("socioeconomic_proxy", f"'{field_name}' is not an allowed constraint type; "
                                     f"permitted: {', '.join(sorted(ALLOWED_FIELDS))}")],
        )
    hits = [(r.category, r.why) for r in RULES if r.pattern.search(value)]
    # de-duplicate by category, keeping the first explanation
    seen: dict[Category, str] = {}
    for cat, why in hits:
        seen.setdefault(cat, why)
    return GuardResult(not seen, field_name, value, list(seen.items()))
