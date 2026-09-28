"""
Banking Domain - Authored Grievance Content Seeder
Writes complaint templates and escalation guides grounded in the real RBI
Master Directions just downloaded (KYC, cards, deposits, advances, wilful
defaulters, credit information, internal ombudsman, payment aggregators,
PPIs), matching the authoring pattern used for the government domain.
"""
import json
from pathlib import Path

KNOWLEDGE_ROOT = Path(__file__).resolve().parents[2] / "knowledge" / "banking"


def save(folder: str, filename: str, title: str, authority: str, category: str, content: str):
    dest_dir = KNOWLEDGE_ROOT / folder
    dest_dir.mkdir(parents=True, exist_ok=True)
    filepath = dest_dir / filename
    filepath.write_text(content.strip() + "\n", encoding="utf-8")

    meta_dir = KNOWLEDGE_ROOT / "metadata" / folder
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / f"{Path(filename).stem}.json").write_text(
        json.dumps(
            {"title": title, "authority": authority, "source_url": None,
             "domain": "banking", "type": "authored_guide", "category": category},
            indent=2, ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"  wrote {filepath.relative_to(KNOWLEDGE_ROOT)}")


DOCUMENTS = [
    {
        "folder": "grievance_templates", "filename": "unauthorized_transaction_complaint.txt",
        "title": "Unauthorized/Fraudulent Transaction Complaint Template", "authority": "RBI",
        "category": "template",
        "content": """
UNAUTHORIZED / FRAUDULENT TRANSACTION COMPLAINT TEMPLATE

Legal basis: RBI's "Limited Liability of Customers in Unauthorised Electronic
Banking Transactions" framework (incorporated into the Master Direction on
Digital Payment Security Controls and related KYC/card directions) gives a
customer ZERO liability if the unauthorized transaction resulted from a
bank-side breach or a third-party breach where the customer notifies the
bank within 3 working days of receiving communication about the transaction.
Liability is limited (capped) if reported within 4-7 working days, and
determined by the bank's Board-approved policy beyond that.

To,
The Branch Manager / Nodal Grievance Officer,
[Bank Name], [Branch/Account details]

Subject: Unauthorized transaction of INR [amount] on [date] — Account/Card
No. [xxxx] — Immediate reversal requested under RBI's zero/limited liability
framework

"I noticed an unauthorized transaction of INR [amount] on [date] on my
[account/credit card/debit card] ending [xxxx], which I did not authorize.
I am reporting this within [X] hours/days of receiving the transaction
alert. I request that this be treated under the RBI's zero/limited
liability framework, that the transaction be reversed (shadow reversal)
within 10 working days as mandated, and that you confirm receipt of this
complaint in writing with a complaint reference number."

Immediate steps before/with filing:
1. Block the card/freeze the account immediately via app, net banking, or
   the 24x7 helpline — get a blocking confirmation reference number.
2. File this written complaint the same day; banks are required to
   acknowledge and resolve within 90 days, crediting the disputed amount
   (shadow reversal) within 10 working days pending investigation.
3. File a cyber crime complaint at cybercrime.gov.in or dial 1930
   (national cyber fraud helpline) — this reference number strengthens the
   bank complaint and is often required for reversal above a threshold.

Escalation path if unresolved:
1. Bank's internal Nodal/Grievance Redressal Officer (first 30 days).
2. Bank's Internal Ombudsman (mandatory for most complaints not resolved
   in the customer's favor before final rejection, per the Internal
   Ombudsman Directions) — the bank itself must route it here before
   rejecting.
3. RBI Integrated Ombudsman Scheme (cms.rbi.org.in) if unresolved after 30
   days or the response is unsatisfactory — free, online, no lawyer needed.
""",
    },
    {
        "folder": "grievance_templates", "filename": "credit_card_dispute_template.txt",
        "title": "Credit Card Billing Dispute / Chargeback Template", "authority": "RBI",
        "category": "template",
        "content": """
CREDIT CARD BILLING DISPUTE TEMPLATE

Legal basis: RBI's Master Direction on Credit Card and Debit Card —
Issuance and Conduct requires card issuers to provide a clear billing
dispute mechanism; a disputed transaction must not accrue interest/charges
while under investigation, and the issuer must respond to a dispute within
a defined window (commonly cited as 30 days) before the amount can be
re-billed if the dispute is rejected, with the reason for rejection
disclosed to the customer.

To,
The Card Division / Nodal Officer,
[Bank Name]

Subject: Dispute of transaction dated [date], amount INR [amount], on card
ending [xxxx] — Reference [statement/transaction ID]

"I am disputing the above transaction on my credit card statement dated
[date]. [Describe: transaction not recognized / duplicate billing /
merchant did not deliver goods or services / amount charged does not match
what was authorized / subscription not cancelled despite request]. I
request that this be investigated, that no interest or late fee be levied
on the disputed amount while investigation is pending, and that I receive
a written explanation of the outcome, including the specific evidence
relied upon if the dispute is rejected."

Documents to attach:
- Statement excerpt showing the disputed line item
- Any merchant correspondence (cancellation confirmation, refund promise,
  non-delivery proof)
- Screenshot of the transaction alert/SMS if amount mismatches

Escalation path if unresolved or rejected without adequate reason:
1. Card issuer's Nodal Officer -> Internal Ombudsman (mandatory pass-through
   before final rejection on eligible complaints).
2. RBI Integrated Ombudsman Scheme (cms.rbi.org.in) — free, binding on the
   bank up to the award amount, no lawyer required.
3. For card-network-level chargebacks (Visa/Mastercard/RuPay dispute
   rules), the bank internally raises the chargeback with the merchant's
   acquiring bank; the customer's role is providing evidence to their own
   issuing bank promptly (chargeback windows are typically 120 days from
   the transaction, so report early).
""",
    },
    {
        "folder": "grievance_templates", "filename": "failed_upi_transaction_complaint.txt",
        "title": "Failed/Stuck UPI Transaction Complaint Template", "authority": "NPCI / RBI",
        "category": "template",
        "content": """
FAILED / STUCK UPI TRANSACTION COMPLAINT TEMPLATE

Background: Most UPI failures (money debited but not credited to the
payee, or stuck "pending" status) are auto-reversed by the banks'/NPCI's
switch within T+1 working day. When auto-reversal doesn't happen, the
Turn Around Time (TAT) for a formal complaint-driven reversal is commonly
cited as within a defined window from the complaint date, after which a
per-day penalty may be payable to the customer under NPCI's dispute
guidelines.

Steps:
1. Raise the complaint FIRST in your UPI app (Bank app / PhonePe / Google
   Pay / Paytm etc.) using the "Raise Dispute" / "Report Issue" option
   against the specific transaction — this creates a complaint reference
   number (CRN) in NPCI's dispute system, which is the fastest path.
2. If not resolved within the app's stated TAT, escalate in writing:

To,
The Nodal Officer, [Remitting Bank Name]

Subject: Failed UPI transaction not reversed — UTR/RRN [xxxxxxxxxx],
amount INR [amount], date [date]

"On [date], I attempted a UPI payment of INR [amount] to [payee UPI ID /
name], UTR/RRN [xxxxxxxxxx]. The amount was debited from my account but
[not credited to the payee / transaction shows failed but amount not
reversed]. I have already raised this in-app (reference [CRN]) without
resolution within the stated TAT. I request immediate reversal of the
debited amount."

Escalation path if unresolved:
1. Remitting bank's Nodal Officer (with the app-generated CRN).
2. NPCI's own dispute redressal mechanism (via the PSP app, since NPCI
   does not take complaints directly from customers outside the app/bank
   channel).
3. RBI Integrated Ombudsman Scheme (cms.rbi.org.in) — UPI/digital payment
   complaints against a bank are squarely within its scope.
""",
    },
    {
        "folder": "grievance_templates", "filename": "loan_foreclosure_dispute_template.txt",
        "title": "Loan Foreclosure / Interest Rate Dispute Template", "authority": "RBI",
        "category": "template",
        "content": """
LOAN FORECLOSURE / INTEREST RATE DISPUTE TEMPLATE

Legal basis: RBI's Master Directions on Interest Rate on Advances require
banks to have a Board-approved interest rate model, disclose the
benchmark and spread applied to a floating-rate loan, and process
foreclosure/prepayment requests without arbitrary delay; RBI has also
directed that floating-rate loans to individual borrowers (for non-business
purposes) generally cannot carry a foreclosure/prepayment penalty.

To,
The Loans Department / Nodal Officer,
[Bank Name]

Subject: [Foreclosure not processed / Foreclosure charge wrongly levied /
Interest rate reset not applied correctly] — Loan A/c No. [xxxx]

"I request foreclosure of my loan account [xxxx] / dispute the following
charge: [describe — e.g. a foreclosure penalty was levied despite this
being a floating-rate individual loan, or my interest rate was not reset
per the disclosed benchmark reset periodicity]. Please process this
[foreclosure / correction] and provide a written statement of the exact
benchmark, spread, and reset dates applied to this loan since disbursement."

Escalation path if unresolved:
1. Bank's Nodal Officer -> Internal Ombudsman.
2. RBI Integrated Ombudsman Scheme (cms.rbi.org.in).
3. For disputes about wrongful reporting to Credit Information Companies
   (CIBIL/Experian/Equifax/CRIF) arising from the same loan (e.g. marked
   as defaulter after a foreclosure dispute), separately raise a credit
   report correction request with the bureau under the Credit Information
   Companies (Regulation) Act — the bank must respond to bureau correction
   requests routed through it within 30 days.
""",
    },
    {
        "folder": "grievance_templates", "filename": "rbi_ombudsman_escalation_template.txt",
        "title": "RBI Integrated Ombudsman Complaint Template", "authority": "RBI",
        "category": "template",
        "content": """
RBI INTEGRATED OMBUDSMAN SCHEME — COMPLAINT TEMPLATE

Legal basis: Reserve Bank - Integrated Ombudsman Scheme, 2021 covers
complaints against banks, NBFCs, and payment system participants. The
Scheme is "One Nation One Ombudsman" — a single point of reference,
free of cost, and does not require a lawyer.

Pre-condition: You must have FIRST filed a written complaint with the
regulated entity (bank/NBFC) and either received no response within 30
days, or an unsatisfactory response/rejection.

File online at: cms.rbi.org.in

Fields typically required:
1. Your complaint filed earlier with the bank (date, reference number,
   copy of correspondence).
2. The bank's response (if any) and why it is unsatisfactory.
3. Ground of complaint — select the closest match: deficiency in service,
   non-adherence to Fair Practices Code / interest rate directions, failure
   to reverse an unauthorized electronic transaction within the RBI
   timeline, non-observance of RBI directions on para-banking, credit
   card/loan mis-selling, ATM/UPI/digital payment failure, etc.
4. Relief sought — specific amount, or a specific action (e.g. correction
   of credit report, reversal of charge, apology, compensation for loss).

What happens next:
- The Ombudsman facilitates a resolution; if not resolved by agreement, the
  Ombudsman can pass an Award, binding on the bank (subject to the bank's
  right to represent to the Appellate Authority, currently a Deputy
  Governor of RBI, within 30 days).
- There is no complaint fee, and complaints below a certain simplicity
  threshold are typically resolved faster than a full Award process.

If the Ombudsman rejects the complaint or you're dissatisfied with the
Award: an appeal lies to the RBI Ombudsman's Appellate Authority within 30
days; beyond that, civil remedies (consumer forum / civil court) remain
available since the Ombudsman Scheme does not bar other legal remedies.
""",
    },
    # ── FAQs ──────────────────────────────────────────────
    {
        "folder": "faqs", "filename": "unauthorized_transactions_faqs.txt",
        "title": "Unauthorized Transactions & Liability FAQs", "authority": "RBI",
        "category": "faq",
        "content": """
UNAUTHORIZED TRANSACTIONS & CUSTOMER LIABILITY — FAQs

Q: Money was debited from my account without my knowledge — am I liable?
A: Depends on how fast you report it after the bank's alert:
   - Reported within 3 working days: zero liability if the breach was on
     the bank's side or a third-party breach not attributable to you.
   - Reported within 4-7 working days: limited liability (a capped amount
     depending on your account/card type).
   - Reported after 7 working days: liability determined per the bank's
     Board-approved policy — can be higher.
   Report immediately regardless — the clock starts from when the bank's
   communication (SMS/email) reaches you, not from when you notice it.

Q: The bank says the amount will be "shadow reversed" — what does that mean?
A: Pending investigation, the disputed amount is provisionally credited
   back to your account within 10 working days of your complaint — this is
   not the final outcome, just a protective interim credit while the bank
   investigates.

Q: The bank rejected my complaint outright — what next?
A: Every eligible complaint that the bank proposes to reject (or resolve
   not fully in your favor) must first go through the bank's own Internal
   Ombudsman before a final rejection letter is issued — ask explicitly
   whether your complaint was routed to the Internal Ombudsman. If it
   wasn't and you weren't told why, that's itself a valid ground to escalate
   to the RBI Ombudsman.

Q: Do I need a police complaint / cyber crime report for the bank to act?
A: Not strictly required for the bank's own zero/limited-liability process,
   but strongly recommended — file at cybercrime.gov.in or call 1930. Many
   banks ask for it above a certain amount, and it strengthens your case
   if the dispute proceeds to the Ombudsman.
""",
    },
    {
        "folder": "faqs", "filename": "credit_card_kyc_faqs.txt",
        "title": "Credit Card & KYC Update FAQs", "authority": "RBI",
        "category": "faq",
        "content": """
CREDIT CARD ISSUANCE & KYC UPDATE — FAQs

Q: Can a bank issue me a credit card or increase my limit without consent?
A: No. RBI's Credit Card and Debit Card Directions require express
   consent (not a pre-ticked box or a passive "opt-out") for card
   issuance, credit limit enhancement, and converting a loan into EMIs
   on a card. An unsolicited card/limit-increase can be reported as a
   direct violation.

Q: My card was closed/blocked and I still see charges — what now?
A: Once a card is surrendered/closed (with a closure confirmation
   reference), no further charges should be levied. Dispute any
   post-closure charge in writing citing the closure reference and date.

Q: My periodic KYC update was rejected or my account got frozen for
   "KYC non-compliance" — what should I do?
A: RBI's KYC Directions require banks to give advance notice and a
   reasonable time to complete periodic KYC before restricting an account,
   and full freezing (debit + credit) is a last resort after intermediate
   steps (e.g. debit freeze only) and further notice. If your account was
   frozen without the required notice sequence, that is a valid complaint
   ground citing the KYC Directions directly.

Q: Where do I actually update KYC?
A: At your home branch, via the bank's net-banking/app "Re-KYC" flow if
   offered, or in some cases via a video-KYC option — low-risk customers
   often qualify for simplified self-declaration based re-KYC without an
   in-branch visit; ask your bank whether you qualify before assuming a
   branch visit is required.
""",
    },
]


def main():
    print("=" * 60)
    print("BANKING DOMAIN — AUTHORED GRIEVANCE CONTENT SEEDING")
    print("=" * 60)
    for doc in DOCUMENTS:
        save(doc["folder"], doc["filename"], doc["title"], doc["authority"], doc["category"], doc["content"])
    print(f"Done. Wrote {len(DOCUMENTS)} authored documents.")


if __name__ == "__main__":
    main()
