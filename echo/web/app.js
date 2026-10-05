"use strict";
const $ = (id) => document.getElementById(id);
const safe = (value) => (value == null ? "—" : String(value));
function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

function renderCandidates(result) {
  const tbody = $("candidate-rows");
  tbody.replaceChildren();
  const recommended = result.recommended_supplier_id;
  for (const candidate of result.candidates) {
    const row = node("tr", candidate.supplier_id === recommended ? "recommended" : "");
    const values = [
      node("strong", "", candidate.supplier_name),
      node("span", "score", candidate.raw_score.toFixed(1)),
      node("span", "score up", candidate.robust_score.toFixed(1)),
      node("span", "", `${candidate.apparent_support_count} observations`),
      node("span", "", `${candidate.provenance_root_count} roots`),
      node("span", "", candidate.supplier_id === recommended ? "RECOMMENDED" : candidate.decision_status),
    ];
    for (const value of values) {
      const cell = node("td");
      cell.append(value);
      row.append(cell);
    }
    tbody.append(row);
  }
}

function renderLineage(candidates) {
  const root = $("lineage");
  root.replaceChildren();
  for (const candidate of candidates) {
    const card = node("article", "lineage-card");
    card.append(node("h3", "", candidate.supplier_name));
    const stats = node("div", "lineage-stat");
    for (const [label, value] of [
      ["Evidence", candidate.apparent_support_count],
      ["Provenance roots", candidate.provenance_root_count],
      ["Correlated observations", candidate.correlated_observation_count],
      ["Correlation penalty", candidate.correlation_penalty.toFixed(1)],
    ]) {
      const item = node("span");
      item.append(node("b", "", safe(value)), document.createTextNode(` ${label}`));
      stats.append(item);
    }
    card.append(stats);
    const uniquePaths = new Map();
    for (const path of candidate.evidence_paths) {
      const key = `${path.source_id} → ${path.root_source_id}`;
      uniquePaths.set(key, (uniquePaths.get(key) || 0) + 1);
    }
    const list = node("ul", "path-list");
    for (const [path, count] of uniquePaths) {
      list.append(node("li", "", `${path} (${count} evidence item${count === 1 ? "" : "s"})`));
    }
    card.append(list);
    root.append(card);
  }
}

function render(result) {
  const rawName = result.candidates.find((c) => c.supplier_id === result.raw_winner_supplier_id)?.supplier_name;
  const winnerName = result.candidates.find((c) => c.supplier_id === result.recommended_supplier_id)?.supplier_name;
  $("decision-title").textContent = result.recommended_supplier_id
    ? `${rawName || result.raw_winner_supplier_id} → ${winnerName || result.recommended_supplier_id}`
    : result.decision_status;
  $("decision-reason").textContent = `${result.reason} ${result.graph_reason}`;
  $("fragility-value").textContent = result.decision_fragility;
  $("flip-count").textContent = `${result.winner_flip_count} winner flips in root-removal counterfactuals`;
  renderCandidates(result);
  renderLineage(result.candidates);
  $("policy-data").textContent = JSON.stringify(result.scoring_policy, null, 2);
  const panel = $("counterfactuals");
  panel.replaceChildren();
  for (const scenario of result.counterfactual_root_removals) {
    panel.append(node("div", "counterfactual",
      `Remove ${scenario.removed_root_source_id}: ${scenario.winner_supplier_id || "ABSTAIN"} ` +
      `(${scenario.winner_robust_score ?? "no eligible score"})`));
  }
  $("result").hidden = false;
  $("error").hidden = true;
}

$("run-demo").addEventListener("click", async () => {
  const button = $("run-demo");
  button.disabled = true;
  button.textContent = "Tracing evidence dependencies…";
  $("error").hidden = true;
  try {
    const response = await fetch("/echo/demo/run", { method: "POST" });
    const body = await response.json();
    if (!response.ok) throw Error(body.detail || `HTTP ${response.status}`);
    render(body);
  } catch (error) {
    $("error").textContent = error.message;
    $("error").hidden = false;
  } finally {
    button.disabled = false;
    button.textContent = "Run the false-consensus demo";
  }
});

function extensionHeaders(admin = false) {
  const fields = $("extension-identity").elements;
  return {"Content-Type": "application/json", "X-Beacon-User": fields.user.value,
    ...(fields.bearer.value ? {Authorization: `Bearer ${fields.bearer.value}`} : {}),
    ...(admin && fields.admin.value ? {"X-Echo-Admin-Token": fields.admin.value} : {})};
}

async function extensionApi(path, body, admin = false) {
  const response = await fetch(path, {method: body === undefined ? "GET" : "POST",
    headers: extensionHeaders(admin), ...(body === undefined ? {} : {body: JSON.stringify(body)})});
  const data = await response.json();
  if (!response.ok) throw Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail));
  return data;
}

async function loadExtensions() {
  const notice = $("extension-notice");
  notice.textContent = "Loading configured providers...";
  try {
    const {extensions} = await extensionApi("/echo/v1/extensions");
    const cards = $("extension-cards");
    cards.replaceChildren();
    for (const extension of extensions) {
      const card = node("article", "lineage-card");
      card.append(node("h3", "", extension.name),
        node("p", "", `v${extension.version} · ${extension.license.spdx} · ${extension.runtime_mode}`),
        node("p", "", extension.capabilities.join(", ")),
        node("p", "", `Status: ${extension.status} · Health: ${extension.health.status}`),
        node("p", "", extension.upstream.repository || "First-party synthetic provider"));
      const toggle = node("button", "", extension.enabled ? "Disable" : "Enable");
      toggle.disabled = !extension.adapter_available;
      toggle.addEventListener("click", async () => {
        toggle.disabled = true;
        try {
          await extensionApi(`/echo/v1/extensions/${extension.id}/enabled`, {enabled: !extension.enabled}, true);
          $("extension-notice").textContent = "Provider selection updated for this server process.";
          await loadExtensions();
        } catch (error) {
          $("extension-notice").textContent = error.message;
          toggle.disabled = false;
        }
      });
      card.append(toggle);
      cards.append(card);
    }
    const enabled = extensions.filter((extension) => extension.enabled).length;
    notice.textContent = `${extensions.length} configured providers · ${enabled} enabled`;
  } catch (error) { notice.textContent = error.message; }
}

$("extension-identity").addEventListener("submit", (event) => { event.preventDefault(); loadExtensions(); });
$("price-extension").addEventListener("submit", async (event) => {
  event.preventDefault();
  const fields = event.currentTarget.elements;
  try {
    const data = await extensionApi("/echo/v1/extensions/execute?extension_id=inflationforge", {
      schema_version: "1", request_id: crypto.randomUUID(), capability: "price_intelligence",
      context: {requirement_id: fields.requirement.value, user_id: $("extension-identity").elements.user.value},
      input: {snapshot_id: fields.snapshot.value, item_id: fields.item.value, city_id: fields.city.value},
    });
    $("extension-execution").textContent = JSON.stringify(data, null, 2);
  } catch (error) { $("extension-execution").textContent = error.message; }
});

$("run-extensions-demo").addEventListener("click", async () => {
  const button = $("run-extensions-demo");
  button.disabled = true;
  try {
    render(await extensionApi("/echo/demo/extensions/run", {}));
  } catch (error) { $("error").textContent = error.message; $("error").hidden = false; }
  finally { button.disabled = false; }
});
loadExtensions();

fetch("/health").then((response) => response.json()).then((data) => {
  $("health").textContent = data.graph ? "FalkorDB connected" : "FalkorDB unavailable";
}).catch(() => { $("health").textContent = "FalkorDB unavailable"; });
