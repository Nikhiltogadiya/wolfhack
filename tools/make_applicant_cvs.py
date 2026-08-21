"""Generate ten fictional applicant CVs for the demo corpus.

A ranking with five people does not look like a real inbox, and the two demo candidates do not
stand out against it. These are ten more: a realistic spread across the fit range, mostly
clean, with a couple carrying mild issues so the flag columns are not uniformly empty.

Every person here is invented. Emails are @example.com. Written at 400-700 words, the band the
CP1 style read is safe at.

    uv run python tools/make_applicant_cvs.py
"""
from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate

OUT = Path("data/demo/applicants")

ss = getSampleStyleSheet()
NAME = ParagraphStyle("n", parent=ss["Title"], fontSize=18, spaceAfter=2, alignment=0)
SUB = ParagraphStyle("s", parent=ss["Normal"], fontSize=9.5, textColor="#444", spaceAfter=10)
H = ParagraphStyle("h", parent=ss["Heading2"], fontSize=11, spaceBefore=10, spaceAfter=4)
B = ParagraphStyle("b", parent=ss["Normal"], fontSize=9.5, leading=13.4, spaceAfter=3)

# (slug, name, headline, city, summary, [(role, dates, detail)], skills, education)
PEOPLE = [
 ("elif-karadag", "Elif Karadag",
  "IT Infrastructure & Security Manager", "Berlin",
  "Infrastructure manager with nine years running enterprise estates and the security "
  "programmes around them. Currently responsible for a 750-person logistics operation across "
  "four countries, leading a team of five.",
  [("Infrastructure & Security Manager - Halden Cargo AG, Berlin", "March 2019 - present",
    "Own the full server, storage and network estate for 750 staff across four countries. "
    "Lead five engineers: two infrastructure, two service desk, one security. Run the "
    "information security programme end to end - annual risk assessment, ISO 27001 surveillance "
    "audits, and the awareness training everyone takes each year. Designed and delivered the "
    "Active Directory consolidation when we merged two domains after an acquisition, moving "
    "1,400 accounts with no unplanned downtime. Escalation point for major incidents, including "
    "a ransomware attempt in 2022 that was contained at the perimeter."),
   ("Senior Systems Engineer - Weser Technik GmbH, Bremen", "June 2015 - February 2019",
    "Windows Server and VMware estate for a manufacturer with 400 users on three sites. "
    "Rebuilt the backup and disaster recovery arrangement after a failed restore test, "
    "cutting recovery time from two days to four hours. Managed Cisco routing and switching "
    "and the Fortinet firewall estate. First point of contact for the external auditors."),
   ("Systems Administrator - Ostsee Handel, Rostock", "August 2013 - May 2015",
    "Day-to-day administration of Windows Server, Active Directory and the VPN estate for "
    "180 users. Ran the hardware refresh across two sites.")],
  "Active Directory design and administration - Windows Server - VMware vSphere - Cisco "
  "routing and switching - Fortinet firewalls - ISO 27001 - risk assessment and audit response "
  "- backup and disaster recovery - Microsoft 365 - SCCM - VPN - incident response - German "
  "(native), English (fluent)",
  "BSc Computer Science, Universitat Bremen, 2013. CISSP. ITIL Foundation. "
  "German and EU citizen, permanent right to work in Germany."),

 ("tomas-ferreira", "Tomas Ferreira",
  "Senior Infrastructure Engineer", "Hamburg",
  "Infrastructure engineer with seven years across server, storage and network estates in "
  "logistics and distribution.",
  [("Senior Infrastructure Engineer - Nordfracht Logistik, Hamburg", "January 2018 - present",
    "Server and storage estate for 600 users. Active Directory administration, Group Policy "
    "design, and the Microsoft 365 tenancy. Planned and delivered two hardware refresh cycles "
    "and the move from on-premise Exchange. Mentor two junior engineers, though not a formal "
    "line manager."),
   ("Infrastructure Engineer - Baltic Freight Services, Kiel", "September 2014 - December 2017",
    "Windows Server, VMware and Veeam backup. Network administration across four depots "
    "including routing, switching and site-to-site VPN.")],
  "Active Directory - Windows Server - VMware - Veeam - Microsoft 365 - Cisco switching - "
  "site-to-site VPN - SCCM - PowerShell - Portuguese (native), German (fluent), English (fluent)",
  "BSc Information Systems, Universidade do Porto, 2014. MCSA. EU citizen."),

 ("aoife-brennan", "Aoife Brennan",
  "Network Engineer", "Dublin",
  "Network engineer with eight years designing and running multi-site networks for "
  "manufacturing and distribution businesses.",
  [("Lead Network Engineer - Shannon Distribution, Limerick", "April 2017 - present",
    "Own the network across eleven sites: Cisco routing and switching, Palo Alto firewalls, "
    "and the MPLS and SD-WAN estate. Delivered the SD-WAN migration across all sites. On call "
    "for network incidents. Work alongside the security team on firewall rule reviews but do "
    "not own the security programme."),
   ("Network Engineer - Corrib Systems, Galway", "July 2015 - March 2017",
    "Switching, wireless and VPN for a 300-user manufacturer. Supported the annual "
    "penetration test remediation.")],
  "Cisco routing and switching - Palo Alto firewalls - SD-WAN - MPLS - wireless - VPN - "
  "network monitoring - English (native), Irish",
  "BEng Electronic Engineering, University of Galway, 2015. CCNP. Irish and EU citizen."),

 ("ravi-shankar-nair", "Ravi Shankar Nair",
  "IT Service Desk Manager", "Frankfurt",
  "Service desk manager with six years leading support teams, moving toward infrastructure "
  "ownership.",
  [("Service Desk Manager - Main Rhein Handel, Frankfurt", "February 2019 - present",
    "Lead a team of six across two shifts supporting 900 users. Own the ticketing system, "
    "SLAs and reporting. Coordinate with the infrastructure team on escalations and change "
    "windows. Ran the Windows 11 rollout across 900 endpoints."),
   ("Senior Support Analyst - Taunus IT Services, Frankfurt", "March 2016 - January 2019",
    "Second-line support for Windows Server, Active Directory account administration and "
    "Microsoft 365. Handled the desktop side of two office relocations.")],
  "Active Directory account administration - Microsoft 365 - SCCM - Windows 11 deployment - "
  "ITIL service management - ticketing and SLA reporting - English (fluent), German (B2), "
  "Malayalam (native)",
  "BTech Information Technology, Cochin University, 2015. ITIL Foundation. "
  "EU Blue Card holder, right to work in Germany."),

 ("margit-halvorsen", "Margit Halvorsen",
  "Information Security Analyst", "Oslo",
  "Security analyst with seven years in risk assessment, audit response and awareness "
  "programmes for regulated businesses.",
  [("Information Security Analyst - Fjordline Maritime, Oslo", "May 2018 - present",
    "Run the annual risk assessment and the ISO 27001 surveillance audits. Own the security "
    "awareness programme, including phishing simulation. Review firewall and access control "
    "changes. Write the security policy set. Work closely with infrastructure but do not "
    "administer the estate."),
   ("Security Analyst - Nordisk Forsikring, Bergen", "January 2016 - April 2018",
    "Access reviews, vendor security assessments, and incident documentation for an insurer.")],
  "ISO 27001 - risk assessment - audit response - security awareness and phishing simulation "
  "- access control review - security policy - vendor assessment - Norwegian (native), "
  "English (fluent), German (B1)",
  "MSc Information Security, NTNU Trondheim, 2015. CISM. Norwegian citizen, EEA."),

 ("kwame-boateng", "Kwame Boateng",
  "Systems Administrator", "Rotterdam",
  "Systems administrator with five years across virtualisation, storage and backup in "
  "shipping and freight.",
  [("Systems Administrator - Maasvlakte Freight BV, Rotterdam", "August 2019 - present",
    "VMware vSphere estate of 90 virtual machines, Windows Server, and the Veeam backup "
    "arrangement. Active Directory administration and Group Policy. Monthly patch cycle "
    "across the server estate. Supported the datacentre migration to a colocation facility."),
   ("Junior Systems Administrator - Delta Port Services, Rotterdam", "June 2017 - July 2019",
    "Windows Server, desktop support and the VPN estate for 220 users.")],
  "VMware vSphere - Windows Server - Active Directory - Veeam - storage administration - "
  "patch management - PowerShell - Dutch (fluent), English (fluent), Twi (native)",
  "HBO Informatica, Hogeschool Rotterdam, 2017. VCP-DCV. Dutch citizen."),

 ("lucia-moreno", "Lucia Moreno",
  "IT Manager", "Madrid",
  "IT manager with ten years running technology for retail businesses, covering "
  "infrastructure, applications and the service desk.",
  [("IT Manager - Grupo Peninsular Retail, Madrid", "March 2016 - present",
    "Own all technology for a retailer with 140 stores and 1,100 staff. Lead a team of seven "
    "covering infrastructure, applications and support. Delivered the point-of-sale replacement "
    "across all stores. Manage the supplier relationships and the technology budget. "
    "Infrastructure is largely outsourced to a managed service provider, which I oversee."),
   ("IT Coordinator - Textiles Ibericos, Valencia", "September 2013 - February 2016",
    "Windows Server and desktop estate for 300 staff across two sites.")],
  "IT service management - supplier and budget management - point of sale systems - "
  "Microsoft 365 - Windows Server - team leadership - Spanish (native), English (fluent)",
  "Licenciatura en Administracion de Empresas, Universidad Complutense de Madrid, 2012. "
  "PRINCE2 Practitioner. Spanish and EU citizen."),

 ("jonas-wiedemann", "Jonas Wiedemann",
  "Infrastructure Consultant", "Munich",
  "Infrastructure consultant working on fixed-term engagements, mostly Active Directory and "
  "datacentre projects for mid-sized businesses.",
  [("Infrastructure Consultant - Sudbayern IT Partner, Munich", "January 2021 - present",
    "Engagements of three to nine months. Active Directory design and migration, Windows "
    "Server estate builds, and two datacentre relocations. Client sites between 200 and 900 "
    "users."),
   ("Infrastructure Consultant - Alpen Systemhaus, Innsbruck", "June 2020 - March 2022",
    "Concurrent contract work on Active Directory and Exchange migrations for Austrian "
    "clients. Overlapped with the Munich engagement by arrangement with both firms."),
   ("Senior Systems Engineer - Isar Werke, Munich", "February 2016 - May 2020",
    "Windows Server, Active Directory and VMware for a 500-user manufacturer.")],
  "Active Directory design and migration - Windows Server - VMware - Exchange - datacentre "
  "relocation - Hyper-V - PowerShell - German (native), English (fluent)",
  "Diplom Informatik, TU Munchen, 2015. German citizen."),

 ("priyanka-deshmukh", "Priyanka Deshmukh",
  "Cloud Platform Engineer", "Amsterdam",
  "Platform engineer with six years building and running cloud infrastructure, mostly AWS "
  "and Kubernetes.",
  [("Cloud Platform Engineer - Vaart Digital BV, Amsterdam", "April 2020 - present",
    "Own the AWS estate and the Kubernetes platform serving 40 engineers. Terraform for all "
    "infrastructure. Built the CI and deployment pipelines. On call for platform incidents. "
    "Reduced monthly cloud spend by 30 percent through rightsizing."),
   ("DevOps Engineer - Zuiderpoort Software, Utrecht", "July 2018 - March 2020",
    "Docker, Kubernetes and GitLab CI for a software business. Some Linux server "
    "administration.")],
  "AWS - Kubernetes - Terraform - Docker - GitLab CI - Linux administration - Python - "
  "Prometheus and Grafana - English (fluent), Hindi (native), Dutch (A2)",
  "BE Computer Engineering, University of Pune, 2017. AWS Solutions Architect Associate. "
  "Dutch residence permit with unrestricted right to work."),

 ("stefan-novak", "Stefan Novak",
  "Infrastructure Team Lead", "Prague",
  "Infrastructure team lead with eight years across server estates, networks and audit "
  "preparation for regulated manufacturers.",
  [("Infrastructure Team Lead - Vltava Precision, Prague", "October 2018 - present",
    "Lead three engineers running the server, storage and network estate for 550 staff on two "
    "sites. Active Directory and Windows Server administration. Cisco switching and Fortinet "
    "firewalls. Prepare and present evidence for the annual ISO 27001 audit and the customer "
    "security assessments that come with automotive contracts. Delivered the storage "
    "replacement and the network refresh."),
   ("Systems Engineer - Morava Industrial, Brno", "September 2015 - September 2018",
    "Windows Server, VMware and backup for a 300-user manufacturer. Supported the first "
    "ISO 27001 certification.")],
  "Active Directory - Windows Server - VMware - Cisco switching - Fortinet firewalls - "
  "ISO 27001 audit preparation - storage - backup and disaster recovery - team leadership - "
  "Czech (native), English (fluent), German (B2)",
  "Ing. Informatics, Czech Technical University in Prague, 2015. "
  "Czech and EU citizen."),
]


def build(slug, name, headline, city, summary, roles, skills, education) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{slug}.pdf"
    s = [Paragraph(name, NAME),
         Paragraph(f"{headline}<br/>{city} &middot; "
                   f"{slug.replace('-', '.')}@example.com", SUB),
         Paragraph("Summary", H), Paragraph(summary, B),
         Paragraph("Experience", H)]
    for role, dates, detail in roles:
        s.append(Paragraph(f"<b>{role}</b> &middot; {dates}", B))
        s.append(Paragraph(detail, B))
    s += [Paragraph("Skills", H), Paragraph(skills, B),
          Paragraph("Education &amp; Certifications", H), Paragraph(education, B)]
    SimpleDocTemplate(str(path), pagesize=A4, leftMargin=20*mm, rightMargin=20*mm,
                      topMargin=18*mm, bottomMargin=18*mm).build(s)
    return path


if __name__ == "__main__":
    for p in PEOPLE:
        path = build(*p)
        print(f"  {path.name:34} {path.stat().st_size:>6} bytes")
    print(f"\n{len(PEOPLE)} CVs written to {OUT}/")
