"use strict";
const $ = (id) => document.getElementById(id);
let actor = localStorage.getItem("peoplepay-user") || crypto.randomUUID();
localStorage.setItem("peoplepay-user", actor);
let token = "", active = null, busy = false, journeys = [];
$("user").value = actor;
const pretty = (value) => JSON.stringify(value, null, 2);
const rupees = (minor) => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(minor / 100);
const score = (value) => Number.isFinite(value) ? value.toFixed(2) : "Unavailable";
const readable = (value) => value.replaceAll("_", " ").toLowerCase();
function node(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (className) element.className = className;
  return element;
}
function notice(text, error = false) {
  $("notice").hidden = !text;
  $("notice").textContent = text;
  $("notice").classList.toggle("error", error);
}
async function api(path, body) {
  const response = await fetch(path, { method: body === undefined ? "GET" : "POST",
    headers: { "Content-Type": "application/json", "X-Beacon-User": actor,
      ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
  let result;
  try { result = await response.json(); }
  catch (_) { throw new Error(`The gateway returned an unreadable response (${response.status}). Reload the saved journey before retrying.`); }
  if (!result || typeof result !== "object" || Array.isArray(result)) throw new Error("The gateway returned an invalid response. Reload the saved journey before retrying.");
  if (!response.ok) throw new Error(result.error || `Request failed (${response.status})`);
  return result;
}
async function run(task) {
  if (busy) return;
  busy = true; notice(""); sync();
  try { await task(); } catch (error) {
    try { await reload(); } catch (_) { /* Preserve the original error while offline. */ }
    notice(error.message, true);
  }
  finally { busy = false; sync(); }
}
function sync() {
  document.querySelectorAll("button").forEach((button) => { button.disabled = busy; });
  $("approve").disabled = busy || !$("approve-confirmation").checked || Boolean(active?.order);
  $("record-delivery").disabled = busy || Boolean(active?.order?.delivery_final) || !active?.order;
  $("explain").disabled = busy || !active?.decision;
  $("refresh-evidence").disabled = busy || !active;
}
function list() {
  $("journey-list").replaceChildren();
  if (!journeys.length) $("journey-list").append(node("p", "No journeys yet.", "hint empty-list"));
  for (const record of journeys) {
    const button = node("button", undefined, "journey-item");
    button.type = "button";
    button.classList.toggle("selected", record.id === active?.id);
    button.append(node("strong", `${record.requirement.quantity} ${record.requirement.product}`), node("small", readable(record.phase)));
    button.onclick = () => run(async () => { active = await api(`/api/v1/journeys/${record.id}`); render(); });
    $("journey-list").append(button);
  }
}
async function reload() {
  try { journeys = (await api("/api/v1/journeys")).journeys; }
  catch (error) { $("connection").textContent = "Account unavailable"; throw error; }
  $("connection").textContent = "Account connected";
  if (active) {
    active = await api(`/api/v1/journeys/${active.id}`);
    render();
  } else list();
}
function references(target, fields) {
  target.replaceChildren();
  for (const [label, value] of fields) target.append(node("dt", label), node("dd", value || "Pending"));
}
function render() {
  if (!active) { $("empty-state").hidden = false; $("active-journey").hidden = true; return; }
  const record = active, requirement = record.requirement, decision = record.decision;
  $("empty-state").hidden = true; $("active-journey").hidden = false;
  $("journey-title").textContent = `${requirement.quantity} ${requirement.product}`;
  $("journey-mode").textContent = record.mode === "reference" ? "REFERENCE LIFECYCLE · NO MONEY MOVED" : "CONNECTED SERVICE RESEARCH";
  $("phase").textContent = readable(record.phase);
  $("requirement-metrics").replaceChildren();
  for (const [label, value] of [["Budget", rupees(requirement.budget_minor)], ["Delivery limit", `${requirement.delivery_days} days`], ["Priority", requirement.prioritize_sustainability ? "Sustainability" : "Price"]]) {
    const metric = node("div"); metric.append(node("small", label), node("strong", value)); $("requirement-metrics").append(metric);
  }
  $("journey-boundary").textContent = record.mode === "reference" ? "Fictitious suppliers and captured native scoring outputs. Merchant and PROXY are reference simulators unless an actor's native PROXY session is explicitly configured." : "Native provider research retains its coverage and verification gaps. This journey cannot authorize a live merchant order.";
  $("progress-chain").replaceChildren();
  for (const [index, label, done] of [[1, "Requirement", true], [2, "Providers", Boolean(decision)], [3, "ECHO", Boolean(decision)], [4, "Approval", Boolean(record.approval)], [5, "Merchant", Boolean(record.order)], [6, "PROXY", Boolean(record.dispute)]]) {
    const step = node("li", undefined, done ? "done" : ""); step.append(node("span", done ? "✓" : index), node("strong", label)); $("progress-chain").append(step);
  }
  $("providers").replaceChildren();
  for (const receipt of decision?.provider_receipts || []) {
    const card = node("article", undefined, "provider-card");
    card.append(node("strong", receipt.extension_id === "greenchain" ? "GreenChain" : "InflationForge"));
    const unsupported = receipt.warnings.some((warning) => warning.includes("NOT_TRACKED"));
    card.append(node("span", unsupported ? "Product not tracked" : `${receipt.entities.length} supplier observations`, unsupported ? "pill warning" : "pill"));
    card.append(node("p", unsupported ? "The native catalog does not cover these chairs. No INR chair price was invented." : "Supplier estimates and raw model scores retained with evidence references."));
    card.append(node("small", `SDK ${receipt.schema_version} · ${receipt.status} · ${receipt.evidence.length} evidence records`));
    $("providers").append(card);
  }
  $("evidence-json").textContent = pretty({ normalized_results: decision?.normalized_results || [], reconciliation: decision?.reconciliation || [], ingestion: decision?.ingestion || [] });
  $("evidence-summary").textContent = "Exact source identifiers reconcile aliases. Display-name similarity alone never establishes supplier identity. Reference evidence remains unverified.";
  $("supplier-table").replaceChildren(); $("supplier-options").replaceChildren(node("legend", "Choose an eligible supplier"));
  $("policy-outcome").textContent = decision ? readable(decision.policy_outcome) : "Awaiting evidence";
  $("decision-caption").textContent = decision ? `Version ${decision.decision_version} · evaluated ${new Date(decision.evaluated_at).toLocaleString()} · fixed ECHO sustainability and price policy` : (record.last_error || "No decision yet. Retry evidence collection with refresh.");
  for (const candidate of decision?.candidates || []) {
    const row = node("tr", undefined, candidate.supplier_id === decision.recommended_supplier_id ? "recommended" : "");
    const name = node("td"); name.append(node("strong", candidate.supplier_name), node("small", candidate.supplier_id === decision.recommended_supplier_id ? "Recommended" : "Alternative"));
    row.append(name, node("td", score(candidate.raw_provider_score)), node("td", score(candidate.echo_score)), node("td", rupees(candidate.terms.total_minor)), node("td", `${candidate.terms.delivery_days} days`), node("td", candidate.eligible ? "Eligible for reference" : candidate.policy_violations.map(readable).join(", ")));
    $("supplier-table").append(row);
    if (candidate.eligible) {
      const label = node("label", undefined, "supplier-choice"); const input = node("input"); input.type = "radio"; input.name = "supplier_id"; input.value = candidate.supplier_id;
      input.checked = candidate.supplier_id === decision.recommended_supplier_id;
      label.append(input, node("span", candidate.supplier_name), node("small", `${rupees(candidate.terms.total_minor)} · ${candidate.terms.delivery_days} days`)); $("supplier-options").append(label);
    }
  }
  $("decision-warnings").replaceChildren(...(decision?.warnings || []).map((warning) => node("li", warning)));
  $("warning-count").textContent = `Decision warnings (${decision?.warnings.length || 0})`;
  $("approval-form").hidden = !decision?.recommended_supplier_id || Boolean(record.order) || record.mode !== "reference";
  $("approve-confirmation").checked = false;
  $("decision-binding").textContent = decision ? `Version ${decision.decision_version} · ${decision.decision_hash}` : "";
  $("approval-receipt").hidden = !record.approval;
  $("approval-receipt").replaceChildren();
  if (record.approval) $("approval-receipt").append(node("strong", `Approved ${record.approval.terms.supplier_id} · ${rupees(record.approval.terms.total_minor)}`), node("span", `Historical version ${record.approval.decision_version} · Terms ${record.approval.terms_hash}`));
  $("commerce-empty").hidden = Boolean(record.checkout); $("commerce-details").hidden = !record.checkout;
  references($("commerce-references"), [["Gateway transaction", record.transaction_id], ["Checkout session", record.checkout?.checkout_session_id], ["Merchant order", record.order?.external_order_ref], ["Merchant state", record.order?.status || record.checkout?.status], ["Payment", "Reference simulator · no money moved"]]);
  $("delivery-form").hidden = !record.order || Boolean(record.order.delivery_final);
  $("delivered").max = requirement.quantity; $("delivery-unit").textContent = `of ${requirement.quantity} units`;
  $("delivery-result").hidden = !record.delivery_event;
  if (record.delivery_event) $("delivery-result").textContent = `${record.order.delivered_quantity}/${record.order.ordered_quantity} units delivered. ${record.order.ordered_quantity - record.order.delivered_quantity} missing. Event ${record.delivery_event.event_id}.`;
  $("dispute-empty").hidden = Boolean(record.dispute) || Boolean(record.dispute_bundle);
  $("dispute-details").hidden = !record.dispute && !record.dispute_bundle;
  $("dispute-details").querySelector(".draft-status strong").textContent = record.dispute ? "Draft ready for review" : "Evidence retained · draft pending";
  document.getElementById("retry-dispute")?.remove();
  if (!record.dispute && record.dispute_bundle) {
    $("draft-mode").textContent = record.proxy_requires_reconciliation || record.proxy_handoff_started
      ? "A native case may exist. Operator reconciliation is required before another handoff."
      : "No external case handoff started. Fix any configuration problem and retry the preserved draft.";
    $("draft-text").textContent = record.last_error || "The complete evidence is preserved below.";
    $("bundle-json").textContent = pretty(record.dispute_bundle);
    $("bundle-links").replaceChildren(node("code", record.dispute_bundle.bundle_hash, "hash"));
    if (!record.proxy_requires_reconciliation && !record.proxy_handoff_started) {
      const retry = node("button", "Retry preserved dispute draft", "secondary");
      retry.id = "retry-dispute"; retry.type = "button";
      retry.onclick = () => run(async () => { active = await api(`/api/v1/journeys/${active.id}/retry-dispute`, {}); await reload(); render(); });
      $("draft-mode").after(retry);
    }
  }
  if (record.dispute) {
    $("draft-mode").textContent = `${record.dispute.mode} · ${record.dispute.provider || "Native PROXY"} · requires human review`;
    $("draft-text").textContent = record.dispute.draft_text || pretty(record.dispute);
    $("bundle-json").textContent = pretty(record.dispute.bundle || record.dispute_bundle);
    $("bundle-links").replaceChildren(...["Requirement", "Supplier", "Decision & evidence", "Approved terms", "Transaction", "Merchant order", "Delivery event"].map((label) => node("span", label)));
    $("bundle-links").append(node("code", record.dispute.bundle_hash, "hash"));
  }
  notice(record.last_error || "", Boolean(record.last_error));
  $("historical-explanation").hidden = true;
  showChanges(); list(); sync();
}
function showChanges() {
  const data = active?.changes;
  $("changes").hidden = !data;
  $("changes").replaceChildren();
  if (!data) return;
  $("changes").append(node("h3", "Current information compared with the preserved decision"), node("p", `Historical: ${new Date(data.historical_evaluated_at).toLocaleString()} · Current: ${new Date(data.current_evaluated_at).toLocaleString()}`));
  const changes = node("ul");
  for (const change of data.changes) {
    let text = `${change.supplier_id || change.extension_id}: ${readable(change.field)} changed`;
    if (change.field === "terms") text += ` from ${rupees(change.at_decision.total_minor)} to ${rupees(change.current.total_minor)}`;
    changes.append(node("li", text));
  }
  $("changes").append(data.changes.length ? changes : node("p", "No observed supplier, merchant term, or evidence changes. Reference captures are fixed; their original observation times remain preserved."));
  $("changes").append(node("p", "The approved terms and historical evidence snapshot have been preserved."));
}
$("requirement-form").onsubmit = (event) => { event.preventDefault(); run(async () => {
  const amount = $("budget").value;
  if (!/^\d{1,10}(\.\d{1,2})?$/.test(amount)) throw Error("Enter an INR amount with at most two decimal places");
  const [whole, fraction = ""] = amount.split(".");
  active = await api("/api/v1/journeys", { mode: $("mode").value, requirement: {
    description: $("description").value, product: $("product").value, quantity: Number($("quantity").value),
    budget_minor: Number(whole) * 100 + Number(fraction.padEnd(2, "0")), currency: "INR", delivery_days: Number($("delivery-days").value),
    destination: "IN", prioritize_sustainability: $("sustainability").checked } });
  await reload(); render();
}); };
$("approve-confirmation").onchange = sync;
$("approval-form").onsubmit = (event) => { event.preventDefault(); run(async () => {
  const supplier = $("supplier-options").querySelector("input:checked");
  if (!supplier || !$("approve-confirmation").checked) throw Error("Choose a supplier and confirm the reference terms");
  active = await api(`/api/v1/journeys/${active.id}/approve`, { decision_hash: active.decision.decision_hash,
    decision_version: active.decision.decision_version, supplier_id: supplier.value, human_confirmation: true, confirm_reference: true });
  await reload(); render();
}); };
$("delivery-form").onsubmit = (event) => { event.preventDefault(); run(async () => {
  active = await api(`/api/v1/journeys/${active.id}/delivery`, { event_id: crypto.randomUUID(), delivered_quantity: Number($("delivered").value) });
  await reload(); render();
}); };
$("explain").onclick = () => run(async () => {
  const explanation = await api(`/api/v1/journeys/${active.id}/explain`);
  $("historical-explanation").replaceChildren(node("h3", `Preserved decision · version ${explanation.decision_version}`), node("p", new Date(explanation.evaluated_at).toLocaleString()), node("p", explanation.explanation), node("p", explanation.candidate ? `${explanation.candidate.supplier_name}: ${rupees(explanation.candidate.terms.total_minor)}, ${explanation.candidate.terms.delivery_days} days. ECHO score ${score(explanation.candidate.echo_score)}.` : "No supplier recommendation."), node("code", explanation.decision_hash, "hash"));
  $("historical-explanation").hidden = false;
});
$("refresh-evidence").onclick = () => run(async () => { active = await api(`/api/v1/journeys/${active.id}/refresh`, {}); await reload(); render(); });
$("reload").onclick = () => run(reload);
$("account-form").onsubmit = (event) => { event.preventDefault(); run(async () => {
  actor = $("user").value.trim(); token = $("token").value.trim(); localStorage.setItem("peoplepay-user", actor);
  active = null; render(); await reload();
}); };
$("mode").onchange = () => { $("mode-help").textContent = $("mode").value === "reference" ? "Fictitious suppliers, captured provider outputs and a merchant simulator. No payment is made." : "Calls configured native services. Missing coverage stays missing. Live orders cannot be authorized in this version."; };
run(reload);
