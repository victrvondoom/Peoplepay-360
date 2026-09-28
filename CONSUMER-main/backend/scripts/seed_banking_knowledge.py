import os
import json
from pathlib import Path
from fpdf import FPDF

KNOWLEDGE_ROOT = Path(__file__).resolve().parents[2] / "knowledge" / "banking"

FOLDERS = [
    "rbi", "circulars", "ombudsman", "npci", 
    "banks/hdfc", "banks/icici", "banks/sbi", "banks/axis", 
    "cards", "loans", "upi", "chargebacks", "complaint_templates", "faqs"
]

DOCUMENTS = [
    # 1. RBI Regulations & Circulars
    {
        "path": "rbi/master_direction_credit_cards.pdf",
        "title": "Master Direction - Credit Card and Debit Card - Issuance and Conduct Directions, 2022",
        "bank": "Reserve Bank of India",
        "category": "rbi",
        "content": "Master Direction - Credit Card and Debit Card\n\nChapter III: Issue of Credit Cards\n3.1. Card-issuers shall ensure that there is no delay in dispatching bills and the customer has sufficient number of days (at least one fortnight) for making payment before the interest starts getting charged.\n\n3.2. Card-issuers shall ensure that wrong bills are not raised and issued to customers. In case, a customer protests any bill, the card-issuer shall provide explanation within a maximum period of 30 days.\n\n3.3. No charges shall be levied on any transaction disputed as 'fraudulent' by the customer until the dispute is resolved.\n\nChapter IV: Interest rates and other charges\n4.1. Card-issuers shall quote Annualized Percentage Rates (APR).\n4.2. The card-issuer shall not levy any charge that was not explicitly indicated to the credit cardholder."
    },
    {
        "path": "rbi/digital_payment_security_controls.pdf",
        "title": "Master Direction on Digital Payment Security Controls",
        "bank": "Reserve Bank of India",
        "category": "rbi",
        "content": "Master Direction on Digital Payment Security Controls\n\nSection 1: Internet Banking Security Controls\n1.1. REs shall introduce a cooling period of at least 12 hours before allowing funds transfer to a newly added beneficiary.\n1.2. REs shall set limits on the amount of funds that can be transferred during the cooling period.\n\nSection 3: Customer Protection\n3.1. Zero Liability of a Customer: A customer's entitlement to zero liability shall arise where the unauthorised transaction occurs due to contributory fraud/negligence by the bank, or a third party breach where the customer notifies the bank within three working days."
    },
    {
        "path": "circulars/rbi_fair_practices_code.pdf",
        "title": "Fair Practices Code for Lenders",
        "bank": "Reserve Bank of India",
        "category": "circulars",
        "content": "Fair Practices Code\n\n1. Loan Application\nLoan application forms should include necessary information which affects the interest of the borrower, so that a meaningful comparison with the terms and conditions offered by other NBFCs can be made.\n\n2. Guarantors\nWhen a person is considering being a guarantor to a loan, he should be informed about his liability as guarantor, the amount of liability he will be committing himself to the bank, and the circumstances under which the bank will call on him to pay."
    },
    # 2. Ombudsman
    {
        "path": "ombudsman/rbi_cms_guidelines.pdf",
        "title": "Reserve Bank - Integrated Ombudsman Scheme, 2021",
        "bank": "Reserve Bank of India",
        "category": "ombudsman",
        "content": "Reserve Bank - Integrated Ombudsman Scheme, 2021\n\nChapter 1: Grounds of Complaint\nAny customer may file a complaint with the Ombudsman on any of the following grounds alleging deficiency in service:\n- Delay or non-reversal of failed transactions.\n- Unauthorized electronic fund transfers.\n- Non-adherence to the Fair Practices Code.\n- Levying of charges without adequate prior notice.\n\nChapter 2: Procedure\nPre-condition: The customer must first file a complaint with the Regulated Entity. If the entity rejects the complaint, or provides no reply within 30 days, the customer can approach the Ombudsman."
    },
    # 3. NPCI & UPI
    {
        "path": "npci/upi_dispute_resolution.pdf",
        "title": "UPI Dispute Resolution Guidelines",
        "bank": "NPCI",
        "category": "npci",
        "content": "UPI Dispute Resolution and Auto-Reversal Guidelines\n\n1. Failed Transactions\nIf a UPI transaction fails, the issuing bank must auto-reverse the amount.\n\n2. Reversal Timelines (T+1 Rule)\nThe auto-reversal must be completed within T + 1 days (where T is the transaction date). If the bank fails to reverse the amount within T + 1 days, a penalty of Rs 100 per day of delay shall be paid to the customer.\n\n4. Chargeback in UPI\nIn cases of unauthorized transactions or goods not delivered, a chargeback can be raised by the remitter bank via the NPCI dispute management system within 60 days."
    },
    {
        "path": "upi/upi_faqs.pdf",
        "title": "NPCI UPI FAQs",
        "bank": "NPCI",
        "category": "upi",
        "content": "UPI FAQs\n\nQ1: What happens if I entered the wrong UPI PIN?\nA: If you enter the wrong UPI PIN multiple times, your bank may block the UPI service for security reasons. You will have to reset your UPI PIN.\n\nQ2: What is the transaction limit for UPI?\nA: The maximum limit is Rs. 1 Lakh per transaction for normal UPI transfers. For specific use cases like IPO and Retail Direct Scheme, the limit is Rs. 5 Lakhs."
    },
    # 4. Bank Specific (HDFC, ICICI, SBI, Axis)
    {
        "path": "banks/hdfc/credit_card_agreements.pdf",
        "title": "HDFC Bank Credit Card Member Agreement",
        "bank": "HDFC Bank",
        "category": "banks/hdfc",
        "content": "HDFC Bank Credit Card Member Agreement\n\n1. Credit Limit\nThe Cardmember must not exceed the Credit Limit. An Overlimit Fee of 2.5% of the overlimit amount (minimum Rs 500) will be charged.\n\n2. Finance Charges\nFinance charges (interest) will be levied if the Total Amount Due is not paid in full by the Payment Due Date. The finance charge ranges from 1.99% to 3.6% per month (23.88% to 43.2% annualized).\n\n3. Unauthorized Transactions\nThe Cardmember must immediately report the loss, theft, or misuse of the Card to the Bank. The Cardmember's liability for unauthorized transactions is zero post-reporting."
    },
    {
        "path": "banks/icici/savings_account_terms.pdf",
        "title": "ICICI Bank Savings Account Terms & Conditions",
        "bank": "ICICI Bank",
        "category": "banks/icici",
        "content": "ICICI Bank Savings Account Terms\n\n1. Minimum Average Balance (MAB)\nCustomers must maintain the required Minimum Average Balance. Non-maintenance charges will be levied as per the Schedule of Charges.\n\n2. Debit Card Issuance\nA debit card will be issued to the account holder. The annual fee will be deducted directly from the savings account balance."
    },
    {
        "path": "banks/sbi/personal_loan_terms.pdf",
        "title": "SBI Personal Loan Terms & Conditions",
        "bank": "SBI",
        "category": "banks/sbi",
        "content": "SBI Personal Loan Agreement\n\n1. EMI Payment\nThe borrower shall repay the loan in EMIs. Late payment of EMI will attract a penal interest of 2% per month (24% p.a.) on the overdue amount.\n\n2. Prepayment and Foreclosure\nThe borrower may prepay the loan. A prepayment penalty of 3% on the prepaid principal amount is applicable if the loan is closed before the completion of 12 EMIs."
    },
    {
        "path": "banks/axis/auto_loan_policies.pdf",
        "title": "Axis Bank Auto Loan Policy",
        "bank": "Axis Bank",
        "category": "banks/axis",
        "content": "Axis Bank Auto Loan Policy\n\n1. Hypothecation\nThe vehicle purchased will be hypothecated to Axis Bank. The borrower must ensure the bank's name is endorsed on the RC book.\n\n2. Default\nIn case of default, the bank reserves the right to repossess the vehicle after serving a 7-day notice to the borrower."
    },
    # 5. Cards & Loans generic
    {
        "path": "cards/chargeback_policies.pdf",
        "title": "Standard Chargeback Policies",
        "bank": "General",
        "category": "cards",
        "content": "Chargeback Policies\n\nCustomers can initiate a chargeback for credit/debit card transactions under the following reason codes:\n- Goods/Services not provided\n- Duplicate processing\n- Fraudulent transaction\nThe chargeback must be filed within 120 days of the transaction date."
    },
    {
        "path": "loans/foreclosure_rules.pdf",
        "title": "RBI Foreclosure Rules for Floating Rate Loans",
        "bank": "Reserve Bank of India",
        "category": "loans",
        "content": "RBI Foreclosure Rules\n\nAs per RBI guidelines, banks and NBFCs are prohibited from levying foreclosure charges or pre-payment penalties on any floating rate term loans sanctioned to individual borrowers, for purposes other than business."
    },
    {
        "path": "chargebacks/timeline.pdf",
        "title": "Chargeback Timelines",
        "bank": "General",
        "category": "chargebacks",
        "content": "Chargeback Timelines\n\n1. Cardholder disputes transaction (Day 0)\n2. Issuer raises chargeback via network (Within 120 days)\n3. Acquirer receives chargeback and notifies merchant (Within 45 days)\n4. Merchant responds with evidence (Representment - Within 30 days)\n5. Pre-arbitration / Arbitration if dispute continues."
    },
    # 6. FAQs & Complaint Templates
    {
        "path": "faqs/unauthorized_transactions.pdf",
        "title": "FAQ: Unauthorized Transactions",
        "bank": "General",
        "category": "faqs",
        "content": "FAQ: Unauthorized Transactions\n\nQ: What do I do if I see an unauthorized charge?\nA: Immediately block your card and report the transaction to your bank's 24x7 customer care. If reported within 3 days, your liability is zero.\n\nQ: Will I get my money back?\nA: Yes, the bank must credit the amount back to your account within 10 working days of reporting."
    },
    {
        "path": "complaint_templates/unauthorized_debit.pdf",
        "title": "Template: Unauthorized Credit Card Transaction",
        "bank": "General",
        "category": "complaint_templates",
        "content": "Complaint Template: Unauthorized Transaction\n\nSubject: Dispute regarding Unauthorized Transaction on Credit Card ending in [Last 4 Digits]\n\nTo The Grievance Redressal Officer,\n[Bank Name]\n\nDear Sir/Madam,\nI am writing to formally dispute an unauthorized transaction that appeared on my credit card statement.\n\nTransaction Details:\n- Date: [Date]\n- Merchant: [Merchant]\n- Amount: [Amount]\n\nI did not authorize this transaction. As per the RBI Master Direction on Customer Protection, my liability should be zero. Please reverse the charges."
    },
    {
        "path": "complaint_templates/failed_upi.pdf",
        "title": "Template: Failed UPI Transaction Auto-Reversal Delay",
        "bank": "General",
        "category": "complaint_templates",
        "content": "Complaint Template: Failed UPI Transaction auto-reversal delay (T+1 Rule)\n\nSubject: Claim for T+1 Penalty for Delayed Auto-Reversal of Failed UPI Transaction\n\nTo The Nodal Officer,\n[Bank Name]\n\nDear Sir/Madam,\nI initiated a UPI transaction which failed, but the amount was debited. The amount was not auto-reversed within the mandated T+1 day timeline.\n\nTransaction Details:\n- RRN: [12-digit RRN]\n- Date: [Date]\n\nAs per the NPCI Circular, banks must reverse failed UPI transactions within T+1 days. Failure attracts a penalty of Rs. 100 per day. I claim compensation of Rs. [Amount]."
    },
    {
        "path": "complaint_templates/emi_error.pdf",
        "title": "Template: EMI Deduction Error",
        "bank": "General",
        "category": "complaint_templates",
        "content": "Complaint Template: Incorrect EMI Deduction\n\nSubject: Incorrect EMI Deduction for Loan Account [Loan Number]\n\nDear Sir/Madam,\nMy loan agreement states my EMI is Rs. [Amount], but this month my account was debited for Rs. [Higher Amount]. \nPlease correct this error, refund the excess amount, and remove any bounce charges applied."
    }
]

def generate_pdf(content: str, filepath: Path):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_font("Helvetica", size=12)
    
    # Simple trick to handle string encoding for standard fonts
    encoded = content.encode("latin-1", "replace").decode("latin-1")
    pdf.multi_cell(0, 10, txt=encoded)
    
    pdf.output(str(filepath))

def main():
    print(f"Initializing Comprehensive Banking Knowledge Base (PDF Datasets) at {KNOWLEDGE_ROOT}")
    
    # 1. Ensure Directory Structure
    for folder in FOLDERS:
        (KNOWLEDGE_ROOT / folder).mkdir(parents=True, exist_ok=True)
        
    (KNOWLEDGE_ROOT / "metadata").mkdir(parents=True, exist_ok=True)
        
    # 2. Write Data and Metadata
    for doc in DOCUMENTS:
        filepath = KNOWLEDGE_ROOT / doc["path"]
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        # Write content as PDF!
        generate_pdf(doc["content"], filepath)
        
        # Write metadata
        metadata = {
            "title": doc["title"],
            "bank": doc["bank"],
            "category": doc["category"],
            "document_type": "pdf",
            "domain": "banking",
            "source_url": f"official://{doc['path']}"
        }
        
        # Ensure metadata directory exists
        meta_dir = KNOWLEDGE_ROOT / "metadata" / doc["category"]
        meta_dir.mkdir(parents=True, exist_ok=True)
        
        meta_path = meta_dir / f"{filepath.stem}.json"
        meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        
        print(f"Generated PDF Dataset: {filepath}")

if __name__ == "__main__":
    main()
