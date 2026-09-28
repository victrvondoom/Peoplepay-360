"""
Housing Domain - Authored Grievance Content Seeder
Complaint templates and FAQs grounded in the real RERA Act 2016 text and
state RERA/registration portals just downloaded.
"""
import json
from pathlib import Path

KNOWLEDGE_ROOT = Path(__file__).resolve().parents[2] / "knowledge" / "housing"


def save(folder, filename, title, authority, category, content):
    dest_dir = KNOWLEDGE_ROOT / folder
    dest_dir.mkdir(parents=True, exist_ok=True)
    filepath = dest_dir / filename
    filepath.write_text(content.strip() + "\n", encoding="utf-8")
    meta_dir = KNOWLEDGE_ROOT / "metadata" / folder
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / f"{Path(filename).stem}.json").write_text(
        json.dumps({"title": title, "authority": authority, "source_url": None,
                    "domain": "housing", "type": "authored_guide", "category": category},
                   indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"  wrote {filepath.relative_to(KNOWLEDGE_ROOT)}")


DOCUMENTS = [
    # ── RERA / builder ────────────────────────────────────
    {
        "folder": "complaint_templates", "filename": "rera_delayed_possession_complaint.txt",
        "title": "RERA Delayed Possession Complaint Template", "authority": "RERA Act 2016",
        "category": "template",
        "content": """
RERA DELAYED POSSESSION COMPLAINT TEMPLATE

Legal basis: Under Section 18 of the Real Estate (Regulation and
Development) Act, 2016, if a promoter (builder) fails to complete or is
unable to give possession of an apartment/plot/building by the date
stated in the registered agreement for sale, the allottee has the right
to either withdraw from the project and get a full refund with interest,
or stay in the project and claim interest for every month of delay until
possession is handed over — the allottee's choice, not the builder's.

File at: the State RERA Authority where the project is registered (e.g.
MahaRERA, TN RERA, Karnataka RERA — search the project's RERA registration
number on the state portal first to confirm jurisdiction and registered
possession date).

Complaint content:
"I am an allottee in [Project Name], RERA registration number [xxxx],
having booked Unit No. [xxxx] on [booking date]. The agreement for sale
dated [date] states a possession date of [date], which has now been
delayed by [X months/years]. I request [a full refund of the amount paid
with interest under Section 18 / interest for every month of delay while
I continue to hold the unit], along with compensation for the delay as
provided under the Act."

Documents to attach: Agreement for sale/allotment letter, payment
receipts, registered project's RERA number, any builder correspondence
about the delay.

Escalation path:
1. State RERA Authority complaint (adjudicating officer) — this is a
   quasi-judicial body, complaints are typically disposed of within 60 days
   as targeted under the Act.
2. Appeal to the state's Real Estate Appellate Tribunal against a RERA
   order, within 60 days of the order.
3. Consumer forum (District/State Commission) remains an alternate/parallel
   remedy for deficiency in service and compensation, though RERA is the
   specialized forum for project-registration-linked disputes.
""",
    },
    {
        "folder": "complaint_templates", "filename": "defective_construction_complaint.txt",
        "title": "Defective Construction / Structural Defect Complaint Template", "authority": "RERA Act 2016",
        "category": "template",
        "content": """
DEFECTIVE CONSTRUCTION COMPLAINT TEMPLATE

Legal basis: Section 14(3) of the RERA Act, 2016 makes the promoter liable,
without further compensation, to rectify structural defects or any other
defects in workmanship, quality, or provision of services, brought to
notice within 5 years of handing over possession — the promoter must
rectify such defects within 30 days at no cost to the allottee.

To,
The Promoter, [Builder/Project Name]
CC: State RERA Authority

Subject: Structural/quality defect notice under Section 14(3) RERA Act,
2016 — Unit [xxxx], possession date [date]

"I took possession of Unit [xxxx] in [Project Name] on [date]. I am
noticing the following defect(s): [describe — e.g. seepage/leakage,
cracks in walls, faulty plumbing/electrical, substandard flooring
material]. Under Section 14(3) of the RERA Act, I request rectification
within 30 days at no cost, as this is within the 5-year defect liability
period from possession."

If the builder does not rectify within 30 days:
File a complaint with the State RERA Authority citing the Section 14(3)
notice date and the builder's non-response/refusal, requesting a direction
to rectify or compensate for independent rectification cost.
""",
    },
    {
        "folder": "complaint_templates", "filename": "occupancy_completion_certificate_delay.txt",
        "title": "Occupancy/Completion Certificate Delay Complaint Template", "authority": "RERA Act 2016 / Local Body",
        "category": "template",
        "content": """
OCCUPANCY / COMPLETION CERTIFICATE DELAY COMPLAINT TEMPLATE

Background: A Completion Certificate (CC) confirms the building was
constructed per the sanctioned plan; an Occupancy Certificate (OC)
certifies the building is fit for occupation (water/electricity/fire
safety compliance). Under RERA, the promoter must obtain the OC/CC before
handing over possession — possession without a valid OC is itself a RERA
violation, and buyers should not be pressured to take possession or pay
final dues without it.

To,
The Promoter, [Builder/Project Name]
CC: State RERA Authority; [Municipal Corporation / Local Planning Authority]

Subject: Occupancy Certificate not obtained — Project [Name], RERA
registration [xxxx]

"Possession of Unit [xxxx] was offered on [date] without a valid
Occupancy Certificate. I request either the OC be produced immediately,
or, per RERA Section 18 read with the possession obligations, [a refund
with interest / compensation for the delay] since possession without OC
does not constitute valid, lawful possession under the Act."

Escalation path:
1. State RERA Authority — OC non-compliance is a direct, checkable
   violation against the project's registered details.
2. Local Municipal Corporation / Development Authority (which actually
   issues the OC/CC) — a parallel complaint about non-issuance can reveal
   whether the builder never applied, or the application is pending for a
   specific deficiency (fire NOC, structural certificate, etc.) — useful to
   know before pressing RERA for a refund vs. waiting for OC.
""",
    },
    # ── Rental / landlord-tenant ───────────────────────────
    {
        "folder": "complaint_templates", "filename": "security_deposit_refund_complaint.txt",
        "title": "Security Deposit Refund Complaint Template", "authority": "Rental Agreement / Model Tenancy Act",
        "category": "template",
        "content": """
SECURITY DEPOSIT REFUND COMPLAINT TEMPLATE

Background: Security deposit terms are primarily governed by the rental/
lease agreement itself, and by state-specific Rent Control Acts or (in
states that have adopted it) the Model Tenancy Act, 2021 framework, which
recommends deposits be capped (commonly 2 months' rent for residential,
higher for commercial) and refunded within a defined window (commonly
cited as within 1 month) of the tenant vacating, net only of legitimately
documented deductions (unpaid rent/utilities, damage beyond normal wear
and tear — not routine wear and tear itself).

To,
[Landlord Name]

Subject: Refund of security deposit — Property [address], tenancy ended
[date]

"I vacated the above property on [date] having given the notice required
under our rental agreement, and handed over the property in the condition
agreed (accounting for normal wear and tear). I have not received my
security deposit of INR [amount] as of today, [X] days after vacating. I
request the deposit be refunded within [7/15] days, with an itemized
statement of any deductions you believe are due, failing which I will
pursue this through [the Rent Authority / Consumer Court / Civil Court as
applicable in my state]."

Escalation path (varies by state — check whether your state has adopted
the Model Tenancy Act with a Rent Authority):
1. States with a Rent Authority / Rent Court under an adopted Model
   Tenancy Act framework: file there — a faster, purpose-built forum for
   exactly this dispute.
2. Otherwise: a written notice, then a civil suit for recovery of the
   deposit (small claims-style track in many states' civil courts), or a
   consumer complaint if the tenancy is characterized as a "service" under
   your state's interpretation.
3. Keep move-in/move-out photos and the signed agreement — deposit
   disputes are decided almost entirely on documented condition evidence.
""",
    },
    {
        "folder": "complaint_templates", "filename": "landlord_tenant_dispute_template.txt",
        "title": "General Landlord-Tenant Dispute Template", "authority": "Rental Agreement / State Rent Laws",
        "category": "template",
        "content": """
LANDLORD-TENANT DISPUTE TEMPLATE (General)

Common dispute types: illegal lock-out/eviction without notice, refusal to
carry out agreed repairs, unauthorized entry, rent hike beyond the
agreement's escalation clause, refusal to provide a rent receipt (needed
for HRA tax claims), or a tenant's non-payment/property misuse from the
landlord's side.

To,
[Landlord Name / Tenant Name]

Subject: [Describe the specific dispute] — Property [address], agreement
dated [date]

"[State the issue factually, quote the relevant clause of the rental
agreement if one governs it, and state the specific remedy sought — e.g.
restoration of access, completion of the agreed repair by a date, a rent
receipt for the stated period, or reversal of a rent increase inconsistent
with the agreement.]"

Key legal notes:
- Illegal eviction (changing locks, cutting utilities without a court
  order) is not permitted even for non-payment — the landlord must go
  through the proper legal process (notice + court/Rent Authority order).
- A tenant generally cannot be evicted purely at the landlord's will
  during a fixed-term lease absent a breach specified in the agreement.

Escalation path:
1. Written notice citing the specific agreement clause breached.
2. State Rent Authority/Rent Court (where the Model Tenancy Act framework
   has been adopted) — otherwise, a civil suit for injunction/possession/
   damages as applicable, or police assistance for immediate illegal
   lock-out/harassment situations.
""",
    },
    # ── Society / maintenance ──────────────────────────────
    {
        "folder": "complaint_templates", "filename": "illegal_maintenance_charges_complaint.txt",
        "title": "Illegal/Excessive Maintenance Charges Complaint Template", "authority": "Society Bye-laws / RERA",
        "category": "template",
        "content": """
ILLEGAL / EXCESSIVE MAINTENANCE CHARGES COMPLAINT TEMPLATE

Background: Maintenance charges must be levied per the society's/RWA's
approved bye-laws and, before a formal society is registered/handed over,
per the RERA-registered project's disclosed maintenance terms — a builder
cannot unilaterally impose charges outside what was disclosed at booking,
and cannot condition possession/OC handover on payment of disputed
"corpus fund" or maintenance amounts not agreed in the sale agreement.

To,
[Builder/Management Committee/RWA]

Subject: Dispute of maintenance charges — Unit [xxxx], [Project/Society
Name]

"I am being charged INR [amount] as [maintenance/corpus fund/other
charge], which [was not disclosed in my agreement for sale / exceeds the
rate approved by the society's general body / is being demanded as a
condition for possession or OC, which is impermissible]. I request an
itemized break-up of this charge and its basis in the bye-laws or my
agreement, and a review of the amount."

Escalation path:
1. Society/RWA general body / managing committee (request an audited
   account of maintenance fund utilization if the dispute is about
   reasonableness, not just disclosure).
2. State Registrar of Cooperative Societies (for registered societies) —
   handles disputes about bye-law violations, unauthorized charges, and
   managing committee conduct.
3. State RERA Authority if the dispute concerns a builder-controlled
   maintenance regime before formal society handover, or possession/OC
   being conditioned on disputed charges.
4. Consumer forum for deficiency-in-service claims once other channels are
   exhausted.
""",
    },
    {
        "folder": "complaint_templates", "filename": "society_noc_denial_complaint.txt",
        "title": "Society NOC Denial Complaint Template", "authority": "Society Bye-laws / Cooperative Societies Act",
        "category": "template",
        "content": """
SOCIETY NOC DENIAL COMPLAINT TEMPLATE

Background: A housing society's No Objection Certificate (NOC) is
typically required for resale, renting out a unit, availing a home loan
against the property, or certain renovations. A managing committee cannot
deny an NOC arbitrarily or on grounds outside the society's registered
bye-laws (e.g. personal disputes, pending but disputed dues, discriminatory
grounds) — most Cooperative Societies Acts require a decision within a
defined time and permit appeal to the Registrar.

To,
The Secretary / Managing Committee, [Society Name]

Subject: NOC request for [sale / rental / loan / renovation] — Unit
[xxxx] — request for written reasons for denial/delay

"I applied for an NOC for [purpose] on [date] and have not received a
response / received a denial on grounds of [state reason given, if any].
I request the NOC be issued, or, if there is a genuine outstanding due or
bye-law violation, a written statement of the specific amount/violation so
I can resolve it."

Escalation path:
1. Society general body (request the matter be placed on the agenda if
   the managing committee is unresponsive).
2. State Registrar of Cooperative Societies — has statutory power to
   direct a society to act per its bye-laws and the state Cooperative
   Societies Act; most states have a defined appeal/complaint process here.
3. Consumer forum if the NOC refusal causes quantifiable loss (e.g. a lost
   sale/loan due to delay).
""",
    },
    # ── Property registration / tax ────────────────────────
    {
        "folder": "complaint_templates", "filename": "property_registration_delay_complaint.txt",
        "title": "Property Registration Delay Complaint Template", "authority": "Registration Act 1908 / State Registration Dept",
        "category": "template",
        "content": """
PROPERTY REGISTRATION DELAY COMPLAINT TEMPLATE

To,
The Sub-Registrar, [office/jurisdiction]

Subject: Delay in registration of [Sale Deed/Gift Deed] — Document/Token
No. [xxxx]

"I submitted a document for registration on [date], token/document number
[xxxx]. [Describe: registration slot unavailable for an extended period /
document held for verification without written reason / encumbrance
certificate or mutation not updated after registration]. I request this
be processed, and if there is a specific defect, that I be informed in
writing so I can rectify it."

Escalation path:
1. Sub-Registrar -> District Registrar / Inspector General of Registration.
2. State e-governance grievance portal for the registration department
   (e.g. TNREGINET grievance module, Kaveri Karnataka helpdesk) if the
   delay is a portal/technical issue rather than a documentary one.
3. For mutation (Record of Rights update) delays after registration, a
   SEPARATE follow-up with the Tahsildar/local revenue authority is
   usually required — registration and mutation are different processes.
""",
    },
    {
        "folder": "complaint_templates", "filename": "encumbrance_certificate_guidance.txt",
        "title": "Encumbrance Certificate Guidance", "authority": "State Registration Dept",
        "category": "guide",
        "content": """
ENCUMBRANCE CERTIFICATE (EC) — GUIDANCE

What it is: An Encumbrance Certificate confirms whether a property is
free of registered legal/monetary liabilities (mortgages, liens, prior
sales) over a specified period — essential before buying property or
availing a home loan against it, since lenders require a clean EC.

How to get one: Apply online via the state registration department's
portal (e.g. TNREGINET for Tamil Nadu, Kaveri Online for Karnataka) for
the specific survey number / property, specifying the period to be
searched (commonly 13, 15, or 30 years depending on the need — a home
loan lender may require a longer period than a simple resale check).

Common issues and fixes:
1. EC shows an entry that has actually been discharged (e.g. an old loan
   already closed): obtain a discharge/release deed or "no dues"
   certificate from the lender and get the registration department to
   note the discharge, or apply for a corrected EC referencing the
   discharge document's registration number.
2. EC application delayed beyond the portal's stated timeline: escalate
   via the registration department's grievance/helpdesk channel, citing
   the application number.
3. Property doesn't show up under the survey number searched: verify the
   correct current survey/sub-division number with the local Village
   Administrative Officer / Tahsildar — EC searches are only as good as
   the survey number used.
""",
    },
    {
        "folder": "complaint_templates", "filename": "property_tax_dispute_template.txt",
        "title": "Property Tax Dispute / Correction Template", "authority": "Municipal Corporation",
        "category": "template",
        "content": """
PROPERTY TAX DISPUTE / CORRECTION TEMPLATE

Common disputes: incorrect property classification (e.g. commercial rate
applied to a residential unit), incorrect built-up area used for
assessment, tax demand for a period the property was unoccupied/under
construction (often eligible for a lower rate), or a demand despite
having paid.

To,
The Revenue Officer / Commissioner, [Municipal Corporation]

Subject: Dispute of property tax assessment — Property ID/PID [xxxx]

"My property tax assessment for [year] shows [describe the error — wrong
classification, wrong area, wrong occupancy status, or a demand despite
payment receipt no. [xxxx]]. I request re-assessment/correction based on
[attach: sale deed showing actual classification, building plan showing
actual area, payment receipt, or occupancy timeline evidence]."

Escalation path:
1. Municipal Corporation Revenue/Tax department (most have an online
   correction/grievance module now).
2. Statutory appeal to the Municipal Commissioner or a dedicated Tax
   Appellate Tribunal where the municipal act provides one (varies by
   state/city — check your municipal corporation's specific appeal
   provision before the assessment year closes, as many have strict
   filing deadlines).
""",
    },
    # ── Home loan ──────────────────────────────────────────
    {
        "folder": "faqs", "filename": "home_loan_documentation_faqs.txt",
        "title": "Home Loan Documentation & Foreclosure FAQs", "authority": "RBI / Lenders",
        "category": "faq",
        "content": """
HOME LOAN DOCUMENTATION & FORECLOSURE — FAQs

Q: What documents does a bank typically need to sanction a home loan
   against an under-construction RERA project?
A: KYC + income documents, the builder-buyer agreement, the project's
   RERA registration number and details, an approved building plan copy,
   and the bank's own legal/technical verification of the property title
   and construction stage (banks disburse in stages tied to construction
   progress for under-construction properties, not as a lump sum).

Q: Can the bank charge a foreclosure/prepayment penalty on my home loan?
A: For floating-rate home loans to individual borrowers, RBI directs that
   banks generally cannot levy a foreclosure or prepayment penalty. Fixed-
   rate loans may still carry one depending on the sanction terms — check
   your specific loan's rate type and sanction letter.

Q: The builder hasn't delivered on time — does that affect my home loan
   EMIs?
A: Your EMI obligation to the bank is independent of the builder's
   performance (the loan is disbursed to the builder as construction-stage
   payments; your repayment obligation to the bank starts regardless). If
   you pursue a RERA refund from the builder for delay, the loan/EMI
   position with your bank is a separate matter to resolve alongside —
   inform your bank of a RERA proceeding as it may affect how they treat
   your account.

Q: What if I never received my property documents back after loan
   closure?
A: Lenders are required (per RBI's directions on release of movable/
   immovable property documents) to return all original property
   documents within a defined window (commonly 30 days) of full loan
   repayment/closure, and to compensate for delay. Escalate to the
   lender's Nodal Officer, then RBI Integrated Ombudsman (cms.rbi.org.in)
   if unresolved — this is the same RBI ombudsman channel used for other
   banking grievances.
""",
    },
    # ── General escalation guide ────────────────────────────
    {
        "folder": "faqs", "filename": "rera_complaint_filing_faqs.txt",
        "title": "RERA Complaint Filing — FAQs", "authority": "RERA Act 2016",
        "category": "faq",
        "content": """
RERA COMPLAINT FILING — FREQUENTLY ASKED QUESTIONS

Q: Which State RERA do I file with?
A: The RERA Authority of the state where the project is physically
   located and registered — find the project's registration number and
   registering authority on that state's RERA portal (e.g. rera.tn.gov.in,
   maharera.maharashtra.gov.in, rera.karnataka.gov.in) before filing;
   filing with the wrong state's authority will just be rejected/
   transferred, wasting time.

Q: What can I actually get from a RERA complaint?
A: Depends on the ground: for possession delay (Section 18), a refund
   with interest or continued possession with monthly interest for delay;
   for structural/quality defects (Section 14(3)), a rectification order;
   for general project non-compliance (false advertising, diversion of
   funds, non-disclosure), a compliance direction and/or penalty on the
   promoter. RERA authorities can also direct compensation for other
   proven losses.

Q: Do I need a lawyer to file a RERA complaint?
A: No — RERA proceedings are explicitly designed to be accessible without
   mandatory legal representation, though complex cases (large amounts,
   disputed facts) often benefit from one.

Q: How long does a RERA complaint take?
A: The Act targets disposal within 60 days of filing, though actual
   timelines vary by state authority caseload — track your complaint's
   status online via the same state portal you filed on.

Q: What if I'm unhappy with the RERA Authority's order?
A: Appeal to the state's Real Estate Appellate Tribunal within 60 days of
   the order (a short window — don't delay). Beyond the Tribunal, further
   appeal lies to the High Court on a question of law.
""",
    },
]


def main():
    print("=" * 60)
    print("HOUSING DOMAIN — AUTHORED GRIEVANCE CONTENT SEEDING")
    print("=" * 60)
    for doc in DOCUMENTS:
        save(doc["folder"], doc["filename"], doc["title"], doc["authority"], doc["category"], doc["content"])
    print(f"Done. Wrote {len(DOCUMENTS)} authored documents.")


if __name__ == "__main__":
    main()
