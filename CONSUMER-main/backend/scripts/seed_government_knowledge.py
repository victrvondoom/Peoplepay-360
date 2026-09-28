"""
Government Domain - Authored Knowledge Seeder
Writes curated procedural guides, grievance/complaint templates, FAQs, and
synthetic test cases for topics that have no single scrapable official page
(certificates, property registration, pensions, state portals) or that are
best captured as structured how-to content, matching the authoring pattern
used by knowledge/ecommerce/complaint_templates and knowledge/banking seeds.
"""
import json
from pathlib import Path

KNOWLEDGE_ROOT = Path(__file__).resolve().parents[2] / "knowledge" / "government"


def save(folder: str, filename: str, title: str, authority: str, category: str, content: str):
    dest_dir = KNOWLEDGE_ROOT / folder
    dest_dir.mkdir(parents=True, exist_ok=True)
    filepath = dest_dir / filename
    filepath.write_text(content.strip() + "\n", encoding="utf-8")

    meta_dir = KNOWLEDGE_ROOT / "metadata" / folder
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / f"{Path(filename).stem}.json").write_text(
        json.dumps(
            {
                "title": title,
                "authority": authority,
                "source_url": None,
                "domain": "government",
                "type": "authored_guide",
                "category": category,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"  wrote {filepath.relative_to(KNOWLEDGE_ROOT)}")


DOCUMENTS = [
    # ── FAQs ──────────────────────────────────────────────
    {
        "folder": "faqs", "filename": "passport_faqs.txt",
        "title": "Passport Application FAQs", "authority": "MEA / Passport Seva",
        "category": "faq",
        "content": """
PASSPORT APPLICATION — FREQUENTLY ASKED QUESTIONS

Q: What are the passport application types?
A: Fresh/Normal application, Tatkal (expedited) application, Reissue (renewal, name change,
address change, damaged/lost passport), and Diplomatic/Official passports handled separately.

Q: How long does a normal passport application take?
A: After document verification and police verification, normal applications are typically
processed within 30-45 days. Tatkal applications are typically processed within 1-3 working
days after appointment, subject to police verification clearance (pre- or post-issuance).

Q: My passport application is delayed beyond the published timeline — what can I do?
A: 1) Check application status on the Passport Seva portal using your File Number.
   2) Contact the Passport Seva Kendra (PSK) / Regional Passport Office (RPO) helpline.
   3) If police verification is the bottleneck, follow up with the local police station
      or e-governance cell; a Case ID from mPassport Police app can help.
   4) If unresolved, file a grievance through the Passport Seva portal's grievance module,
      or escalate via CPGRAMS (Ministry of External Affairs is a CPGRAMS-linked ministry).
   5) For urgent travel, apply for Tatkal or request an out-of-turn appointment citing
      documented emergency (medical, death in family, etc.) at the RPO.

Q: What documents are commonly required?
A: Proof of address, proof of date of birth, identity proof, and (for Tatkal) additional
verification documents/annexures. Requirements vary by application type; always check the
current document advisor on the Passport Seva portal before applying.

Q: Who do I escalate to if the Regional Passport Office does not respond?
A: Regional Passport Officer -> Passport Seva grievance cell -> CPGRAMS complaint against
Ministry of External Affairs -> Central Public Information Officer (RTI) for status records
if administrative escalation fails.
""",
    },
    {
        "folder": "faqs", "filename": "aadhaar_update_faqs.txt",
        "title": "Aadhaar Update & Correction FAQs", "authority": "UIDAI",
        "category": "faq",
        "content": """
AADHAAR UPDATE / CORRECTION — FREQUENTLY ASKED QUESTIONS

Q: What Aadhaar details can be updated?
A: Name, address, date of birth, gender, mobile number, email, and biometrics (photo,
fingerprints, iris) can be updated at an Aadhaar Enrolment/Update Centre, and demographic
details (like address) can also be updated online via the UIDAI Self-Service Update Portal
(SSUP) with supporting documents.

Q: My update request was rejected — what now?
A: 1) Check the rejection reason in the update history on the UIDAI portal (usually a
      document mismatch, poor scan quality, or field-format issue).
   2) Resubmit with a clearer, currently-valid supporting document that matches UIDAI's
      accepted Proof of Identity / Proof of Address / Proof of Date of Birth lists.
   3) If the rejection appears to be an error, raise a complaint via UIDAI's contact centre
      (1947) or the UIDAI grievance portal, quoting the Update Request Number (URN).
   4) Escalate to CPGRAMS against UIDAI if unresolved after the standard turnaround time.

Q: How long does an update normally take?
A: Online demographic updates are typically processed within a few days to a few weeks
after document verification; biometric updates done at a centre can take longer if flagged
for manual quality review. Track status using the URN on the UIDAI website.

Q: What if my Aadhaar is locked, or biometric authentication keeps failing?
A: Use the UIDAI portal or mAadhaar app to unlock/lock biometrics, or visit an Aadhaar
Seva Kendra to update biometrics if repeated authentication failures affect a benefit
(e.g. bank KYC, PDS ration, EPFO withdrawal) — carry proof of the failed transaction.

Q: Where do I escalate persistent Aadhaar-linked benefit denial (e.g. ration, bank KYC)?
A: First raise it with the service provider (bank/ration dealer) referencing UIDAI's
Aadhaar (Targeted Delivery of Financial and Other Subsidies, Benefits and Services) Act,
2016 provision that exact biometric match is not the sole ground for denial of a service —
alternate means of identification must be offered. If refused, escalate via CPGRAMS.
""",
    },
    {
        "folder": "faqs", "filename": "pan_correction_faqs.txt",
        "title": "PAN Application & Correction FAQs", "authority": "Income Tax Dept / Protean (NSDL)",
        "category": "faq",
        "content": """
PAN CARD APPLICATION & CORRECTION — FREQUENTLY ASKED QUESTIONS

Q: How do I apply for a new PAN or correct an existing PAN?
A: Apply online via the Protean (formerly NSDL) e-Gov portal or UTIITSL, or via the Income
Tax Department's e-filing portal for Instant e-PAN (Aadhaar-based, for those without an
existing PAN). Corrections (name, date of birth, address, photo, signature) use Form
"Request for New PAN Card or/and Changes or Correction in PAN Data".

Q: My PAN correction has been pending for a long time — what should I do?
A: 1) Track status using the 15-digit acknowledgement number on the Protean/UTIITSL portal.
   2) If stuck at "under process" beyond the normal processing window, raise a service
      request/grievance on the Protean portal or Income Tax e-filing helpdesk.
   3) If a document was rejected, resubmit with a clear, current, name-matching document
      (PAN correction is one of the most common rejections due to name-format mismatches
      between supporting documents).
   4) Escalate unresolved cases via CPGRAMS against the Income Tax Department / CBDT.

Q: I have two PAN numbers by mistake — is that a problem?
A: Yes — holding more than one PAN is against Section 139A of the Income Tax Act, 1961,
and can attract a penalty. Surrender the duplicate/incorrect PAN using the correction
form, clearly stating the PAN to be retained and the PAN(s) to be deactivated.

Q: My PAN is not linked to Aadhaar / my PAN has become inoperative — what next?
A: PAN-Aadhaar linking is mandatory for most taxpayers; an unlinked PAN becomes
inoperative, which blocks TDS credit, refunds, and some banking/KYC processes. Link PAN
and Aadhaar via the Income Tax e-filing portal (fee applies where linking is delayed) and
allow processing time before retrying the blocked transaction.

Q: Where do I escalate if a bank or employer refuses a valid PAN?
A: First request the specific rejection reason in writing; most refusals are name-format
mismatches with the PAN database. If the PAN is correct and still refused, escalate to the
Income Tax Department's grievance cell or CPGRAMS with supporting proof.
""",
    },
    {
        "folder": "faqs", "filename": "driving_licence_faqs.txt",
        "title": "Driving Licence & Vehicle Services FAQs", "authority": "MoRTH / Parivahan",
        "category": "faq",
        "content": """
DRIVING LICENCE & VEHICLE SERVICES — FREQUENTLY ASKED QUESTIONS

Q: What is the process to get a driving licence?
A: 1) Apply for and pass the Learner's Licence (LL) test (online theory test in most
      states) — LL is valid for 6 months.
   2) After a minimum gap (commonly 30 days) and before LL expiry, apply for the
      Permanent Driving Licence (DL) and pass the practical driving test at the RTO,
      or via a certified driving training school under the voluntary exemption scheme.
   3) The DL is issued/dispatched, and status can be tracked on the Parivahan portal
      using the application number.

Q: My driving licence application/test has been stalled or repeatedly rescheduled — what
   can I do?
A: 1) Check application status on the Parivahan Sewa portal (parivahan.gov.in).
   2) Contact the specific RTO's grievance cell or helpline for the reason (common causes:
      slot backlog, Aadhaar e-KYC mismatch, document verification pending).
   3) If unresolved beyond a reasonable period, file a grievance via CPGRAMS against the
      state Transport Department / Ministry of Road Transport and Highways (MoRTH).

Q: My learner's licence expired before I could book the permanent DL test — now what?
A: A fresh LL application is generally required once the 6-month validity lapses; check
   your state RTO's current policy on whether a grace-period re-test or fresh LL fee
   applies, since this varies by state.

Q: How do I dispute an incorrect entry on my DL (wrong vehicle class, wrong address, wrong
   DOB) or an incorrectly imposed penalty/blacklist flag?
A: File a correction request at the issuing RTO with supporting documents; if the RTO
   does not act, escalate to the Regional Transport Commissioner and then to CPGRAMS
   against the state Transport Department.

Q: What about vehicle registration (RC) delays or transfer-of-ownership disputes?
A: Vehicle registration and RC transfer are also handled through Parivahan/Vahan; track
   status by application number, follow up with the registering RTO, and escalate
   unresolved delays the same way (RTO -> Transport Commissioner -> CPGRAMS).
""",
    },
    {
        "folder": "faqs", "filename": "cpgrams_rti_faqs.txt",
        "title": "CPGRAMS Escalation & RTI Filing FAQs", "authority": "DARPG / RTI Online",
        "category": "faq",
        "content": """
PUBLIC GRIEVANCE (CPGRAMS) & RTI — FREQUENTLY ASKED QUESTIONS

Q: What is CPGRAMS?
A: The Centralized Public Grievance Redress and Monitoring System (CPGRAMS) is the
online platform, run by the Department of Administrative Reforms and Public Grievances
(DARPG), through which citizens can lodge grievances against any central government
ministry, department, or linked public authority — including UIDAI, Income Tax, Passport
Seva/MEA, Parivahan-linked transport departments, and pension bodies like EPFO.

Q: How does CPGRAMS escalation work?
A: 1) File the grievance on pgportal.gov.in with the relevant department/ministry and a
      clear factual description, attaching supporting documents.
   2) The grievance is forwarded to the concerned department's Nodal Grievance Officer.
   3) Departments are expected to redress within a defined window (commonly cited as
      around 21 working days under DARPG guidelines); status can be tracked with the
      registration number.
   4) If unsatisfied with the resolution, the citizen can request an "Appeal" within
      CPGRAMS, which routes the grievance to the next-higher appellate authority.
   5) Persistent or systemic issues can also be raised with the Central/State
      Information Commission (via RTI) or the relevant Ombudsman/regulator.

Q: What is RTI and how do I file an RTI request?
A: The Right to Information Act, 2005 lets any citizen request information held by a
   public authority. File online at rtionline.gov.in (for central government bodies) or
   the applicable state RTI portal, addressed to the Public Information Officer (PIO) of
   the concerned department, with the prescribed fee (commonly INR 10 for central
   applications; fee-exempt for BPL applicants).

Q: How long does a public authority have to respond to an RTI request?
A: The statutory response window under the RTI Act is 30 days from receipt (reduced to
   48 hours for information concerning life or liberty). If the request is transferred to
   another public authority, the clock effectively restarts from the transfer, and total
   time can extend, though authorities are expected to inform the applicant promptly.

Q: The PIO did not respond or gave an unsatisfactory reply — what next?
A: File a First Appeal with the department's Appellate Authority within 30 days of the
   deadline/response. If still unresolved, file a Second Appeal with the Central/State
   Information Commission, which can also impose penalties on the PIO for unreasonable
   delay or refusal without valid grounds.

Q: When should I use CPGRAMS vs RTI?
A: Use CPGRAMS to get a pending service/application actually resolved (e.g. delayed
   certificate, stuck application). Use RTI when you specifically need official
   information/records (e.g. the exact status noting, the reason for rejection in
   writing, processing timelines) — the two can be used together, RTI often being the
   stronger tool when a department stays silent on a CPGRAMS grievance.
""",
    },
    # ── Grievance / complaint templates ──────────────────
    {
        "folder": "grievance_templates", "filename": "cpgrams_grievance_template.txt",
        "title": "CPGRAMS Public Grievance Filing Template", "authority": "DARPG",
        "category": "template",
        "content": """
CPGRAMS PUBLIC GRIEVANCE — FILING TEMPLATE

Ministry/Department: [e.g. Ministry of External Affairs / UIDAI / Income Tax Department]
Subject: Delay in [service name] — Reference/Application No. [xxxx]

Grievance Description:
"I submitted an application for [service, e.g. passport reissue / Aadhaar address update /
PAN correction / driving licence] on [date] bearing reference/application number [xxxx] at
[office/portal name]. As per the published service standard, this should be completed
within [timeline]. As of today, [number] days have passed without resolution or a
satisfactory explanation.

I have already followed up on [dates] via [phone/email/in-person] with [office name]
without success. I request that this grievance be examined and the pending
application/service be resolved at the earliest, and that I be informed of the specific
reason for the delay if one exists."

Documents to attach:
- Copy of the original application/acknowledgement receipt
- Any prior correspondence or follow-up reference numbers
- Proof of the service standard/timeline being breached (screenshot of official portal
  timeline, if available)

Escalation path if unresolved:
1. CPGRAMS grievance -> Nodal Officer of the department (initial disposal window).
2. CPGRAMS "Appeal" against an unsatisfactory resolution.
3. RTI request to the same department for the file noting/status, if administrative
   escalation stalls.
4. Where applicable, escalate to the sectoral ombudsman/appellate authority (e.g. State
   Information Commission for RTI, Transport Commissioner for RTO matters).
""",
    },
    {
        "folder": "grievance_templates", "filename": "rti_application_template.txt",
        "title": "RTI Application Template", "authority": "RTI Online",
        "category": "template",
        "content": """
RTI APPLICATION (Right to Information Act, 2005) — TEMPLATE

To,
The Public Information Officer (PIO),
[Name of Public Authority/Department]

Subject: Request for information under Section 6(1) of the RTI Act, 2005

I would like to request the following information regarding [application/service, e.g.
passport application file no. XXXX / Aadhaar update request URN XXXX / PAN correction
acknowledgement no. XXXX]:

1. Current status of the above-referenced application, and the date on which it is
   expected to be resolved.
2. If the application has been rejected or is on hold, the specific reason(s) for
   rejection/hold and the officer/section responsible for the decision.
3. Copies of any internal notings, communications, or verification reports (e.g. police
   verification report status) related to this application, to the extent disclosable
   under the RTI Act.
4. The name and designation of the officer currently handling this file.

I am enclosing the prescribed RTI application fee of INR 10 (or proof of BPL exemption).
Please provide the requested information within 30 days as mandated under Section 7(1) of
the RTI Act, 2005.

Applicant Name:
Address:
Contact Number / Email:
Date:

Note: If the PIO does not respond within 30 days, or the response is unsatisfactory, file
a First Appeal with the Appellate Authority of the same department within 30 days, and if
still unresolved, a Second Appeal with the Central/State Information Commission.
""",
    },
    {
        "folder": "grievance_templates", "filename": "certificate_delay_complaint_template.txt",
        "title": "Certificate Delay Complaint Template (Income/Caste/Birth/Death)", "authority": "State Revenue/Municipal Dept",
        "category": "template",
        "content": """
CERTIFICATE DELAY COMPLAINT TEMPLATE
(Income Certificate / Caste Certificate / Birth Certificate / Death Certificate)

To,
The [Tahsildar / Revenue Officer / Municipal Registrar / e-District Officer],
[Office name and jurisdiction]

Subject: Delay in issuance of [Income/Caste/Birth/Death] Certificate — Application No. [xxxx]

I applied for a [certificate type] on [date] through [CSC / e-District portal / Tahsil
office], application/reference number [xxxx]. The published service level for this
certificate under the [state] Right to Public Services / Sakala / e-District service
guarantee is [X] working days; more than [X] days have now elapsed.

I request that this application be processed immediately, or that I be given the specific
reason for the delay (e.g. field verification pending, document discrepancy) so that I
can address it promptly, as this certificate is required for [purpose, e.g. scholarship
application, court proceeding, welfare scheme enrolment].

Documents attached:
- Application acknowledgement / receipt
- Supporting documents originally submitted (proof of identity, residence, income/caste
  evidence, hospital/municipal birth-death intimation, as applicable)

Escalation path if unresolved:
1. Written follow-up to the issuing officer (Tahsildar/Registrar) referencing the
   applicable Right to Public Services Act service-level guarantee for the state, which
   in most states provides for a designated appellate authority and a penalty on the
   responsible official for unjustified delay.
2. First Appeal to the designated Appellate Authority under the state's service-delivery
   law (name varies by state: e.g. Right to Public Services Act, Sakala Act, e-District
   guarantee).
3. CPGRAMS grievance if the service is linked to a centrally monitored scheme, or the
   state's own online grievance portal for state-subject matters.
""",
    },
    {
        "folder": "grievance_templates", "filename": "pension_grievance_template.txt",
        "title": "Pension Grievance Template (EPFO / NPS)", "authority": "EPFO / PFRDA",
        "category": "template",
        "content": """
PENSION GRIEVANCE TEMPLATE (EPFO / NPS)

For EPFO (EPS-95 pension / PF withdrawal / transfer delays):
Subject: Grievance regarding [pension not credited / PF withdrawal delayed / transfer
claim pending] — UAN/PPO No. [xxxx]

"My [pension / PF withdrawal / transfer claim] under UAN/PPO number [xxxx] was submitted
on [date] and remains unresolved. [Describe: pension stopped without notice / withdrawal
claim rejected without clear reason / transfer claim pending beyond normal processing
time]. I request immediate review and resolution, and a written explanation if a rejection
is being upheld."

File via: EPFO Grievance Management System (EPFiGMS) or CPGRAMS against EPFO/Ministry of
Labour & Employment. Escalation: Regional PF Commissioner -> EPFO grievance cell ->
CPGRAMS appeal -> Central Provident Fund Commissioner.

For NPS (National Pension System, regulated by PFRDA):
Subject: Grievance regarding [NPS withdrawal delay / annuity not started / account
statement discrepancy] — PRAN [xxxx]

"My NPS account (PRAN [xxxx]) has an unresolved issue: [describe]. I request review and
resolution as per PFRDA's grievance redressal timelines."

File via: CRA (Central Recordkeeping Agency) grievance portal or PFRDA's grievance system;
escalate to PFRDA directly, or via CPGRAMS, if unresolved by the CRA/POP (Point of
Presence, e.g. the bank handling the NPS account).
""",
    },
    {
        "folder": "grievance_templates", "filename": "driving_licence_dispute_template.txt",
        "title": "Driving Licence Dispute / Delay Template", "authority": "MoRTH / State Transport Dept",
        "category": "template",
        "content": """
DRIVING LICENCE DISPUTE / DELAY COMPLAINT TEMPLATE

To,
The Regional Transport Officer (RTO), [office/jurisdiction],

Subject: [Delay in Learner's/Permanent Driving Licence issuance / Incorrect DL record] —
Application No. [xxxx]

"I applied for [Learner's Licence / Permanent Driving Licence / DL correction / RC
transfer] on [date], application number [xxxx]. [Describe the issue: test repeatedly
rescheduled beyond LL validity / documents verified but licence not dispatched / DL issued
with incorrect [name/DOB/vehicle class]/ vehicle transfer pending beyond normal
timeline]. I request immediate correction/completion of this application."

Escalation path if unresolved:
1. RTO grievance cell / helpline (in person or via the state transport department portal).
2. Regional Transport Commissioner (write formally, reference the application number and
   prior follow-ups).
3. CPGRAMS grievance against the state Transport Department / Ministry of Road Transport
   and Highways (MoRTH) for centrally-linked services (e.g. Parivahan/Sarathi portal
   issues).
4. RTI request to the RTO for the file status if the delay reason is unclear.
""",
    },
    {
        "folder": "grievance_templates", "filename": "property_registration_delay_template.txt",
        "title": "Property Registration Delay Complaint Template", "authority": "State Registration/Stamps Dept",
        "category": "template",
        "content": """
PROPERTY REGISTRATION DELAY COMPLAINT TEMPLATE

To,
The Sub-Registrar, [office/jurisdiction],

Subject: Delay in registration of [Sale Deed / Gift Deed / Mortgage / Lease] — Document
No. [xxxx] / Token No. [xxxx]

"I submitted a document for registration on [date], token/document number [xxxx], at your
office under the Registration Act, 1908. [Describe the issue: registration slot
repeatedly unavailable / document held for verification beyond the normal window /
mutation/encumbrance certificate not updated after registration]. I request that this be
processed and, if there is a specific defect requiring correction, that I be informed in
writing so I can rectify it promptly."

Escalation path if unresolved:
1. Written follow-up to the Sub-Registrar with the token/document number.
2. Escalate to the District Registrar / Inspector General of Registration for the state.
3. State grievance portal or CPGRAMS (for centrally-linked digital registration/e-Stamp
   issues) or the state's own e-service grievance module if property registration is
   handled through a state e-governance platform.
4. For mutation (Record of Rights) delays after registration, escalate separately to the
   Tahsildar/local revenue authority responsible for updating land records.
""",
    },
    # ── Certificates guides ───────────────────────────────
    {
        "folder": "certificates", "filename": "income_certificate_guide.txt",
        "title": "Income Certificate — Process & Delay Guide", "authority": "State Revenue Department",
        "category": "guide",
        "content": """
INCOME CERTIFICATE — PROCESS & DELAY RESOLUTION GUIDE

What it is: An Income Certificate is issued by the state Revenue Department (via
Tahsildar/Revenue Officer or an e-District/CSC portal) certifying a person's or family's
annual income, commonly required for scholarships, fee concessions, reservation-linked
benefits, and welfare scheme eligibility.

Typical process:
1. Apply online via the state's e-District/Seva portal (or offline at the Tahsil office)
   with supporting documents: identity proof, residence proof, salary slips / Form 16 /
   self-employment income declaration, and often a local enquiry/verification by a
   Revenue Inspector or Village Administrative Officer.
2. Field verification is the most common source of delay.
3. Certificate is digitally signed and issued; most states also make it available/
   verifiable via DigiLocker.

If delayed beyond the state's published service-level timeline (commonly a few days to
2-3 weeks depending on the state's Right to Public Services / Sakala-type law):
1. Check status online using the application/acknowledgement number.
2. Follow up in writing with the Tahsildar/Revenue Officer citing the service-level
   guarantee and the number of days elapsed.
3. File a First Appeal with the designated Appellate Authority under the state's
   service-delivery law.
4. If the delay is due to field verification being stuck, directly contact the assigned
   Village Administrative Officer / Revenue Inspector for the enquiry status.
5. Escalate via the state grievance portal, or CPGRAMS if the service is centrally linked.
""",
    },
    {
        "folder": "certificates", "filename": "caste_certificate_guide.txt",
        "title": "Caste Certificate — Process & Delay Guide", "authority": "State Revenue/Social Welfare Department",
        "category": "guide",
        "content": """
CASTE CERTIFICATE — PROCESS & DELAY RESOLUTION GUIDE

What it is: A Caste Certificate is issued by the Revenue Department or the Social Welfare
Department (varies by state) certifying that a person belongs to a Scheduled Caste (SC),
Scheduled Tribe (ST), Other Backward Class (OBC), or a state-specific category, commonly
required for education admissions, reservations in employment, and scheme eligibility.

Typical process:
1. Apply via the state e-District/Seva portal or the Tahsil/Taluk office with supporting
   documents: identity/residence proof and, most importantly, documentary evidence of
   caste status (e.g. a parent's or ancestor's caste certificate, school records, or
   community/gazette references establishing lineage).
2. Field/community verification by the Revenue Inspector or Village Administrative
   Officer is typically required and is the most common source of delay, especially where
   old ancestral records must be traced.
3. In many states, a Scrutiny Committee reviews SC/ST/OBC certificates for genuineness,
   which adds processing time, particularly near admission/exam deadlines.

If delayed beyond the state's published timeline:
1. Check application status online; identify whether the delay is at the verification
   stage or the scrutiny/approval stage.
2. Submit any additional supporting lineage documents proactively if verification is
   stuck on evidence gaps.
3. Escalate in writing to the Tahsildar/Revenue Divisional Officer, citing the applicable
   state service-guarantee law and the elapsed time.
4. File a First Appeal under the state's Right to Public Services-type law if unresolved.
5. For time-critical needs (admission/exam deadlines), request a provisional/interim
   certificate where the state's rules allow one, explicitly citing the deadline.
6. Escalate persistent delay via the state grievance portal or CPGRAMS.
""",
    },
    {
        "folder": "certificates", "filename": "birth_death_certificate_guide.txt",
        "title": "Birth & Death Certificate — Process & Delay Guide", "authority": "Municipal/Panchayat Registrar (RBD Act, 1969)",
        "category": "guide",
        "content": """
BIRTH & DEATH CERTIFICATE — PROCESS & DELAY RESOLUTION GUIDE

Legal basis: Registration of Births and Deaths (RBD) Act, 1969 requires every birth and
death to be registered with the local Registrar (municipal corporation, municipality, or
gram panchayat) within 21 days of occurrence, most commonly via intimation from the
hospital or institution where the event occurred.

Typical process:
1. Hospitals/institutions typically forward birth/death intimation to the local Registrar
   directly; the certificate can then be obtained online (via the state's Civil
   Registration System / CRS portal, and often DigiLocker) or at the municipal office.
2. Registration after 21 days but within 30 days requires a late fee; registration after
   1 year requires a magistrate/designated officer's order and an affidavit — this is the
   most common cause of long delays.
3. Corrections to a certificate (name, spelling, date, gender) require a separate
   correction application with supporting documents (often including an affidavit and, in
   some states, a Gazette publication for name changes).

If delayed or a correction request is stuck:
1. Check status via the CRS portal (crsorgi.gov.in / state equivalent) using the
   registration/application number.
2. If the delay is because the original hospital/institution never filed intimation,
   contact the hospital's medical records department and the Registrar together — this is
   the most common root cause for "birth not registered" cases.
3. For registrations delayed beyond 1 year, prepare the required affidavit and approach
   the designated officer (often the local Executive Magistrate/Tahsildar) for the
   condonation order needed to register late.
4. Escalate unresolved delays to the Municipal Commissioner's office or the state's Chief
   Registrar (Births & Deaths), and via CPGRAMS/state grievance portal if still unresolved.
""",
    },
    # ── Land records ──────────────────────────────────────
    {
        "folder": "land_records", "filename": "property_registration_guide.txt",
        "title": "Property Registration & Land Records — Process & Delay Guide", "authority": "State Registration/Revenue Department",
        "category": "guide",
        "content": """
PROPERTY REGISTRATION & LAND RECORDS — PROCESS & DELAY RESOLUTION GUIDE

Legal basis: Property transactions (sale, gift, mortgage, lease above a threshold term)
are registered under the Registration Act, 1908 at the jurisdictional Sub-Registrar
Office (SRO), with stamp duty governed by the applicable state Stamp Act. Land ownership
records (Record of Rights / 7/12 extract / Khatauni / Patta, depending on the state) are
separately maintained by the Revenue Department and updated via "mutation" after a
registered transaction.

Typical process:
1. Compute and pay stamp duty (often via e-Stamping) and registration fee.
2. Book a registration slot/token at the SRO (many states now do this online).
3. Both parties (and witnesses) appear at the SRO for biometric verification and document
   execution; the registered document is returned digitally signed/scanned.
4. Separately, apply for "mutation" with the Revenue Department/Tahsildar so the Record of
   Rights reflects the new owner — registration alone does NOT automatically update land
   records in every state.

Common delay points and what to do:
1. Registration slot backlog: check the SRO's online booking system for the next
   available slot; escalate to the District Registrar if slots are unavailable for an
   unreasonably long period.
2. Document held for verification (title doubt, encumbrance flag, valuation mismatch):
   request the specific defect in writing so it can be rectified; unresolved valuation
   disputes can be escalated to the Collector (stamp duty valuation appeal process).
3. Mutation delay after registration: follow up directly with the Tahsildar/Revenue
   Inspector responsible for updating the Record of Rights — this is a distinct process
   from registration and is a very common point of citizen complaint.
4. Escalation path: Sub-Registrar -> District Registrar / Inspector General of
   Registration -> state grievance portal / CPGRAMS (for centrally-linked digital/e-Stamp
   platforms) -> RTI request for the file status if the reason for delay is unclear.
""",
    },
    # ── Pensions ────────────────────────────────────────
    {
        "folder": "pensions", "filename": "pension_grievance_guide.txt",
        "title": "Pension Grievance — EPFO & NPS Guide", "authority": "EPFO / PFRDA",
        "category": "guide",
        "content": """
PENSION GRIEVANCES — EPFO & NPS RESOLUTION GUIDE

EPS-95 / EPFO pension and PF:
1. Pension not credited: verify the Pension Payment Order (PPO) number and bank account
   seeding on the EPFO member portal; a common cause is a bank account/KYC mismatch after
   a bank merger or account closure.
2. PF withdrawal or transfer claim delayed/rejected: check claim status on the EPFO
   Unified Portal using the UAN; rejections are frequently due to KYC (Aadhaar/PAN/bank)
   not being verified/seeded, or employer not approving the digital signature on the exit
   date.
3. Escalation path: Employer's HR/PF section (to confirm KYC/exit approval) -> EPFO
   Regional Office grievance cell / EPFiGMS (EPF i-Grievance Management System) -> CPGRAMS
   against EPFO/Ministry of Labour & Employment -> Central Provident Fund Commissioner
   for unresolved systemic issues.

NPS (National Pension System), regulated by PFRDA:
1. Withdrawal/annuity not started: NPS exit requires online submission plus, above a
   threshold corpus, mandatory annuity purchase from an empanelled insurer — delays are
   often at the annuity service provider stage, not the CRA (Central Recordkeeping
   Agency) stage.
2. Contribution/statement discrepancy: verify contributions were correctly uploaded by
   the nodal office/employer or POP (Point of Presence, typically a bank) handling the
   NPS account; mismatches are frequently a POP-side upload error.
3. Escalation path: POP/bank NPS desk -> CRA grievance portal -> PFRDA grievance
   redressal system directly, or via CPGRAMS if the POP is a government-linked entity.

General tip: For any pension grievance, always retain the acknowledgement/reference
number for every step (claim ID, PPO number, UAN, PRAN) — resolution timelines are
tracked against these reference numbers, and CPGRAMS/EPFiGMS escalations require them.
""",
    },
    # ── State services ──────────────────────────────────
    {
        "folder": "state_services", "filename": "state_citizen_service_portals.txt",
        "title": "State Government Citizen Service Portals — Overview", "authority": "Various State Governments",
        "category": "reference",
        "content": """
STATE GOVERNMENT CITIZEN SERVICE PORTALS — OVERVIEW

Most Indian states run their own single-window e-Governance portal (often called an
"e-District" implementation) bundling certificates, licences, and utility services
alongside the central portals (UIDAI, Passport Seva, Parivahan, RTI Online) already
covered in this knowledge base. Because these are state-subject services, exact workflows,
fees, and turnaround times vary by state; the pattern below generalizes across the major
implementations so a case can be routed correctly even without a state-specific scrape:

- Tamil Nadu: e-Sevai centres / TNeGA portal — certificates, revenue services, and
  utility bill services bundled under one CSC-style front end.
- Andhra Pradesh / Telangana: MeeSeva — one of the earliest and most widely cited
  e-District implementations, covering certificates, licences, and welfare scheme
  applications.
- Maharashtra: Aaple Sarkar (RTS Act-backed) — publishes explicit service-level
  timelines per service with a designated first/second appellate authority for delay.
- Karnataka: Seva Sindhu — integrated citizen services portal.
- Delhi: e-District Delhi — certificates and Delhi-specific welfare/utility services.
- Most other states run an equivalent "e-District" or "Seva Kendra" branded portal under
  the central Digital India / e-District Mission Mode Project framework.

Common structural pattern across all state portals:
1. Application filed online (or via a Common Service Centre / CSC for citizens without
   internet access), generating a tracked application/token number.
2. Field verification (where required) by a local revenue/municipal officer.
3. A published service-level timeline exists under most states' Right to Public
   Services Act (RTS Act) or equivalent — commonly ranging from a few days for simple
   certificates to a few weeks for verification-heavy services.
4. A statutory appellate mechanism exists for delay/refusal: a First Appellate Authority
   at the district level, and often a Second Appellate Authority / RTS Commission with
   powers to penalize the responsible official for unjustified delay.

Recommended routing when the user's state is known: identify whether the state has an
RTS/Sakala-type law (most do), cite the specific service-level guarantee and appellate
authority, and treat CPGRAMS as the fallback national-level escalation channel for any
centrally-linked component of the service (e.g. Aadhaar-based e-KYC failures, DigiLocker
issuance) even when the underlying service itself is a state subject.
""",
    },
    # ── Schemes ────────────────────────────────────────
    {
        "folder": "schemes", "filename": "government_schemes_overview.txt",
        "title": "Common Government Welfare Schemes — Grievance-Relevant Overview", "authority": "Various Ministries",
        "category": "reference",
        "content": """
COMMON GOVERNMENT WELFARE SCHEMES — GRIEVANCE-RELEVANT OVERVIEW

This is a short reference for the welfare-scheme disputes citizens most commonly bring to
a grievance/consumer-rights assistant, alongside the identity/certificate/pension topics
already covered:

- Public Distribution System (PDS) / Ration Card: disputes usually involve ration card
  not linked to Aadhaar, entitlement denied at the Fair Price Shop despite a valid card,
  or a name wrongly deleted during a de-duplication drive. Escalate to the local Food &
  Civil Supplies office, then the district Food Controller, then the state consumer/
  grievance portal or CPGRAMS for centrally-linked components (e.g. One Nation One Ration
  Card portability failures).
- Atal Pension Yojana (APY) / other PFRDA-linked schemes: see pensions/
  pension_grievance_guide.txt for the NPS/PFRDA escalation path, which also applies to APY
  contribution and payout disputes.
- Ayushman Bharat / state health schemes: hospital empanelment or claim-denial disputes
  should be escalated to the scheme's State Health Agency grievance cell, with CPGRAMS as
  the fallback for the central National Health Authority component.
- Direct Benefit Transfer (DBT) failures: most DBT failures trace back to an Aadhaar
  seeding/bank-linking mismatch — see faqs/aadhaar_update_faqs.txt for the standard
  resolution path before escalating to the specific scheme's nodal ministry.

For any scheme not explicitly covered here, the same general escalation pattern applies:
implementing department/agency -> scheme's own grievance cell (if one exists) ->
CPGRAMS against the nodal ministry -> RTI request for the specific rejection/eligibility
reasoning if the department stays silent.
""",
    },
]


def main():
    print("=" * 60)
    print("GOVERNMENT DOMAIN — AUTHORED KNOWLEDGE SEEDING")
    print("=" * 60)
    for doc in DOCUMENTS:
        save(doc["folder"], doc["filename"], doc["title"], doc["authority"], doc["category"], doc["content"])
    print(f"Done. Wrote {len(DOCUMENTS)} authored documents.")


if __name__ == "__main__":
    main()
