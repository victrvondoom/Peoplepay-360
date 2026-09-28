"""
Airlines Domain - Authored Grievance Content Seeder
Complaint templates and FAQs grounded in the real DGCA CAR PDFs just
downloaded (consumer protection, denied boarding/cancellation/delay,
refund/passenger rights).
"""
import json
from pathlib import Path

KNOWLEDGE_ROOT = Path(__file__).resolve().parents[2] / "knowledge" / "airlines"


def save(folder, filename, title, authority, category, content):
    dest_dir = KNOWLEDGE_ROOT / folder
    dest_dir.mkdir(parents=True, exist_ok=True)
    filepath = dest_dir / filename
    filepath.write_text(content.strip() + "\n", encoding="utf-8")
    meta_dir = KNOWLEDGE_ROOT / "metadata" / folder
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / f"{Path(filename).stem}.json").write_text(
        json.dumps({"title": title, "authority": authority, "source_url": None,
                    "domain": "airlines", "type": "authored_guide", "category": category},
                   indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"  wrote {filepath.relative_to(KNOWLEDGE_ROOT)}")


DOCUMENTS = [
    {
        "folder": "grievance_templates", "filename": "denied_boarding_compensation_template.txt",
        "title": "Denied Boarding Compensation Claim Template", "authority": "DGCA",
        "category": "template",
        "content": """
DENIED BOARDING COMPENSATION CLAIM TEMPLATE

Legal basis: DGCA CAR Section 3 requires airlines to first call for
volunteers before denying boarding involuntarily. If boarding is denied
against your will on a flight you held a confirmed reservation for and
checked in on time, you are entitled to compensation set by CAR (commonly
cited as a percentage of basic fare plus fuel charge, subject to a cap,
scaled by how much alternate travel is delayed), in addition to a refund
or alternate flight — the airline cannot simply substitute one for the other.

To,
The Duty Manager / Nodal Officer, [Airline Name]

Subject: Denied boarding on flight [flight number], [date] — compensation
claim under DGCA CAR Section 3

"I held a confirmed reservation on [flight number] dated [date] and
checked in within the stipulated time, but was denied boarding
involuntarily [describe: without being asked to volunteer / after
volunteers were insufficient]. I request compensation as prescribed under
DGCA CAR Section 3 for denied boarding, in addition to [a full refund /
rebooking on the next available flight], and a written explanation of how
volunteers were solicited before my boarding was denied."

Escalation path if unresolved:
1. Airline's own Nodal Officer / customer relations (most airlines must
   respond within a stated window, commonly 7-30 days).
2. AirSewa portal (airsewa.gov.in) — the government's air-passenger
   grievance platform, routes the complaint to the airline with tracking.
3. Ministry of Civil Aviation grievance channel if AirSewa/airline
   response is inadequate.
""",
    },
    {
        "folder": "grievance_templates", "filename": "flight_cancellation_delay_template.txt",
        "title": "Flight Cancellation / Delay Compensation Template", "authority": "DGCA",
        "category": "template",
        "content": """
FLIGHT CANCELLATION / DELAY COMPENSATION TEMPLATE

Legal basis: DGCA CAR Section 3 (Facilities to Passengers) sets airline
obligations based on notice given before a cancellation, and on delay
duration: informing passengers of cancellation less than the required
notice window before departure entitles the passenger to compensation
in addition to a refund or alternate flight; delays beyond stated
thresholds require the airline to provide meals/refreshments and, beyond
longer thresholds, hotel accommodation for outstation passengers.

To,
The Duty Manager / Nodal Officer, [Airline Name]

Subject: [Cancellation / Delay] of flight [flight number], [date] —
facilities and compensation claim

"My flight [flight number] scheduled for [date/time] was [cancelled with
less than the required notice / delayed by [X] hours]. I was not offered
[meals / refreshments / hotel accommodation / alternate flight / refund]
as required under DGCA CAR Section 3 for a delay/cancellation of this
duration. I request [the applicable facility] and, where a cancellation
notice was inadequate, the compensation prescribed under CAR in addition
to my refund or rebooking."

Note the 2026 update: DGCA now requires a 48-hour "look-in" cancellation
window on qualifying bookings (7+ days out domestic, 15+ days out
international) letting passengers cancel/modify without penalty, and bars
airlines from forcing a credit shell instead of a cash refund — cite this
directly if a refund was converted to a credit shell without your consent.

Escalation path if unresolved:
1. Airline Nodal Officer -> 2. AirSewa (airsewa.gov.in) -> 3. Ministry of
Civil Aviation grievance channel.
""",
    },
    {
        "folder": "grievance_templates", "filename": "baggage_loss_damage_template.txt",
        "title": "Lost/Damaged Baggage Claim Template", "authority": "Montreal Convention / DGCA",
        "category": "template",
        "content": """
LOST / DAMAGED BAGGAGE CLAIM TEMPLATE

Legal basis: For international carriage, the Montreal Convention caps
airline liability for baggage loss/damage/delay at a fixed amount in
Special Drawing Rights (SDRs) per passenger unless a higher value was
declared in advance; domestic Indian carriage follows the Carriage by Air
Act 1972 (which applies Montreal/Warsaw-derived rules domestically) and
DGCA's baggage-related CAR provisions.

Immediate step: file a Property Irregularity Report (PIR) at the airport
baggage desk BEFORE leaving — this is generally required to preserve your
claim; note the PIR reference number.

To,
The Baggage Services / Customer Relations, [Airline Name]

Subject: [Lost / Damaged / Delayed] baggage — PIR [reference], flight
[flight number], [date]

"My baggage was [lost / damaged / delivered X days late] on flight
[flight number] dated [date], PIR reference [xxxx]. I am claiming
[replacement value of contents / repair cost / reimbursement for
essential purchases made during the delay], with receipts attached. Please
confirm the applicable liability limit and processing timeline for this
claim."

Escalation path if unresolved:
1. Airline's baggage/customer relations team (using the PIR reference).
2. AirSewa (airsewa.gov.in) if unresolved within the airline's stated
   timeline.
3. Consumer court (District/State Commission under the Consumer Protection
   Act) for claims the airline disputes or undervalues — baggage liability
   caps under Montreal Convention do not prevent a consumer complaint about
   deficiency in service more broadly.
""",
    },
    {
        "folder": "faqs", "filename": "airsewa_and_escalation_faqs.txt",
        "title": "AirSewa & Airline Grievance Escalation FAQs", "authority": "MoCA",
        "category": "faq",
        "content": """
AIRSEWA & AIRLINE GRIEVANCE ESCALATION — FAQs

Q: What is AirSewa?
A: AirSewa (airsewa.gov.in) is the Ministry of Civil Aviation's online
   platform for air passengers to file grievances against airlines and
   airport operators, track flight status, and get general information.
   It routes your complaint directly to the concerned airline/airport with
   a tracked reference number and a monitored resolution timeline.

Q: Should I go straight to AirSewa or complain to the airline first?
A: Complain to the airline's own Nodal Officer / customer relations first
   — most CAR-based rights (compensation, refund) are the airline's direct
   obligation, and many complaints resolve at this stage within their
   stated timeline. Use AirSewa when the airline doesn't respond in a
   reasonable time or the response is inadequate — AirSewa complaints
   carry a government-tracked SLA to which airlines respond faster.

Q: My refund was converted to a "credit shell" without asking me — is
   that allowed?
A: Under the 2026 DGCA update, no — the choice of refund form (cash/original
   payment method vs. credit shell) rests with the passenger, not the
   airline. Cite this directly when disputing a forced credit shell.

Q: How do I escalate beyond AirSewa?
A: The Ministry of Civil Aviation's own grievance channel (vigilance
   complaints for staff conduct, or the public grievance portal for
   service issues) is the next step. For monetary claims the airline
   disputes, a consumer court (District Consumer Disputes Redressal
   Commission for smaller claims) remains available under the Consumer
   Protection Act — DGCA/AirSewa processes don't bar this route.
""",
    },
]


def main():
    print("=" * 60)
    print("AIRLINES DOMAIN — AUTHORED GRIEVANCE CONTENT SEEDING")
    print("=" * 60)
    for doc in DOCUMENTS:
        save(doc["folder"], doc["filename"], doc["title"], doc["authority"], doc["category"], doc["content"])
    print(f"Done. Wrote {len(DOCUMENTS)} authored documents.")


if __name__ == "__main__":
    main()
