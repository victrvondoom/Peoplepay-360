"""
E-Commerce Domain — Comprehensive Data Downloader v2
Downloads from Wikipedia, official GoI portals, and accessible policy pages.
Covers ALL topics: Consumer Protection, CCPA, ONDC, each marketplace,
payment systems, couriers, warranty law, and complaint procedures.
"""
import json, time, requests
from pathlib import Path
from bs4 import BeautifulSoup

KNOWLEDGE_ROOT = Path(__file__).resolve().parents[2] / "knowledge" / "ecommerce"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

# ───────────────────────────────────────────────────────────────────────────
# SOURCES: (url, folder, filename, title, authority)
# ───────────────────────────────────────────────────────────────────────────
SOURCES = [
    # ── CONSUMER PROTECTION LAWS ────────────────────────────────────────────
    ("https://en.wikipedia.org/wiki/Consumer_Protection_Act,_2019",
     "consumer_protection", "consumer_protection_act_2019",
     "Consumer Protection Act 2019", "GoI"),
    ("https://en.wikipedia.org/wiki/Consumer_Protection_Act,_1986",
     "consumer_protection", "consumer_protection_act_1986",
     "Consumer Protection Act 1986", "GoI"),
    ("https://en.wikipedia.org/wiki/Central_Consumer_Protection_Authority",
     "ccpa", "ccpa_overview",
     "Central Consumer Protection Authority (CCPA)", "GoI"),
    ("https://en.wikipedia.org/wiki/Consumer_court",
     "consumer_protection", "consumer_court_overview",
     "Consumer Court (India) Overview", "GoI"),
    ("https://en.wikipedia.org/wiki/National_Consumer_Disputes_Redressal_Commission",
     "consumer_protection", "ncdrc_overview",
     "National Consumer Disputes Redressal Commission", "GoI"),
    ("https://en.wikipedia.org/wiki/Product_liability",
     "regulations", "product_liability",
     "Product Liability Law Overview", "Legal"),

    # ── ONDC & DPIIT ────────────────────────────────────────────────────────
    ("https://en.wikipedia.org/wiki/Open_Network_for_Digital_Commerce",
     "ondc", "ondc_overview",
     "ONDC Framework and Architecture", "GoI"),
    ("https://en.wikipedia.org/wiki/Department_for_Promotion_of_Industry_and_Internal_Trade",
     "regulations", "dpiit_overview",
     "DPIIT Overview", "GoI"),

    # ── E-COMMERCE REGULATIONS ──────────────────────────────────────────────
    ("https://en.wikipedia.org/wiki/E-commerce_in_India",
     "regulations", "ecommerce_india_overview",
     "E-Commerce in India Overview", "GoI"),
    ("https://en.wikipedia.org/wiki/Information_Technology_Act,_2000",
     "regulations", "it_act_2000",
     "Information Technology Act 2000", "GoI"),
    ("https://en.wikipedia.org/wiki/Digital_Personal_Data_Protection_Act,_2023",
     "regulations", "dpdp_act_2023",
     "Digital Personal Data Protection Act 2023", "GoI"),

    # ── NATIONAL CONSUMER HELPLINE ──────────────────────────────────────────
    ("https://consumerhelpline.gov.in/",
     "faqs", "national_consumer_helpline",
     "National Consumer Helpline", "GoI"),

    # ── AMAZON ──────────────────────────────────────────────────────────────
    ("https://www.amazon.in/gp/help/customer/display.html?nodeId=GKM69DUUYKQWKWX7",
     "marketplaces/amazon", "amazon_returns",
     "Amazon India Return Policy", "Amazon"),
    ("https://www.amazon.in/gp/help/customer/display.html?nodeId=GQ37ZCNECJKTFYQV",
     "marketplaces/amazon", "amazon_a_to_z_guarantee",
     "Amazon A-to-z Guarantee", "Amazon"),
    ("https://www.amazon.in/gp/help/customer/display.html?nodeId=201117590",
     "marketplaces/amazon", "amazon_refunds",
     "Amazon India Refund Policy", "Amazon"),
    ("https://www.amazon.in/gp/help/customer/display.html?nodeId=GE38DUQE2BFF5XU",
     "marketplaces/amazon", "amazon_shipping",
     "Amazon India Shipping Policy", "Amazon"),
    ("https://en.wikipedia.org/wiki/Amazon_(company)",
     "marketplaces/amazon", "amazon_overview",
     "Amazon Company Overview", "Wikipedia"),

    # ── FLIPKART ────────────────────────────────────────────────────────────
    ("https://www.flipkart.com/pages/returnpolicy",
     "marketplaces/flipkart", "flipkart_returns",
     "Flipkart Return Policy", "Flipkart"),
    ("https://www.flipkart.com/pages/cancelPolicy",
     "marketplaces/flipkart", "flipkart_cancellation",
     "Flipkart Cancellation Policy", "Flipkart"),
    ("https://en.wikipedia.org/wiki/Flipkart",
     "marketplaces/flipkart", "flipkart_overview",
     "Flipkart Overview", "Wikipedia"),

    # ── MYNTRA ──────────────────────────────────────────────────────────────
    ("https://www.myntra.com/faq",
     "marketplaces/myntra", "myntra_faq",
     "Myntra FAQs on Returns and Exchanges", "Myntra"),
    ("https://en.wikipedia.org/wiki/Myntra",
     "marketplaces/myntra", "myntra_overview",
     "Myntra Overview", "Wikipedia"),

    # ── AJIO ────────────────────────────────────────────────────────────────
    ("https://en.wikipedia.org/wiki/Ajio",
     "marketplaces/ajio", "ajio_overview",
     "AJIO Overview", "Wikipedia"),

    # ── MEESHO ──────────────────────────────────────────────────────────────
    ("https://en.wikipedia.org/wiki/Meesho",
     "marketplaces/meesho", "meesho_overview",
     "Meesho Overview", "Wikipedia"),

    # ── JIOMART ─────────────────────────────────────────────────────────────
    ("https://en.wikipedia.org/wiki/JioMart",
     "marketplaces/jiomart", "jiomart_overview",
     "JioMart Overview", "Wikipedia"),

    # ── BLINKIT ─────────────────────────────────────────────────────────────
    ("https://blinkit.com/terms",
     "marketplaces/blinkit", "blinkit_terms",
     "Blinkit Terms and Conditions", "Blinkit"),
    ("https://en.wikipedia.org/wiki/Blinkit",
     "marketplaces/blinkit", "blinkit_overview",
     "Blinkit Quick Commerce Overview", "Wikipedia"),

    # ── ZEPTO ───────────────────────────────────────────────────────────────
    ("https://en.wikipedia.org/wiki/Zepto_(company)",
     "marketplaces/zepto", "zepto_overview",
     "Zepto Overview", "Wikipedia"),

    # ── SWIGGY INSTAMART ────────────────────────────────────────────────────
    ("https://en.wikipedia.org/wiki/Swiggy",
     "marketplaces/swiggy_instamart", "swiggy_overview",
     "Swiggy Instamart Overview", "Wikipedia"),

    # ── BIGBASKET ───────────────────────────────────────────────────────────
    ("https://www.bigbasket.com/terms-and-conditions/",
     "marketplaces/bigbasket", "bigbasket_terms",
     "BigBasket Terms and Conditions", "BigBasket"),
    ("https://en.wikipedia.org/wiki/BigBasket",
     "marketplaces/bigbasket", "bigbasket_overview",
     "BigBasket Overview", "Wikipedia"),

    # ── PAYMENT ─────────────────────────────────────────────────────────────
    ("https://en.wikipedia.org/wiki/Unified_Payments_Interface",
     "payment", "upi_overview",
     "Unified Payments Interface (UPI)", "NPCI"),
    ("https://en.wikipedia.org/wiki/Chargeback",
     "payment", "chargeback_rules",
     "Credit Card Chargeback Guidelines", "Financial"),
    ("https://en.wikipedia.org/wiki/National_Payments_Corporation_of_India",
     "payment", "npci_overview",
     "National Payments Corporation of India (NPCI)", "NPCI"),
    ("https://en.wikipedia.org/wiki/Digital_wallet",
     "payment", "digital_wallet_overview",
     "Digital Wallet Overview", "Financial"),

    # ── COURIER ─────────────────────────────────────────────────────────────
    ("https://en.wikipedia.org/wiki/Delhivery",
     "courier", "delhivery_overview",
     "Delhivery Logistics Overview", "Delhivery"),
    ("https://en.wikipedia.org/wiki/Blue_Dart_Express",
     "courier", "bluedart_overview",
     "Blue Dart Express Overview", "Blue Dart"),
    ("https://en.wikipedia.org/wiki/DTDC",
     "courier", "dtdc_overview",
     "DTDC Courier Overview", "DTDC"),
    ("https://en.wikipedia.org/wiki/India_Post",
     "courier", "india_post_overview",
     "India Post Overview", "India Post"),
    ("https://en.wikipedia.org/wiki/Ecom_Express",
     "courier", "ecom_express_overview",
     "Ecom Express Overview", "Ecom Express"),

    # ── WARRANTY & SELLER FRAUD ─────────────────────────────────────────────
    ("https://en.wikipedia.org/wiki/Warranty",
     "warranty", "warranty_law_overview",
     "Warranty Law - Types and Enforcement", "Legal"),
    ("https://en.wikipedia.org/wiki/Counterfeit_consumer_goods",
     "seller_policies", "counterfeit_goods",
     "Counterfeit Consumer Goods", "Legal"),

    # ── RETURNS & REFUND LAW ────────────────────────────────────────────────
    ("https://en.wikipedia.org/wiki/Lemon_law",
     "returns", "lemon_law",
     "Lemon Law - Product Return Rights", "Legal"),
    ("https://en.wikipedia.org/wiki/Refund",
     "refunds", "refund_law_overview",
     "Refund Laws and Procedures", "Legal"),

    # ── NEW: OFFICIAL RULES, ACTS & GUIDELINES (verified this session) ─────
    ("https://www.icsi.edu/media/webmodules/Consumer_Protection_E-Commerce_Rules_2020.pdf",
     "regulations", "ecommerce_rules_2020_full_text",
     "Consumer Protection (E-Commerce) Rules, 2020 - Full Text", "GoI"),
    ("https://www.indiacode.nic.in/ViewFileUploaded?path=AC_CEN_21_44_00007_201001_1517807327712%2Fnotificationindividualfile%2F&file=2-packgd_rules_2011.pdf",
     "regulations", "legal_metrology_packaged_commodities_rules_2011",
     "Legal Metrology (Packaged Commodities) Rules, 2011 - Full Text", "GoI"),
    ("https://www.nls.ac.in/wp-content/uploads/2021/04/Dark-Patterns.pdf",
     "ccpa", "ccpa_dark_patterns_guidelines_2023",
     "CCPA Guidelines for Prevention and Regulation of Dark Patterns, 2023", "CCPA"),
    ("https://fcsca.mizoram.gov.in/uploads/qms/e9121baff24698a3668010b6befee96c/consumer-protection-act-2019.pdf",
     "consumer_protection", "consumer_protection_act_2019_full_text",
     "Consumer Protection Act, 2019 - Full Text", "GoI"),
    ("https://consumeraffairs.gov.in/pages/consumer-protection-acts",
     "consumer_protection", "doca_consumer_protection_acts_page",
     "Department of Consumer Affairs - Consumer Protection Acts", "DoCA"),
    ("https://www.ondc.org/",
     "ondc", "ondc_official_home",
     "ONDC Official Website", "ONDC"),
    ("https://www.ondc.org/learn-about-ondc/",
     "ondc", "ondc_learn_about",
     "Learn About ONDC", "ONDC"),
    ("https://www.amazon.in/gp/help/customer/display.html?nodeId=202134240",
     "marketplaces/amazon", "amazon_grievance_redressal",
     "Amazon Pay Grievance Redressal Policy", "Amazon"),
]

# ───────────────────────────────────────────────────────────────────────────
# COMPLAINT TEMPLATES (written directly — no download needed)
# ───────────────────────────────────────────────────────────────────────────
TEMPLATES = {
    "fake_product_complaint.txt": """\
TO: The Grievance Officer / Nodal Officer
[Marketplace Name]

SUBJECT: Legal Notice — Sale of Counterfeit / Fake Product (Order ID: [ORDER_ID])

Dear Sir/Madam,

I ordered [Product Name] (Brand: [Brand]) from [Marketplace] on [Date].
Upon receipt, I found the product is a counterfeit item. The packaging,
build quality, and authenticity stickers clearly identify this as a fake.

Under the Consumer Protection (E-Commerce) Rules, 2020 and the Consumer
Protection Act, 2019, the marketplace is jointly and severally liable for
products sold on its platform. I demand:

1. Immediate full refund of INR [Amount].
2. Removal of the fraudulent seller listing.
3. A written response within 48 hours.

Failing compliance, I will file a complaint on the National Consumer Helpline
(1915) and approach the CCPA.

Yours faithfully,
[Customer Name] | [Order Date] | [Contact]
""",
    "refund_delay_complaint.txt": """\
TO: The Grievance Officer
[Marketplace Name]

SUBJECT: Notice of Unreasonable Refund Delay — Order ID: [ORDER_ID]

Dear Sir/Madam,

My order was returned/cancelled on [Date]. As per your stated refund policy,
the refund should have been credited within [5-7 / 7-10] business days.
It has now been [X] days and I have not received the refund of INR [Amount].

Under Section 2(11) of the Consumer Protection Act 2019, this constitutes
"deficiency of service." I demand immediate processing of the refund within
48 hours of receipt of this notice.

Failing this, I shall raise the matter with:
- National Consumer Helpline (1915 / www.consumerhelpline.gov.in)
- CCPA (Central Consumer Protection Authority)
- District Consumer Forum

[Customer Name] | [Email] | [Phone] | [Order Date]
""",
    "wrong_product_complaint.txt": """\
TO: The Grievance Officer
[Marketplace Name]

SUBJECT: Wrong Product Delivered — Order ID: [ORDER_ID]

I ordered [Correct Product] but received [Wrong Product] on [Delivery Date].
I have photographic evidence of the wrong product in the sealed package.

Under the Consumer Protection Act 2019 and your own "accurate product
description" obligation (E-Commerce Rules 2020, Rule 6), this is an
unlawful substitution. I demand:

1. Immediate free pickup of the wrong product.
2. Delivery of the correct product OR full refund.
3. Response within 24 hours.

[Customer Name] | [Order ID] | [Date]
""",
    "missing_package_complaint.txt": """\
TO: The Grievance Officer
[Marketplace Name]

SUBJECT: Non-Delivery Despite Delivery Confirmation — Order ID: [ORDER_ID]

My order (Order ID: [ORDER_ID]) is marked as "Delivered" on [Date], but I
have NOT received the package. The delivery OTP was not shared with me and
no delivery was attempted at my address.

Under Section 86 (Product Liability) of the Consumer Protection Act 2019,
you are liable. I demand:

1. CCTV / GPS proof of delivery attempt.
2. Re-delivery or full refund within 48 hours.
3. Courier partner escalation report.

[Customer Name] | [Delivery Address] | [Contact]
""",
    "warranty_claim_template.txt": """\
TO: The Customer Care / Warranty Department
[Brand / Manufacturer Name]

SUBJECT: Warranty Claim for Defective Product — Invoice No: [INVOICE_NO]

I purchased [Product Name] (Model: [Model No]) on [Date] from [Marketplace].
The product has developed the following defect within the warranty period
of [X] months: [Describe defect clearly].

As per the warranty card and Consumer Protection Act 2019 (Section 86 —
Product Liability), I am entitled to a FREE repair or replacement.

I request a service appointment or replacement unit within 7 working days.
Failure to comply will lead to a consumer complaint at the District Forum.

[Customer Name] | [Purchase Date] | [Serial Number]
""",
    "consumer_court_filing_guide.txt": """\
HOW TO FILE A CONSUMER COMPLAINT IN INDIA (2024 Guide)

Step 1: File with National Consumer Helpline
- Call 1915 or visit www.consumerhelpline.gov.in
- Register the complaint and get a ticket number
- Wait up to 30 days for resolution

Step 2: File with the Company Grievance Officer
- Every e-commerce company must publish a Nodal Officer contact
  (mandated by E-Commerce Rules 2020)
- Send a formal written complaint by email and retain the copy

Step 3: Approach Consumer Forum
- District Commission: Claims up to INR 50 Lakhs
- State Commission: Claims from INR 50 Lakhs to INR 2 Crore
- National Commission (NCDRC): Claims above INR 2 Crore

Documents Required:
- Invoice / Order confirmation
- Payment proof
- Correspondence with the company
- Photos of defective / wrong product
- Complaint reference numbers

Filing Fee: Nominal (INR 100-500 depending on claim amount)
You DO NOT need a lawyer. Consumer forums are designed for self-filing.
""",
}

SYNTHETIC_CASES = {
    "case_wrong_product.txt": """\
CASE: Wrong Product Delivered — Flipkart
Customer ordered Nike Air Max shoes (Size 10) for INR 7,499.
Received a cheap imitation with no brand markings.
Flipkart refused return saying "item not eligible."
Resolution: Customer cited Consumer Protection Act 2019 Section 2(11),
filed on National Consumer Helpline. Flipkart processed full refund in 3 days.
""",
    "case_refund_30_days_pending.txt": """\
CASE: Refund Pending 30 Days — Amazon India
Customer cancelled an order for a refrigerator (INR 32,000) via UPI.
Refund not received for 30 days despite multiple chat interactions.
Resolution: Customer initiated UPI chargeback via bank app + NCH complaint.
Amazon credited full refund within 48 hours.
""",
    "case_fake_branded_product.txt": """\
CASE: Counterfeit Product — Myntra
Customer purchased a "Levi's" T-shirt for INR 1,800.
Product had wrong stitching, faded logo, and no Levi's authenticity tag.
Myntra refused to accept return post 30-day window.
Resolution: CCPA complaint filed. Myntra issued refund and removed the listing.
""",
    "case_missing_blinkit.txt": """\
CASE: Missing Quick Commerce Order — Blinkit
Order of groceries worth INR 850 marked delivered via OTP.
Customer claims OTP was never shared; delivery agent cannot be traced.
Resolution: Blinkit customer support issued credit equivalent to full order.
""",
    "case_warranty_refused.txt": """\
CASE: Warranty Refused — OnePlus Phone (Amazon)
Customer's OnePlus 11 (INR 56,999) developed screen issues in 8th month.
OnePlus service centre claimed "physical damage" (which was disputed).
Resolution: Consumer Forum complaint; OnePlus replaced display free of charge
under warranty (physical damage exclusion did not apply to manufacturing defect).
""",
}

# ───────────────────────────────────────────────────────────────────────────

def html_to_text(html_bytes: bytes) -> str:
    soup = BeautifulSoup(html_bytes, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()
    lines = [l.strip() for l in soup.get_text("\n", strip=True).splitlines() if l.strip()]
    return "\n".join(lines)

def save_file(folder: str, name: str, content: bytes, ext: str, metadata: dict):
    dest = KNOWLEDGE_ROOT / folder
    dest.mkdir(parents=True, exist_ok=True)
    fp = dest / f"{name}.{ext}"
    fp.write_bytes(content)
    md = KNOWLEDGE_ROOT / "metadata" / folder
    md.mkdir(parents=True, exist_ok=True)
    (md / f"{name}.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    return fp

def download(url, folder, name, title, authority):
    print(f"  GET {url}")
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code not in (200, 301, 302):
            print(f"    -> HTTP {r.status_code} — skip")
            return False
        is_pdf = url.lower().endswith(".pdf") or "application/pdf" in r.headers.get("Content-Type","")
        if is_pdf:
            fp = save_file(folder, name, r.content, "pdf",
                           {"title":title,"authority":authority,"source_url":url,"domain":"ecommerce","type":"pdf"})
        else:
            text = html_to_text(r.content)
            if len(text) < 200:
                print(f"    -> Too short ({len(text)} chars) — skip")
                return False
            fp = save_file(folder, name, text.encode("utf-8"), "txt",
                           {"title":title,"authority":authority,"source_url":url,"domain":"ecommerce","type":"html_text","chars":len(text)})
        print(f"    -> {fp.stat().st_size//1024} KB => {fp.relative_to(KNOWLEDGE_ROOT)}")
        return True
    except Exception as e:
        print(f"    -> ERROR: {e}")
        return False

def write_templates():
    for fname, content in TEMPLATES.items():
        fp = KNOWLEDGE_ROOT / "complaint_templates" / fname
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content, encoding="utf-8")
        print(f"    -> Template written: {fp.name}")

def write_synthetic_cases():
    for fname, content in SYNTHETIC_CASES.items():
        fp = KNOWLEDGE_ROOT / "synthetic_cases" / fname
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content, encoding="utf-8")
        print(f"    -> Synthetic case written: {fp.name}")

def main():
    print("=" * 65)
    print("ECOMMERCE DOMAIN — COMPREHENSIVE DATA DOWNLOAD v2")
    print("=" * 65)

    print("\n[1/3] Writing complaint templates...")
    write_templates()

    print("\n[2/3] Writing synthetic test cases...")
    write_synthetic_cases()

    print(f"\n[3/3] Downloading {len(SOURCES)} live sources...")
    ok = fail = 0
    for (url, folder, name, title, authority) in SOURCES:
        if download(url, folder, name, title, authority):
            ok += 1
        else:
            fail += 1
        time.sleep(0.8)

    print("=" * 65)
    print(f"Templates:  {len(TEMPLATES)}")
    print(f"Syn. Cases: {len(SYNTHETIC_CASES)}")
    print(f"Downloaded: {ok}   Failed: {fail}")
    print("=" * 65)

if __name__ == "__main__":
    main()
