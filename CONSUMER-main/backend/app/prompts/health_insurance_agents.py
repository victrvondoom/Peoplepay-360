from app.models.domain import Domain
from app.prompts.consumer_advocacy import SYSTEM_GUARDRAILS, DOMAIN_PROMPTS
from app.prompts.domain_profiles import get_profile


def _base(domain: Domain, task: str, case_summary: str, context: str = "", evidence: str = "") -> str:
    domain_prompt = DOMAIN_PROMPTS.get(domain, "")
    parts = [
        SYSTEM_GUARDRAILS,
        f"Domain instructions:\n{domain_prompt}",
        f"Task:\n{task}",
        f"Case summary:\n{case_summary}",
    ]
    if context:
        parts.append(f"Retrieved knowledge:\n{context[:12000]}")
    if evidence:
        parts.append(f"Uploaded case evidence:\n{evidence[:16000]}")
    return "\n\n".join(parts)


def research_prompt(domain: Domain, case_summary: str, context: str, graph_context: str = "") -> str:
    profile = get_profile(domain)
    domain_label = domain.value.replace("_", " ")
    questions = "\n".join(f"{i + 1}. {q}" for i, q in enumerate(profile.research_questions))
    task = f"""You are the Research Agent for a {domain_label} case involving a {profile.entity} and a {profile.counterparty}.
Answer ONLY from supplied retrieved knowledge and graph context.
Return JSON with exactly this schema:

{{
  "applicable_clauses": ["clause, term, or rule 1", "clause, term, or rule 2"],
  "possible_exclusions": ["exclusion or limitation 1 that the {profile.counterparty} may invoke"],
  "waiting_periods": ["any relevant timelines, waiting periods, or deadlines -- leave empty list if none apply"],
  "regulations": ["{profile.regulator} rule/circular/provision X"],
  "summary": "One paragraph research summary citing specific sources.",
  "confidence": 0.75
}}

Rules -- answer these questions specifically for this case:
{questions}
Cite sources explicitly. If uncertain, state what document is missing.
RETURN JSON ONLY. No markdown fences. Research Agent output."""
    if graph_context:
        context = f"{context}\n\nInstitutional graph memory:\n{graph_context}"
    return _base(domain, task, case_summary, context)


def evidence_prompt(domain: Domain, case_summary: str, context: str, evidence: str, has_uploaded_documents: bool = True) -> str:
    profile = get_profile(domain)
    domain_label = domain.value.replace("_", " ")
    schema_lines = ",\n  ".join(f'"{key}": "{example}"' for key, example in profile.evidence_schema.items())
    if has_uploaded_documents:
        relevance_instruction = (
            "FIRST, decide whether the uploaded evidence actually relates to the case summary below (same case, "
            "same institution/counterparty, same underlying issue -- not just the same broad domain). If the "
            "uploaded evidence is about a different, unrelated matter (wrong institution, wrong transaction/"
            "incident, or simply doesn't mention anything from the case summary), set \"evidence_relevant\" to "
            "false, leave every extracted field an empty string, and say so plainly in \"summary\" -- do NOT "
            "invent or guess values to fill the schema just because a document was uploaded."
        )
        summary_hint = "Concise one-paragraph extraction summary, or a note that the uploaded evidence doesn't match the case if evidence_relevant is false."
    else:
        # No document was uploaded at all -- the case summary text below is
        # being reused as the only source to extract structured facts from,
        # NOT a stand-in "uploaded document" to judge relevance against.
        # Asking the model to judge whether the case summary "relates to"
        # itself is a meaningless comparison that was producing false
        # evidence_relevant=false verdicts, which then rendered as "the
        # document you uploaded does not appear to relate to this case" --
        # confusing and wrong when the user never uploaded anything.
        relevance_instruction = (
            "No documents were uploaded for this case -- extract whatever structured facts you can from the case "
            "summary text alone. Always set \"evidence_relevant\" to true (there is no separate uploaded document "
            "to judge as relevant or not); leave a field empty string only if that specific fact genuinely isn't "
            "present in the case summary."
        )
        summary_hint = "Concise one-paragraph summary of what could be extracted from the case summary alone, noting this is based on the written description only, not uploaded documents."
    task = f"""You are the Evidence Agent. Read the case evidence below and extract structured facts for this {domain_label} case.

{relevance_instruction}

Return JSON with exactly this schema:

{{
  "evidence_relevant": true,
  {schema_lines},
  "documents_missing": ["Document or fact still needed"],
  "key_dates": ["Event: date"],
  "summary": "{summary_hint}"
}}

Be strictly factual. Do not invent values not present in the evidence. Leave fields empty string if not found there.
RETURN JSON ONLY. No markdown fences. Evidence Agent output."""
    return _base(domain, task, case_summary, context, evidence)


def strategy_prompt(
    domain: Domain,
    case_summary: str,
    context: str,
    evidence_summary: str,
    research_summary: str,
    review_feedback: str = "",
) -> str:
    profile = get_profile(domain)
    escalation_json = ", ".join(f'"{step}"' for step in profile.escalation_path)
    feedback_block = ""
    if review_feedback:
        feedback_block = f"""

The Review Agent rejected the previous version of this strategy. You MUST fix every issue
below, not just acknowledge it -- do not repeat a hallucinated claim or a miscited clause a
second time, and do not soften a flagged weak argument instead of replacing it with one the
retrieved research/evidence actually supports:
{review_feedback}"""

    if not profile.is_dispute:
        task = f"""You are the Response Planning Agent for an informational query (not a dispute -- there is no counterparty to appeal to).
Return JSON with exactly this schema:

{{
  "can_appeal": "N/A",
  "success_probability": 1.0,
  "recommended_strategy": "Step-by-step plan for what the response should cover, in order.",
  "evidence_required": ["Any clarifying context that would help answer more precisely, if any"],
  "escalation_path": [{escalation_json}],
  "summary": "One-paragraph plan rationale."
}}

Inputs:
Research summary:
{research_summary}

Evidence summary:
{evidence_summary}

Decide:
1. What should the response prioritize covering?
2. Are there any red-flag/urgent symptoms or concerns that must be flagged prominently?
3. What tone is appropriate (educational, reassuring, or urging prompt care)?
{feedback_block}
RETURN JSON ONLY. No markdown fences. Response Planning Agent output."""
        return _base(domain, task, case_summary, context)

    task = f"""You are the Strategy Agent. Decide the dispute path for this {profile.entity} vs {profile.counterparty} case, based on research and evidence.
Return JSON with exactly this schema:

{{
  "can_appeal": "YES",
  "success_probability": 0.72,
  "recommended_strategy": "Step-by-step numbered plan for the appeal/dispute",
  "evidence_required": ["Document 1 needed", "Document 2 needed"],
  "escalation_path": [{escalation_json}],
  "summary": "One-paragraph strategy rationale."
}}

Inputs:
Research summary:
{research_summary}

Evidence summary:
{evidence_summary}

Decide:
1. Can this be disputed/appealed? YES or NO
2. Success probability (0.0 to 1.0) with reason
3. Recommended strategy (numbered steps)
4. Evidence still required before filing
5. Escalation path if the {profile.counterparty} does not respond, in order: {' -> '.join(profile.escalation_path)}
{feedback_block}
RETURN JSON ONLY. No markdown fences. Strategy Agent output."""
    return _base(domain, task, case_summary, context)


def negotiation_prompt(domain: Domain, case_summary: str, context: str, strategy: str, evidence_summary: str) -> str:
    profile = get_profile(domain)

    if not profile.is_dispute:
        task = f"""You are the Response Drafting Agent. Produce a clear, accurate, well-organized informational answer.
Generate the following in ONE JSON response:

{{
  "appeal_letter": "The full informational answer in plain language, organized with clear sections. This is NOT a legal letter -- it is a direct answer to the reader's question, written for a general audience.",
  "complaint_email": "",
  "escalation_note": "",
  "consumer_complaint": "",
  "summary": "Brief description of what was generated."
}}

Response plan to follow:
{strategy}

Context to rely on:
{evidence_summary}

Always include a clear disclaimer that this is educational information, not a diagnosis, and to consult a licensed physician for personal medical advice. If any red-flag/urgent symptoms were identified in the plan, state them prominently and recommend seeking care promptly.

RETURN JSON ONLY. No markdown fences. Response Drafting Agent output."""
        return _base(domain, task, case_summary, context)

    escalation_path_str = " -> ".join(profile.escalation_path)
    task = f"""You are the Negotiation Agent. Draft professional outputs for human approval for this {profile.entity} vs {profile.counterparty} dispute.
Generate ALL of the following in ONE JSON response. These are four DIFFERENT documents for different
recipients and purposes -- each has a required FORMAT below that is deliberately different from the
others, specifically so you cannot write one letter and paste it into all four fields with only the
greeting changed. If you notice two fields ending up with nearly the same sentences, that is a sign
you have done this wrong -- rewrite the shorter/later one from scratch in its required format instead.

{{
  "appeal_letter": "Formal letter addressed TO {profile.counterparty}. Prose, 3-5 paragraphs: state the dispute, cite the specific clause/regulation/evidence, state what you want done, state the response deadline you expect. Subject line, salutation, body, closing.",
  "complaint_email": "A DIFFERENT, MUCH SHORTER document (under 100 words) addressed to {profile.counterparty}'s customer-support desk, not their legal/nodal channel. Plain conversational tone, NO clause citations, NO legal language. Just: what happened (one sentence), what you want (one sentence), a request to log a ticket/reference number. Do not reuse appeal_letter's sentences.",
  "escalation_note": "An INTERNAL memo, NOT addressed to {profile.counterparty} at all -- this is a note for the consumer's own record / next escalation contact, in this exact structured format with these labeled lines (not prose paragraphs): 'CASE: <one-line summary>' / 'PRIOR ATTEMPT: <when the appeal_letter/complaint_email above was or will be sent, and the response deadline given>' / 'IF NO RESPONSE BY DEADLINE: escalate via {escalation_path_str}' / 'NEXT ACTION: <specific next step, e.g. which regulator form to file>'.",
  "consumer_complaint": "A formal regulator complaint for {profile.regulator}, in STRUCTURED FIELD format (labeled fields, not flowing prose, and NOT a Python/JSON dict literal -- write each as its own plain text line like 'Name: [Your Name]') so it visually cannot be confused with the letter above: 'COMPLAINANT DETAILS:' then separate lines 'Name: <placeholder>', 'Address: <placeholder>', 'Contact Number: <placeholder>' / 'RESPONDENT: {profile.entity} name placeholder' / 'REFERENCE/ACCOUNT NUMBER: <placeholder>' / 'NATURE OF COMPLAINT: <one or two lines>' / 'CHRONOLOGY: <dated bullet list of what happened, from the evidence below>' / 'RELIEF SOUGHT: <specific ask>'.",
  "summary": "Brief description of what was generated."
}}

Strategy to follow:
{strategy}

Evidence to rely on:
{evidence_summary}

RETURN JSON ONLY. No markdown fences. Negotiation Agent output."""
    return _base(domain, task, case_summary, context)


def review_prompt(
    domain: Domain,
    case_summary: str,
    context: str,
    evidence_summary: str,
    strategy: str,
    appeal_draft: str,
) -> str:
    profile = get_profile(domain)
    task = f"""You are the Review Agent (devil's advocate). Audit the entire case before human approval.
Return JSON with exactly this schema:

{{
  "missing_evidence": ["List specific documents or facts still missing"],
  "hallucination_risks": ["Any claims made without evidence backing"],
  "wrong_clause_risks": ["Any clauses, rules, or regulations cited incorrectly or that may not apply"],
  "weak_arguments": ["Arguments the {profile.counterparty} could easily counter"],
  "approval_ready": false,
  "summary": "Overall audit verdict and what must be fixed before submission."
}}

Check:
- Missing evidence that weakens the case
- Hallucinated clauses, rules, or regulations not in the retrieved knowledge
- Wrong clause or regulation cited (verify against {profile.regulator} where applicable)
- Weak or unsupported arguments

Strategy reviewed:
{strategy}

Draft reviewed:
{appeal_draft[:6000]}

Evidence reviewed:
{evidence_summary[:4000]}

RETURN JSON ONLY. No markdown fences. Review Agent output."""
    return _base(domain, task, case_summary, context)


def final_report_prompt(domain: Domain, state: dict) -> str:
    profile = get_profile(domain)
    research_output = state.get("research_output", {})
    evidence_output = state.get("evidence_output", {})
    strategy_output = state.get("strategy_output", {})
    negotiation_output = state.get("negotiation_output", {})
    review_output = state.get("review_output", {})

    section_5 = "Response Drafted - Summary of the generated informational answer" if not profile.is_dispute else "Generated Documents - Summary of appeal letter, complaint, and escalation drafts"
    section_4 = "Response Plan - What the answer covers and its tone" if not profile.is_dispute else "Appeal Strategy - Recommended approach with probability"

    mismatch_notice = ""
    if evidence_output.get("evidence_relevant") is False:
        mismatch_notice = (
            "\n\nIMPORTANT: evidence_relevant is False -- the uploaded document does NOT match this case "
            "(see the evidence summary below for why). You MUST open the report with a clearly marked "
            "notice, before the Executive Summary, e.g. \"NOTE: The document you uploaded does not appear "
            "to relate to this case -- the analysis below is based only on your written description.\" "
            "Do not build any Key Facts from that document; state plainly that no usable evidence was extracted."
        )

    task = f"""Compile the Final Case Report. Do not write it like an internal case file addressed to
"the {profile.entity}" in the third person -- write it addressed directly to the person who filed this
case, in second person, by name if they mentioned one in the case summary below. This is the single
document they'll actually read, so it needs to read like a real answer from someone who understands their
situation, not a formal audit log.

Do not end any sentence with a question awaiting their reply (no "would you like...", no "let me know
if..."). State what's already been generated and what to do next directly, as fact -- not as something
offered pending their response.

Never write a URL, hyperlink, or "download here" reference for the generated documents themselves -- they
are not hosted anywhere and have no link; they appear directly in the Generated Documents section of this
same report. Only include a URL when it's a real one from the research findings below (e.g. an actual
regulator portal) -- never invent a plausible-looking link for anything else.

HARD RULE -- LANGUAGE: detect the language the case summary below is actually written in, and write this
entire report in that same language, start to finish -- section headings included. If it's written in
Tamil, the whole report is in Tamil; if Hindi, entirely in Hindi; and so on for any language. Do not drift
into English partway through even though the research/evidence/regulation findings you're citing were
established in English -- translate the substance, but keep proper nouns, regulation/act names, and
specific citations as they actually appear in the source material. Only write in English if the case
summary itself is in English.

HARD RULE -- DO NOT PARROT A CORRECTED COMPLAINT: the case summary below is the person's own initial framing,
written before any evidence was examined -- it can be imprecise about what actually happened (e.g. they call
it "charged twice" when the evidence findings below actually show unrelated unauthorized transactions).
Evidence findings reflect what the evidence actually shows. If the two disagree, the opening and Key Facts
must describe what the evidence actually shows, not the person's original guess -- never open by restating
their framing and then contradict it later in the same report. Silently correct it in your own words.

Sections, in this order:
1. A short, warm opening acknowledging their specific situation (1-2 sentences, not generic), describing
   what actually happened per the rule above.
2. Why this is happening - the underlying cause in plain terms (1-3 sentences), before any procedure. This
   is what separates a real answer from a checklist -- diagnose it, don't just restate the facts back to them.
3. Key Facts - the specific dates/amounts/references established from evidence.
4. Applicable Rules & Regulations - from research, cited specifically (not "relevant regulations").
5. {section_4}
6. {section_5}
7. What to double-check - fold any review-flagged uncertainty into ONE natural sentence here (e.g. "I'd
   confirm the exact clause number directly with them, but the underlying entitlement is clear") -- never a
   bracketed technical annotation like "(not confirmed word-for-word in retrieved sources)"; that is an
   internal QA note, not something the reader should ever see verbatim.
8. Next Steps - if there's a real deadline anywhere in the case summary, sequence these as an explicit
   schedule (Day 1: ..., Day 2-3: ...), not an unordered list. If there's no deadline, rank by leverage/speed.
9. Close with a concrete pointer to what's already been generated -- e.g. "the formal appeal letter is
   drafted in the Generated Documents section above, ready for you to review and send" -- do NOT phrase
   this as an open question like "would you like me to draft this?" if it's already been generated in
   section 6 above (it usually has been); only ask a genuine open question if something truly hasn't been
   drafted yet, and even then phrase it as a next step to take, not a yes/no awaiting a reply.

Research findings: {research_output.get('summary', state.get('research_summary', 'Not available'))}
Evidence findings: {evidence_output.get('summary', state.get('evidence_summary', 'Not available'))}
Strategy: {strategy_output.get('summary', state.get('strategy', 'Not available'))}
Documents generated: {negotiation_output.get('summary', 'Not available')}
Review flags: {review_output.get('summary', 'Not available')}
Review approval status: {'READY' if review_output.get('approval_ready') else 'NEEDS ATTENTION'}{mismatch_notice}

Cite only what prior agents established -- do not add new facts. Return the final case report as a plain
text document. Do NOT return JSON for this one — return formatted text with clear section headings."""
    return _base(
        domain,
        task,
        state.get("case_summary", ""),
        state.get("retrieved_context", ""),
        state.get("evidence_summary", ""),
    )
