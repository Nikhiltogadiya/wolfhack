"""Build the demo fixture CV.

Deliberately defective, by construction, so the demo has a candidate C: the two Slop Bouncer
beats had no data in the corpus (nobody had a non-low style band or two corroborated flags,
and no CV named a GitHub handle at all). Each defect below is one the detectors are supposed
to catch, so this doubles as a labelled test case.
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate

import os

# Overridable, and not an absolute path from one machine: this file is public.
OUT = os.environ.get("FIT_HAPPENS_CV_OUT", "data/demo/resumes/rowan-feltz-cv.pdf")

ss = getSampleStyleSheet()
name = ParagraphStyle("name", parent=ss["Title"], fontSize=19, spaceAfter=2, alignment=0)
sub = ParagraphStyle("sub", parent=ss["Normal"], fontSize=9.5, textColor="#444", spaceAfter=10)
h = ParagraphStyle("h", parent=ss["Heading2"], fontSize=11.5, spaceBefore=11, spaceAfter=4)
b = ParagraphStyle("b", parent=ss["Normal"], fontSize=9.5, leading=13.5, spaceAfter=3)

S = []
S.append(Paragraph("Rowan Feltz", name))
S.append(Paragraph(
    "IT Infrastructure &amp; Information Security Manager<br/>"
    "Berlin, Germany · rowan.feltz@example.com · +49 30 5550 0142<br/>"
    "GitHub: tiangolo", sub))

S.append(Paragraph("Professional Summary", h))
# stock phrases + rule of three + self-significance + negative parallelism
S.append(Paragraph(
    "Results-driven infrastructure leader who has spearheaded enterprise transformation, "
    "leveraged cutting-edge technology, and orchestrated cross-functional synergy at scale. "
    "Not just an administrator, but a strategic partner to the business. Proven track record "
    "of owning enterprise infrastructure end to end, leading teams, and delivering upgrades — "
    "demonstrating strong leadership throughout.", b))

S.append(Paragraph("Experience", h))

# OVERLAP 1: these two full-time roles overlap 2021-2023 with no explanation
S.append(Paragraph("<b>Head of Infrastructure — Nordwind Freight GmbH</b> (full-time), "
                   "Berlin · January 2019 – December 2023", b))
S.append(Paragraph(
    "Spearheaded the migration of 200 servers, leveraged automation to reduce incidents by "
    "50%, and orchestrated a 100% successful audit outcome. Led a team of four engineers. "
    "Owned Active Directory administration and design across a 900-person business. "
    "Ran the information security programme including risk assessment, audit response and "
    "security awareness — demonstrating strong leadership.", b))

S.append(Paragraph("<b>Principal Systems Architect — Halvard Systems AG</b> (full-time), "
                   "Hamburg · March 2021 – June 2024", b))
S.append(Paragraph(
    "Acted as escalation point for major incidents. Planned and delivered hardware and "
    "software upgrades across the estate. Network administration across routing, switching "
    "and firewalls, covering 300 sites and 3,000 endpoints with 100% uptime.", b))

S.append(Paragraph("<b>Systems Administrator — Bergmann Logistik</b>, "
                   "Bremen · June 2014 – December 2018", b))
S.append(Paragraph(
    "Windows Server, VMware and Cisco networking. Supported 500 users across 5 sites. "
    "Managed backup, disaster recovery and the VPN estate.", b))

S.append(Paragraph("Technical Skills", h))
# EXPERTISE PREDATING THE TECHNOLOGY: Kubernetes was first released in 2014
S.append(Paragraph(
    "Active Directory · Windows Server · VMware · Cisco routing and switching · Fortinet "
    "firewalls · SCCM · VPN · Microsoft 365 · Expert-level Kubernetes, used continuously "
    "since 2009 · Terraform · ISO 27001 · Backup and disaster recovery", b))

S.append(Paragraph("Education &amp; Certifications", h))
S.append(Paragraph(
    "BSc Computer Science, Technische Universität Berlin, 2014<br/>"
    "MCSA (Microsoft) · CompTIA Security+ · ITIL Foundation", b))

SimpleDocTemplate(OUT, pagesize=A4, leftMargin=20*mm, rightMargin=20*mm,
                  topMargin=18*mm, bottomMargin=18*mm).build(S)
print("wrote", OUT)
