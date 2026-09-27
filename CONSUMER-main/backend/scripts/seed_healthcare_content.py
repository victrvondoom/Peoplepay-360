"""
Healthcare Domain - Authored Educational Content Seeder
Structured public-health education content (disease fact-sheets, vaccination
schedule tables, lab reference ranges, patient rights charter summary,
medical terminology glossary) for topics not fully covered by a single
scrapable primary source, grounded in publicly known, well-established
guidance from WHO, MoHFW/NHM (Universal Immunization Programme), NABH, and
the Charter of Patients' Rights (India).

IMPORTANT: All content here is general, evidence-based educational
information only. It is NOT a diagnosis and NOT a substitute for
professional medical advice — every document should be read alongside the
platform-wide disclaimer that users must consult a qualified healthcare
professional for decisions about their own care. Reference ranges and
schedules can vary by lab, manufacturer, and updated national guidance;
always confirm with a treating clinician or the current official schedule.
"""
import json
from pathlib import Path

KNOWLEDGE_ROOT = Path(__file__).resolve().parents[2] / "knowledge" / "healthcare"


def save(folder, filename, title, authority, category, content):
    dest_dir = KNOWLEDGE_ROOT / folder
    dest_dir.mkdir(parents=True, exist_ok=True)
    filepath = dest_dir / filename
    filepath.write_text(content.strip() + "\n", encoding="utf-8")
    meta_dir = KNOWLEDGE_ROOT / "metadata" / folder
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / f"{Path(filename).stem}.json").write_text(
        json.dumps({"title": title, "authority": authority, "source_url": None,
                    "domain": "healthcare", "type": "authored_guide", "category": category},
                   indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"  wrote {filepath.relative_to(KNOWLEDGE_ROOT)}")


DOCUMENTS = [
    # ── Vaccination ─────────────────────────────────────────
    {
        "folder": "vaccination", "filename": "national_immunization_schedule_india.txt",
        "title": "National (Universal) Immunization Programme Schedule — India, Overview",
        "authority": "MoHFW / National Health Mission", "category": "schedule",
        "content": """
NATIONAL IMMUNIZATION SCHEDULE — INDIA (UNIVERSAL IMMUNIZATION PROGRAMME) — OVERVIEW

This is a general educational summary of the vaccine groups covered under
India's Universal Immunization Programme (UIP), run by the Ministry of
Health and Family Welfare / National Health Mission. It is NOT a substitute
for the current official schedule — always confirm exact ages, doses, and
any updates with your pediatrician, nearest government health facility, or
the current MoHFW/NHM immunization schedule, since schedules are
periodically revised (e.g. new vaccines added, dose timing adjusted).

At birth: BCG (tuberculosis), OPV-0 (oral polio, birth dose), Hepatitis B
birth dose.

6, 10, 14 weeks: OPV (oral polio) doses, Pentavalent vaccine (Diphtheria,
Pertussis, Tetanus, Hepatitis B, Hib), Rotavirus vaccine, Pneumococcal
Conjugate Vaccine (PCV), Inactivated Polio Vaccine (IPV, given with the
second dose in many state schedules).

9-12 months: Measles-Rubella (MR) first dose, Japanese Encephalitis (JE,
first dose, in endemic districts), Vitamin A (first dose).

16-24 months: DPT first booster, OPV booster, MR second dose, JE second
dose (in endemic districts), Vitamin A (repeat doses up to 5 years in many
state programmes).

5-6 years: DPT second booster.

10 and 16 years: Td (Tetanus and adult-dose Diphtheria) — replacing the
older TT vaccine in the UIP schedule.

Pregnant women: Td/TT doses per the antenatal schedule to protect against
neonatal tetanus, generally given during antenatal care visits.

Why timing matters: Doses are spaced to build adequate immunity while
minimizing the number of clinic visits; missing a dose does not usually
mean restarting the whole series — a health worker can advise a catch-up
schedule. Vaccines under the UIP are provided free of cost at government
health facilities in India.

This overview does not include every vaccine now available (e.g. some
states/private providers also offer HPV, varicella, typhoid conjugate, or
additional pneumococcal/rotavirus formulations) — ask your health provider
which vaccines are recommended for your child's age, region, and health
status.
""",
    },
    {
        "folder": "symptoms", "filename": "when_to_seek_emergency_care.txt",
        "title": "When to Seek Emergency Care — General Red-Flag Symptoms",
        "authority": "General Public Health Education", "category": "emergency_guidance",
        "content": """
WHEN TO SEEK EMERGENCY CARE — GENERAL RED-FLAG SYMPTOMS

This is general educational information about symptoms that typically
warrant urgent/emergency medical attention rather than a routine
appointment. It is NOT a diagnostic tool — if you are experiencing any of
these symptoms, seek emergency care immediately (call local emergency
services or go to the nearest emergency department) rather than relying on
this or any other written guide.

Possible heart attack: chest pain or pressure lasting more than a few
minutes (or that comes and goes), pain spreading to the arm/jaw/back,
shortness of breath, cold sweat, nausea, or lightheadedness.

Possible stroke — remember "FAST": Face drooping on one side, Arm
weakness/numbness on one side, Speech difficulty or slurring, Time to call
emergency services immediately — stroke treatment is highly time-sensitive.

Severe breathing difficulty: gasping for air, blue-tinged lips/face,
inability to speak in full sentences, or a known severe allergy with
swelling of the face/throat and breathing difficulty (possible anaphylaxis).

Severe bleeding or major trauma: bleeding that does not stop with firm
pressure, a deep wound, or a significant fall/accident with suspected
fracture or head injury (especially with confusion, repeated vomiting, or
loss of consciousness after a head injury).

High fever with specific warning signs: fever with a stiff neck and
severe headache, fever with a rash that does not fade under pressure,
fever with confusion, or fever with difficulty breathing.

Dehydration danger signs, especially in infants/young children: very
little or no urine for 8+ hours, sunken eyes, extreme lethargy or
difficulty waking, dry mouth with no tears when crying, or persistent
vomiting/diarrhea that prevents fluid intake.

Severe abdominal pain: sudden, severe, or worsening abdominal pain,
especially with fever, vomiting blood, or a rigid/tender abdomen.

Pregnancy warning signs: heavy vaginal bleeding, severe abdominal pain,
severe headache with visual changes or swelling (possible pre-eclampsia
warning signs), reduced fetal movement, or fluid leakage before term.

General principle: if in doubt, especially for infants, elderly patients,
pregnant women, or anyone with a chronic condition (heart disease,
diabetes, immunosuppression), it is safer to seek urgent evaluation than to
wait. This guide cannot account for your specific medical history — a
qualified healthcare professional or emergency service is the appropriate
next step for any symptom that concerns you.
""",
    },
    # ── Diagnostics / Lab reference ────────────────────────
    {
        "folder": "diagnostics", "filename": "common_lab_test_reference_ranges.txt",
        "title": "Common Lab Tests — General Reference Range Overview",
        "authority": "General Public Health Education", "category": "reference_ranges",
        "content": """
COMMON LAB TESTS — GENERAL REFERENCE RANGE OVERVIEW (EDUCATIONAL ONLY)

Reference ranges vary by laboratory, analyzer, patient age/sex, and
population, and can change with updated clinical guidance. The ranges
below are widely-cited general adult ranges for orientation only — always
use the reference range printed on your own lab report (each lab states
its own range), and discuss the result with your doctor, who interprets it
in the context of your full clinical picture, not the number alone.

Fasting blood glucose: roughly 70-100 mg/dL is commonly cited as a normal
fasting range in adults without diabetes; 100-125 mg/dL is often flagged as
"prediabetes" range; 126 mg/dL or higher on more than one occasion is one
of the criteria clinicians use when evaluating for diabetes — diagnosis is
made by a doctor using multiple criteria, not a single home reading.

HbA1c (glycated hemoglobin, reflects ~3-month average blood sugar): below
5.7% is commonly cited as normal; 5.7-6.4% as prediabetes range; 6.5% or
higher (confirmed) as consistent with diabetes. For people already
diagnosed with diabetes, doctors often set an individualized HbA1c target
(commonly below 7%, but this varies by patient).

Blood pressure: commonly cited categories include normal (below
120/80 mmHg), elevated (120-129 systolic and below 80 diastolic), Stage 1
hypertension (130-139/80-89 mmHg), and Stage 2 hypertension (140/90 mmHg or
higher) — a single elevated reading is not a diagnosis; clinicians look at
repeated readings, often including home or ambulatory monitoring.

Complete Blood Count (CBC) — commonly referenced adult ranges: hemoglobin
roughly 13.5-17.5 g/dL (men) and 12.0-15.5 g/dL (women); white blood cell
count roughly 4,000-11,000 cells/mcL; platelet count roughly
150,000-450,000/mcL. Ranges differ notably by lab and by age/pregnancy
status.

Lipid profile: total cholesterol below 200 mg/dL is commonly cited as
desirable; LDL ("bad" cholesterol) targets vary by individual
cardiovascular risk (a doctor sets your target, which may be much lower
than a generic "normal" if you have heart disease risk factors); HDL
("good" cholesterol) above roughly 40 mg/dL (men) / 50 mg/dL (women) is
commonly cited as more favorable; triglycerides below 150 mg/dL is commonly
cited as normal.

Thyroid-Stimulating Hormone (TSH): roughly 0.4-4.0 mIU/L is a commonly
cited general adult range, though "normal" varies by lab, age, and
pregnancy status; a value outside this range does not by itself indicate a
specific thyroid condition without further evaluation.

Kidney function (creatinine, eGFR): reference creatinine ranges differ by
sex and muscle mass; eGFR above 90 mL/min/1.73m^2 is often considered
normal kidney function, with lower values used to stage chronic kidney
disease severity — always interpreted by a clinician alongside other
factors.

Key takeaway: a value slightly outside the printed reference range is not
automatically a disease and does not mean you should self-medicate or
self-diagnose — bring the report to a qualified healthcare professional for
interpretation in the context of your symptoms and history.
""",
    },
    {
        "folder": "diagnostics", "filename": "understanding_your_lab_report_faqs.txt",
        "title": "Understanding Your Lab Report — FAQs",
        "authority": "General Public Health Education", "category": "faq",
        "content": """
UNDERSTANDING YOUR LAB REPORT — FAQs

Q: My result is flagged "H" (high) or "L" (low) — does that mean something
   is wrong?
A: A flag means the result falls outside the lab's stated reference range,
   not that a disease is present. Reference ranges are statistical (often
   covering the middle ~95% of a healthy reference population), so a small
   percentage of healthy people will naturally fall just outside them. Your
   doctor interprets the flagged value together with your symptoms,
   history, and other tests.

Q: Why do two different labs give different reference ranges for the same
   test?
A: Different labs may use different analyzers, reagents, and reference
   population studies, so their normal ranges can differ slightly even for
   the same test. This is why it's best to compare results from the same
   lab over time when tracking a trend, and always read the range printed
   on that specific report.

Q: What does "fasting" mean for a blood test, and why does it matter?
A: Fasting typically means no food or caloric drink for a specified window
   (commonly 8-12 hours, water is usually allowed) before the blood draw —
   required for tests like fasting glucose and lipid profile because eating
   can temporarily raise glucose and triglyceride levels and produce a
   misleading result.

Q: Can medications or supplements affect my lab results?
A: Yes — many medications, supplements, and even recent strenuous exercise
   or dehydration can shift lab values. Tell your doctor about everything
   you're taking (including over-the-counter drugs and supplements) before
   a test, and mention it again when discussing results if you're unsure
   whether something might have affected them.

Q: Should I search my results online and self-treat based on what I find?
A: General information (like this guide) can help you understand what a
   test measures, but it cannot account for your full medical history, other
   test results, or physical examination findings. Please discuss any
   abnormal or concerning result with a qualified healthcare professional
   rather than self-diagnosing or self-medicating based on an online search.
""",
    },
    # ── Patient rights ──────────────────────────────────────
    {
        "folder": "patient_rights", "filename": "patient_rights_charter_india_summary.txt",
        "title": "Charter of Patients' Rights (India) — Summary Overview",
        "authority": "MoHFW / NHRC-linked Charter of Patients' Rights", "category": "patient_rights",
        "content": """
CHARTER OF PATIENTS' RIGHTS (INDIA) — SUMMARY OVERVIEW

India's Charter of Patients' Rights, developed with reference to the
National Human Rights Commission and circulated by the Ministry of Health
and Family Welfare for adoption by states/hospitals, sets out rights
patients can expect when receiving healthcare. This is a general summary
for educational purposes — the exact enumerated rights and their
implementation can vary by state notification and by individual hospital
policy; ask your treating hospital for its specific patient rights policy
and grievance/redressal contact.

Commonly enumerated rights include:

1. Right to information: to receive understandable information about your
   diagnosis, proposed treatment, and the qualifications of those treating
   you, in a language/manner you can understand.

2. Right to records and reports: to receive copies of your case papers,
   test reports, and discharge summary, generally within a defined
   timeframe of request.

3. Right to emergency medical care: to receive emergency stabilizing
   treatment regardless of ability to pay, particularly relevant at
   hospitals bound by such obligations (e.g. under Supreme Court
   directions on emergency care and various state provisions).

4. Right to informed consent: to receive a clear explanation of a
   procedure, its risks, benefits, and alternatives, in an understandable
   manner, before consenting — and the right to refuse treatment/leave
   against medical advice, having been informed of the consequences.

5. Right to confidentiality, human dignity, and privacy: to have your
   medical information kept confidential, and to be treated with dignity
   during examination, procedures, and treatment.

6. Right to a second opinion: to seek a second opinion from another
   qualified doctor without facing denial of records or treatment for
   doing so.

7. Right to non-discrimination: to receive care without discrimination on
   grounds such as illness, disability, gender identity, sexual
   orientation, religion, caste, or economic status.

8. Right to transparency in rates and an estimated bill: to be informed of
   the expected cost of treatment/care and any changes, and to receive an
   itemized bill on request.

9. Right to a proper referral and transfer: to receive an appropriate
   referral and stabilization prior to transfer if a facility cannot
   provide needed care.

10. Right to patient education: to receive information about your
    condition, treatment, and rehabilitation options in a manner suited to
    your understanding.

11. Right to be heard and seek redressal: to file a grievance about the
    quality or conduct of care through the hospital's grievance mechanism,
    and to escalate to the relevant State Medical Council, Clinical
    Establishments regulator (where applicable), or consumer forum if
    unresolved.

This summary is general education, not legal advice — the specific rights
that legally apply can depend on your state's adoption of the Charter, the
type of facility (public/private, and whether it is a "clinical
establishment" registered under applicable state/central law), and the
nature of the treatment.
""",
    },
    # ── Hospital quality ────────────────────────────────────
    {
        "folder": "hospital_quality", "filename": "nabh_accreditation_standards_overview.txt",
        "title": "NABH Hospital Accreditation Standards — Overview",
        "authority": "National Accreditation Board for Hospitals & Healthcare Providers (NABH)", "category": "accreditation",
        "content": """
NABH HOSPITAL ACCREDITATION STANDARDS — OVERVIEW

The National Accreditation Board for Hospitals & Healthcare Providers
(NABH), a constituent board of the Quality Council of India, sets voluntary
accreditation standards that Indian hospitals can be assessed against.
NABH accreditation is a marker that a hospital has been independently
assessed against defined quality and patient-safety standards — it is not
itself a guarantee of outcome for any individual patient, and not every
functioning, licensed hospital in India is NABH-accredited (accreditation
is voluntary, unlike basic state licensing/registration which is generally
mandatory).

Broad standard chapters commonly used in hospital accreditation frameworks
like NABH include:

- Access, Assessment and Continuity of Care (AAC): how patients are
  registered, assessed, and their care coordinated across departments.
- Care of Patients (COP): standards for how clinical care, including
  high-risk care (ICU, emergency, obstetric), is planned and delivered.
- Management of Medication (MOM): safe prescription, storage, dispensing,
  and administration of medicines, including look-alike/sound-alike drug
  safeguards.
- Patient Rights and Education (PRE): the hospital's obligations to
  inform, involve, and respect patients and their families, aligned with
  charters like the Charter of Patients' Rights.
- Hospital Infection Control (HIC): infection prevention practices,
  surveillance, and outbreak response.
- Continuous Quality Improvement (CQI): tracking of quality/safety
  indicators and improvement cycles.
- Responsibility of Management (ROM): governance, ethics, and
  organizational accountability for quality and safety.
- Facility Management and Safety (FMS): physical infrastructure, fire
  safety, biomedical waste management, and equipment maintenance.
- Human Resource Management (HRM): staff credentialing, training, and
  competency assessment.
- Information Management System (IMS): medical record-keeping and data
  management standards.

Why this matters to patients: accreditation status is one input (not the
only one) when choosing a hospital, alongside your doctor's recommendation,
the facility's experience with your specific condition, distance/
accessibility, and cost/insurance considerations. You can generally ask a
hospital directly about its accreditation status, and independently check
current status via NABH's public accredited-hospital listing.

This is general educational information about how hospital quality
frameworks work, not an endorsement or rating of any specific facility.
""",
    },
    # ── Drug safety ─────────────────────────────────────────
    {
        "folder": "drug_safety", "filename": "medication_safety_faqs.txt",
        "title": "Medication Safety — FAQs (Interactions, Generics, Reporting Adverse Reactions)",
        "authority": "CDSCO / Pharmacovigilance Programme of India (PvPI)", "category": "drug_safety",
        "content": """
MEDICATION SAFETY — FAQs

Q: Are generic medicines as safe/effective as branded ones?
A: In India, generic drugs approved by the Central Drugs Standard Control
   Organisation (CDSCO) are required to meet the same quality, safety, and
   (for oral solid generics) bioequivalence standards as the reference
   branded product. Cost differences mainly reflect marketing/branding, not
   a difference in the regulatory quality bar. If you have a specific
   concern about switching between a brand and its generic, discuss it with
   your prescribing doctor or pharmacist rather than switching unilaterally
   for a narrow-therapeutic-index medicine.

Q: How do I know if two medicines I'm taking might interact?
A: Always give every doctor and pharmacist a complete list of everything
   you take, including over-the-counter medicines, supplements, and herbal/
   ayurvedic products, since interactions aren't limited to prescription
   drugs. Pharmacists can check for known interactions at the point of
   dispensing; do not rely solely on informal internet searches to decide
   whether a combination is safe for you.

Q: What is a CDSCO drug alert, and where can I check for one?
A: CDSCO periodically issues alerts on substandard/spurious drug batches,
   safety-related regulatory actions, and Not of Standard Quality (NSQ)
   findings from testing. If you've been advised a specific medicine has
   been flagged, check CDSCO's public notices/alerts section (cdsco.gov.in)
   or ask your pharmacist, rather than stopping a prescribed medicine
   without medical advice based on an unverified message.

Q: What should I do if I think I've had an adverse drug reaction?
A: Report it — India's Pharmacovigilance Programme of India (PvPI),
   coordinated by the Indian Pharmacopoeia Commission under CDSCO, collects
   Adverse Drug Reaction (ADR) reports from patients and healthcare
   providers to monitor medicine safety after they reach the market. Tell
   your treating doctor or pharmacist promptly, and seek urgent care for
   any severe reaction (difficulty breathing, swelling of face/throat,
   severe rash, or fainting).

Q: Is it safe to stop a prescribed medicine once I feel better?
A: Not necessarily — for many conditions (e.g. antibiotics, blood pressure
   or diabetes medication, tuberculosis treatment), stopping early can
   allow the underlying condition to worsen or, for antibiotics/TB
   treatment, contribute to drug resistance. Always confirm the intended
   duration/stopping plan with your prescriber rather than deciding to stop
   on your own.

This is general medication-safety education, not a substitute for advice
from your prescribing doctor or pharmacist about your specific medicines.
""",
    },
    # ── Treatment guidelines ────────────────────────────────
    {
        "folder": "treatment_guidelines", "filename": "evidence_based_treatment_guideline_overview.txt",
        "title": "Evidence-Based Clinical Guidelines — How They Work",
        "authority": "General Public Health Education", "category": "guidelines_overview",
        "content": """
EVIDENCE-BASED CLINICAL GUIDELINES — HOW THEY WORK (OVERVIEW)

Clinical practice guidelines (sometimes called Standard Treatment
Guidelines, or STGs) are recommendations developed by expert bodies —
such as WHO, ICMR, national medical associations, or MoHFW-convened expert
committees for specific programmes (e.g. tuberculosis, malaria, maternal
health) — based on a structured review of the available clinical evidence,
intended to help clinicians (not patients) make consistent, evidence-based
treatment decisions.

Key things to understand about guidelines as a patient:

- Guidelines describe what generally works best for a typical patient with
  a given condition, based on population-level evidence (clinical trials,
  systematic reviews); your doctor still individualizes care based on your
  specific health profile, other conditions, allergies, pregnancy status,
  and preferences, which may reasonably lead to a different plan.
- Guidelines are periodically revised as new evidence emerges — a guideline
  from several years ago may no longer reflect current best practice, so
  always check for the most current version from the issuing body (WHO,
  ICMR, or the relevant national programme) rather than relying on an
  outdated document.
- India-specific programmes with published treatment guidelines include,
  for example, the Revised National TB Control Programme / Ni-kshay
  framework for tuberculosis, the National Vector Borne Disease Control
  Programme guidance for malaria/dengue, and ICMR's periodically updated
  guidance across multiple disease areas.
- "Evidence-based" does not mean "one-size-fits-all" — it means the
  recommendation is grounded in the best available research evidence,
  weighed against clinical expertise and, ideally, patient values/
  preferences, per the standard definition of evidence-based medicine.

Why this matters here: information in this knowledge base is drawn from
such publicly published guidance and fact sheets to give you accurate,
general orientation on a topic — it summarizes what established guidance
generally says, but it cannot replace an individualized clinical assessment
by a qualified healthcare professional who knows your specific case.
""",
    },
    # ── Public health advisory ──────────────────────────────
    {
        "folder": "public_health", "filename": "outbreak_public_health_advisory_guide.txt",
        "title": "Public Health Advisories and Outbreak Notification — How India's System Works",
        "authority": "NCDC / Integrated Disease Surveillance Programme (IDSP)", "category": "public_health_advisory",
        "content": """
PUBLIC HEALTH ADVISORIES AND OUTBREAK NOTIFICATION — HOW INDIA'S SYSTEM WORKS

India tracks and responds to disease outbreaks and seasonal public health
risks primarily through the Integrated Disease Surveillance Programme
(IDSP), coordinated by the National Centre for Disease Control (NCDC) under
the Ministry of Health and Family Welfare, working with state
surveillance units and district/sub-district reporting units.

How it generally works:
- Health facilities and surveillance units report defined "presumptive"
  case counts for certain diseases on a routine (often weekly) basis, which
  can trigger further investigation if numbers cross an expected threshold
  for that time/place (an "outbreak signal").
- When an outbreak is confirmed, state health departments typically issue
  local advisories (e.g. fogging/vector control for dengue, water-source
  advisories for cholera/diarrheal disease after floods, isolation guidance
  for a respiratory outbreak) alongside NCDC/MoHFW national guidance where
  relevant.
- Seasonal advisories are common and recurring: pre-monsoon and monsoon
  advisories for vector-borne diseases (dengue, malaria, chikungunya) and
  water-borne diseases; summer advisories for heat-related illness; winter
  advisories for cold-wave-related risks and respiratory illness spikes.

What patients/the public can do:
- Follow official advisories from MoHFW, NCDC, ICMR, WHO, and your state
  health department rather than unverified social media claims, especially
  during an active outbreak.
- Report unusual disease clusters (e.g. many people in one area with
  similar symptoms in a short time) to the local health authority/primary
  health centre — this is exactly the kind of signal surveillance systems
  rely on.
- For international travel, check both the destination country's advisories
  and WHO's disease outbreak news for relevant precautions/vaccinations.

This is a general overview of how public health surveillance and
advisories function, not a live outbreak alert — for current, location-
specific advisories, check MoHFW, NCDC (ncdc.mohfw.gov.in), your state
health department, or WHO directly.
""",
    },
    # ── Diseases (not otherwise covered by scraped sources) ─
    {
        "folder": "diseases", "filename": "influenza_and_covid19_fact_sheet.txt",
        "title": "Influenza and COVID-19 — General Fact Sheet",
        "authority": "General Public Health Education", "category": "respiratory_illness",
        "content": """
INFLUENZA AND COVID-19 — GENERAL FACT SHEET

This is general educational information about two common respiratory
illnesses. It does not diagnose your symptoms — testing and clinical
evaluation by a healthcare professional are needed to tell these apart
from each other and from other respiratory infections, since symptoms
substantially overlap.

Influenza ("flu"): a contagious respiratory illness caused by influenza
viruses. Common symptoms include sudden fever, chills, cough, sore throat,
body aches, headache, and fatigue; some people (especially children) may
also have vomiting/diarrhea. Most healthy people recover within about a
week to 10 days, but flu can cause severe illness in young children, older
adults, pregnant women, and people with chronic conditions. Annual
vaccination is the primary prevention tool recommended in many national
programmes for higher-risk groups.

COVID-19: caused by the SARS-CoV-2 virus. Symptoms range widely from mild
(sore throat, runny nose, mild cough, fatigue, loss of taste/smell in some
cases) to severe (significant shortness of breath, low oxygen levels,
pneumonia), and can also be asymptomatic. Risk of severe illness is higher
in older adults and people with certain underlying conditions or weakened
immune systems, though anyone can be affected.

General preventive measures commonly recommended for both: staying current
with recommended vaccinations, good hand hygiene, staying home when
symptomatic to reduce spread, and improved ventilation in shared indoor
spaces. Specific current recommendations (vaccine timing, isolation
duration, testing guidance) change over time — check current guidance from
MoHFW/ICMR or WHO rather than relying on advice from earlier phases of the
pandemic, which may be outdated.

When to seek care: difficulty breathing, persistent chest pain/pressure,
new confusion, inability to stay awake, or bluish lips/face are warning
signs that need urgent medical attention regardless of which virus is
suspected. Mild symptoms can typically be managed with rest, fluids, and
symptomatic care as advised by a healthcare professional, who can also
advise on testing and any antiviral treatment appropriate for your risk
level.
""",
    },
    {
        "folder": "diseases", "filename": "diarrheal_disease_and_ors_fact_sheet.txt",
        "title": "Diarrheal Disease and Oral Rehydration — General Fact Sheet",
        "authority": "General Public Health Education (WHO/UNICEF ORS-Zinc protocol)", "category": "diarrheal_disease",
        "content": """
DIARRHEAL DISEASE AND ORAL REHYDRATION — GENERAL FACT SHEET

Diarrheal disease remains a major cause of illness, particularly serious in
young children, largely due to dehydration rather than the infection
itself. This is general educational information, not a treatment protocol
for a specific patient — always consult a healthcare professional,
especially for infants, young children, elderly patients, or anyone with a
chronic illness.

Common causes: contaminated food or water (bacterial, viral, or parasitic
infection), and occasionally non-infectious causes (medication side
effects, food intolerance). Most acute diarrheal illness in otherwise
healthy people is self-limited.

The WHO/UNICEF-recommended core home management for acute watery diarrhea,
especially in children, centers on:
1. Oral Rehydration Solution (ORS) — a precise glucose-salt solution that
   helps the gut absorb fluid even during diarrhea; prepared using ORS
   packets dissolved in the exact specified amount of clean water (using
   the wrong ratio reduces effectiveness or can be unsafe) — do not
   substitute a homemade mixture unless a healthcare provider has taught
   you the correct proportions.
2. Zinc supplementation for children (per the WHO/UNICEF protocol, commonly
   given for about 10-14 days), which has been shown to reduce the
   duration and severity of the episode and reduce risk of recurrence in
   the following months — dosing should follow product/clinician guidance
   for the child's age.
3. Continued feeding, including continued breastfeeding for infants —
   withholding food is generally not recommended for most diarrheal
   illness.

Warning signs that need urgent medical attention: blood in stool, high
fever, signs of dehydration (very little urine, sunken eyes, lethargy, dry
mouth, in infants a sunken soft spot), diarrhea lasting more than a few
days without improvement, or inability to keep fluids down due to
repeated vomiting.

Prevention: safe drinking water, handwashing with soap (especially before
eating/feeding and after using the toilet), safe food handling, and
rotavirus vaccination (part of many national immunization schedules,
including India's UIP) to reduce a major cause of severe diarrheal illness
in infants.

This is general information — a healthcare professional should evaluate
any diarrheal illness with warning signs, in infants, or that does not
improve as expected.
""",
    },
    # ── Glossary ─────────────────────────────────────────────
    {
        "folder": "faqs", "filename": "medical_terminology_glossary.txt",
        "title": "Common Medical Terminology and Abbreviations — Glossary",
        "authority": "General Public Health Education", "category": "glossary",
        "content": """
COMMON MEDICAL TERMINOLOGY AND ABBREVIATIONS — GLOSSARY

A plain-language glossary of terms/abbreviations frequently seen on
prescriptions, lab reports, and discharge summaries. This is general
educational information to help you understand documents you already
have — always ask your doctor or pharmacist to explain anything unclear
about your specific report or prescription.

BP — Blood Pressure. The force of blood against artery walls, recorded as
systolic/diastolic (e.g. 120/80 mmHg).

HbA1c (A1C) — Glycated hemoglobin; reflects average blood glucose over
roughly the prior 2-3 months, used to monitor/diagnose diabetes.

CBC — Complete Blood Count; measures red cells, white cells, and
platelets, used to screen for anemia, infection, and clotting-related
issues among other things.

LFT — Liver Function Test panel (e.g. bilirubin, liver enzymes such as
ALT/AST, albumin), used to assess liver health.

KFT / RFT — Kidney (Renal) Function Test panel (e.g. creatinine, blood
urea, eGFR), used to assess kidney function.

BMI — Body Mass Index; weight relative to height, used as a general
population-level screening measure, not a complete individual health
assessment on its own.

TSH — Thyroid-Stimulating Hormone; the primary screening test for thyroid
function.

MRI — Magnetic Resonance Imaging; a scan using magnetic fields (no
ionizing radiation) to visualize soft tissue in detail.

CT (CT scan) — Computed Tomography; a detailed cross-sectional X-ray-based
scan.

Biopsy — Removal of a small tissue sample for laboratory examination,
often to check for cancer or confirm a diagnosis.

Prognosis — The likely course/outcome of a disease, as assessed by a
clinician; distinct from "diagnosis," which identifies the condition
itself.

Comorbidity — A medical condition existing alongside a primary condition
(e.g. diabetes as a comorbidity in a patient being treated for heart
disease).

Contraindication — A specific situation/condition in which a drug,
procedure, or treatment should NOT be used because it could be harmful.

Prophylaxis — Preventive treatment given to prevent a disease/condition
before it occurs (e.g. antibiotic prophylaxis before certain surgeries).

Idiopathic — A term meaning the cause of a condition is unknown.

Acute vs. Chronic — Acute describes a condition with sudden onset and
usually short duration; chronic describes a condition that is long-lasting
or persistent, often requiring ongoing management.

This glossary is not exhaustive and definitions are simplified for general
understanding — for terms specific to your own diagnosis or report, ask
your treating healthcare professional.
""",
    },
]


def main():
    print("=" * 60)
    print("HEALTHCARE DOMAIN — AUTHORED EDUCATIONAL CONTENT SEEDING")
    print("=" * 60)
    for doc in DOCUMENTS:
        save(doc["folder"], doc["filename"], doc["title"], doc["authority"], doc["category"], doc["content"])
    print(f"Done. Wrote {len(DOCUMENTS)} authored documents.")


if __name__ == "__main__":
    main()
