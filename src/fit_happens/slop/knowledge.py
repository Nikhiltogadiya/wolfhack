"""Facts the deterministic bluff patterns check against.

Kept small and auditable on purpose. Every entry here can produce a flag on a real person's
application, so each one is a claim we are prepared to defend in front of them - which rules
out anything scraped or guessed.

Dates are first public release, not first commit or first announcement, because that is the
earliest point at which someone could plausibly have used the thing in a job.
"""

from __future__ import annotations

import re

# First public release year. A claim of N years' experience that reaches back before this is
# arithmetically impossible, which is the strongest kind of flag we can raise: it needs no
# judgement and the candidate can check it themselves.
TECH_RELEASED: dict[str, int] = {
    "kubernetes": 2014, "docker": 2013, "terraform": 2014, "ansible": 2012, "helm": 2016,
    "prometheus": 2015, "grafana": 2014, "istio": 2017, "argo cd": 2018, "argocd": 2018,
    "react": 2013, "vue": 2014, "angular": 2016, "angularjs": 2010, "svelte": 2016,
    "next.js": 2016, "nextjs": 2016, "typescript": 2012, "deno": 2018, "node.js": 2009,
    "rust": 2015, "go": 2009, "golang": 2009, "kotlin": 2011, "swift": 2014, "scala": 2004,
    "tensorflow": 2015, "pytorch": 2016, "keras": 2015, "scikit-learn": 2010, "pandas": 2008,
    "hugging face": 2018, "transformers": 2017, "bert": 2018, "gpt-3": 2020, "gpt-4": 2023,
    "langchain": 2022, "llamaindex": 2022, "chatgpt": 2022, "openai api": 2020,
    "chromadb": 2022, "pinecone": 2021, "weaviate": 2019, "qdrant": 2021, "milvus": 2019,
    "snowflake": 2014, "databricks": 2013, "airflow": 2015, "dbt": 2016, "spark": 2010,
    "kafka": 2011, "elasticsearch": 2010, "mongodb": 2009, "redis": 2009, "postgresql": 1996,
    "aws lambda": 2014, "azure": 2010, "gcp": 2008, "google cloud": 2008, "aws": 2006,
    "graphql": 2015, "grpc": 2016, "kubeflow": 2018, "openshift": 2011, "vmware": 1999,
    "figma": 2016, "slack": 2013, "notion": 2016, "salesforce": 1999, "hubspot": 2006,
    "power bi": 2015, "tableau": 2003, "looker": 2012, "sccm": 2007, "wsus": 2005,
}

# Certifications, as their issuers actually name them. A credential written in a form the
# issuing body does not use is a specific, checkable inconsistency - but ONLY as one flag among
# others, since people abbreviate constantly and a typo is not a fabrication.
REAL_CERTIFICATIONS: dict[str, str] = {
    "cissp": "CISSP (ISC2)", "cisa": "CISA (ISACA)", "cism": "CISM (ISACA)",
    "ccna": "CCNA (Cisco)", "ccnp": "CCNP (Cisco)", "ccie": "CCIE (Cisco)",
    "comptia security+": "CompTIA Security+", "security+": "CompTIA Security+",
    "comptia network+": "CompTIA Network+", "network+": "CompTIA Network+",
    "comptia a+": "CompTIA A+", "pmp": "PMP (PMI)", "prince2": "PRINCE2 (Axelos)",
    "itil": "ITIL (Axelos)", "cka": "CKA (CNCF)", "ckad": "CKAD (CNCF)", "cks": "CKS (CNCF)",
    "aws certified solutions architect": "AWS Certified Solutions Architect",
    "aws certified developer": "AWS Certified Developer",
    "azure administrator": "Microsoft Certified: Azure Administrator Associate",
    "mcse": "MCSE (Microsoft)", "mcsa": "MCSA (Microsoft)", "rhce": "RHCE (Red Hat)",
    "rhcsa": "RHCSA (Red Hat)", "oscp": "OSCP (Offensive Security)", "ceh": "CEH (EC-Council)",
    "csm": "Certified ScrumMaster (Scrum Alliance)", "safe": "SAFe (Scaled Agile)",
    "togaf": "TOGAF (The Open Group)", "six sigma": "Six Sigma",
    # Added after running against real resumes, which write these forms constantly.
    "a+ certified": "CompTIA A+", "network+ certified": "CompTIA Network+",
    "security+ certified": "CompTIA Security+",
    "microsoft certified professional": "MCP (Microsoft)", "mcp": "MCP (Microsoft)",
    "microsoft certified systems engineer": "MCSE (Microsoft)",
    "cisco certified network associate": "CCNA (Cisco)",
    "certified information systems auditor": "CISA (ISACA)",
    "certified information systems security professional": "CISSP (ISC2)",
    "project management professional": "PMP (PMI)",
    "certified scrum master": "Certified ScrumMaster (Scrum Alliance)",
    "aws certified cloud practitioner": "AWS Certified Cloud Practitioner",
    "azure fundamentals": "Microsoft Certified: Azure Fundamentals",
    "vcp": "VCP (VMware)", "vmware certified professional": "VCP (VMware)",
    "microsoft certified system administrator": "MCSA (Microsoft)",
    "microsoft certified systems administrator": "MCSA (Microsoft)",
    "juniper networks certified internet associate": "JNCIA (Juniper)",
    "brocade certified network engineer": "BCNE (Brocade)",
}

# Credential shapes that do not exist, i.e. someone has invented a plausible-sounding name.
# Each is a real pattern seen in fabricated resumes: a vendor that issues no such cert, or a
# level that vendor does not offer.
IMPOSSIBLE_CERT_PATTERNS = [
    (re.compile(r"\bcertified\s+(kubernetes|docker)\s+(expert|master|professional)\b", re.I),
     "CNCF issues CKA, CKAD and CKS - there is no 'Certified Kubernetes Expert'"),
    (re.compile(r"\baws\s+certified\s+(expert|master)\b", re.I),
     "AWS levels are Foundational, Associate, Professional and Specialty - not Expert or Master"),
    (re.compile(r"\bcissp\s*[- ]?\s*(level\s*[23]|advanced|master)\b", re.I),
     "CISSP has no levels; concentrations are ISSAP, ISSEP and ISSMP"),
    (re.compile(r"\bpmp\s*[- ]?\s*(level\s*\d|advanced|senior)\b", re.I),
     "PMI issues one PMP; there are no PMP levels"),
    (re.compile(r"\bgoogle\s+certified\s+(expert|master)\s+(cloud|engineer)\b", re.I),
     "Google Cloud levels are Associate and Professional"),
    (re.compile(r"\bcertified\s+(agile|scrum)\s+(guru|ninja|expert)\b", re.I),
     "no scrum body issues a 'guru', 'ninja' or 'expert' credential"),
]


def tech_release_year(skill: str) -> int | None:
    """Release year for a named technology, matching the longest key first so 'aws lambda'
    is not resolved as 'aws'."""
    s = skill.lower().strip()
    for key in sorted(TECH_RELEASED, key=len, reverse=True):
        if re.search(rf"\b{re.escape(key)}\b", s):
            return TECH_RELEASED[key]
    return None
