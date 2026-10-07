"use strict";
(function () {
  const $ = (id) => document.getElementById(id);
  const { node, api } = PP;
  let providers = [], vault = {}, prefs = {}, catalog = { models: [] }, deployment = "self_hosted";
  const say = (t, bad) => { const n = $("notice"); n.hidden = !t; n.textContent = t || ""; n.classList.toggle("error", !!bad); };
  const fail = (e) => say(e.detail && e.detail.message ? `${e.detail.message}${e.detail.detail ? " — " + e.detail.detail : ""}` : e.message, true);
  const act = async (fn) => { try { await fn(); } catch (e) { fail(e); } };
  const keyOf = (m) => `${m.connection_id}::${m.provider_model_id}`;
  const stClass = (s) => ({ "Connected": "st-connected", "Degraded": "st-warn", "Rate limited": "st-warn", "Invalid credentials": "st-bad", "Unavailable": "st-bad", "Disabled": "st-off" }[s] || "st-off");
  const ago = (s) => (s == null ? "never" : s < 90 ? "just now" : s < 5400 ? `${Math.round(s / 60)} min ago` : s < 129600 ? `${Math.round(s / 3600)} h ago` : `${Math.round(s / 86400)} d ago`);
  const when = (t) => (t ? new Date(t * 1000).toLocaleString() : "never");

  async function loadAll() {
    const [p, pr, cat] = await Promise.all([api("/api/v1/models/providers"), api("/api/v1/models/preferences"), api("/api/v1/models/catalog?all=1&kind=")]);
    providers = p.providers; vault = p.vault; deployment = p.deployment; prefs = pr.preferences || {}; catalog = cat;
    $("vault-note").textContent = vault.note || "";
    renderGeneral(); renderProviderForm(); await renderConnections(); renderModels(); renderFallbacks(); renderLocal(); renderPrivacy(); await renderUsage(); renderCompare();
  }

  // ---------------------------------------------------------------- general
  function renderGeneral() {
    const sel = $("default-model"); sel.replaceChildren(node("option", "Auto (recommended)", undefined, { value: "" }));
    for (const m of catalog.models.filter((x) => x.selectable_as_chat)) sel.append(node("option", `${m.display_name} — ${m.route}`, undefined, { value: keyOf(m) }));
    sel.value = prefs.default_model || "";
    $("policy").value = prefs.routing_policy || "BALANCED";
    const box = $("presets"); box.replaceChildren();
    for (const [id, t] of [["private_work", "Private work"], ["fast_chat", "Fast chat"], ["deep_research", "Deep research"], ["low_cost", "Low cost"], ["local_coding", "Local coding"]]) {
      const b = node("button", t, "secondary", { type: "button", "aria-pressed": String(prefs.preset === id) });
      b.addEventListener("click", () => act(async () => { prefs = (await api("/api/v1/models/preferences/preset", { name: id })).preferences; say(`Preset "${t}" applied.`); renderGeneral(); renderLocal(); renderFallbacks(); }));
      box.append(b);
    }
  }
  $("default-model").addEventListener("change", () => act(async () => { prefs = (await api("/api/v1/models/preferences", { default_model: $("default-model").value })).preferences; say("Default model saved."); }));
  $("policy").addEventListener("change", () => act(async () => {
    const was = prefs.routing_policy, now = $("policy").value, patch = { routing_policy: now };
    if (now === "LOCAL_ONLY") patch.local_only = true; else if (was === "LOCAL_ONLY") patch.local_only = false;
    prefs = (await api("/api/v1/models/preferences", patch)).preferences; say("Routing preference saved."); renderLocal();
  }));
  $("export").addEventListener("click", () => act(async () => {
    const blob = new Blob([JSON.stringify(await api("/api/v1/models/preferences/export"), null, 2)], { type: "application/json" });
    const a = node("a", "", undefined, { href: URL.createObjectURL(blob), download: "peoplepay-model-preferences.json" }); a.click(); URL.revokeObjectURL(a.href);
  }));
  $("import-file").addEventListener("change", () => act(async () => {
    const f = $("import-file").files[0]; if (!f) return;
    prefs = (await api("/api/v1/models/preferences/import", JSON.parse(await f.text()))).preferences; say("Preferences imported."); renderGeneral();
  }));

  // ---------------------------------------------------------------- providers / BYOK
  function renderProviderForm() {
    const sel = $("ptype"); const prev = sel.value; sel.replaceChildren();
    for (const p of providers) sel.append(node("option", `${p.display_name}${p.experimental ? " (experimental)" : ""}${p.kind === "decision" ? " — typed decisions" : ""}`, undefined, { value: p.id }));
    if (prev) sel.value = prev;
    drawFields();
  }
  function drawFields() {
    const p = providers.find((x) => x.id === $("ptype").value); if (!p) return;
    const box = $("pfields"); box.replaceChildren();
    for (const f of p.fields) {
      const id = `pf-${f.name}`;
      box.append(node("label", f.label + (f.required ? "" : " (optional)"), undefined, { for: id }));
      let inp;
      if (f.options) { inp = node("select", undefined, undefined, { id, name: f.name }); for (const o of f.options) inp.append(node("option", o, undefined, { value: o })); if (f.default) inp.value = f.default; }
      else { inp = node("input", undefined, undefined, { id, name: f.name, type: f.secret ? "password" : "text", autocomplete: f.secret ? "new-password" : "off", spellcheck: "false" }); if (f.default) inp.placeholder = f.default; }
      box.append(inp); if (f.help) box.append(node("p", f.help, "hint"));
    }
    if (p.id === "openai_compatible") {
      box.append(node("label", "Custom headers as JSON (advanced)", undefined, { for: "pf-headers" }), node("textarea", undefined, undefined, { id: "pf-headers", rows: "2", placeholder: '{"X-Org": "team-a"}' }));
      box.append(node("label", "Capability overrides as JSON (advanced — wrong values can break requests)", undefined, { for: "pf-caps" }), node("textarea", undefined, undefined, { id: "pf-caps", rows: "2", placeholder: '{"tools": true, "vision": false}' }));
    }
    let n = p.notice || "";
    if (p.id === "ollama" && deployment === "cloud") n += " This PeoplePay is cloud-hosted: its server cannot reach localhost on your computer. Use a reachable endpoint you operate or a self-hosted PeoplePay.";
    $("pnotice").textContent = n || "Requests are processed by the provider under their terms.";
    $("pname").placeholder = p.display_name;
  }
  $("ptype").addEventListener("change", drawFields);
  $("add-form").addEventListener("submit", (e) => { e.preventDefault(); act(async () => {
    const p = providers.find((x) => x.id === $("ptype").value), values = {};
    for (const f of p.fields) { const el = $(`pf-${f.name}`); if (el && el.value.trim() !== "") values[f.name] = el.value.trim(); }
    for (const [id, k] of [["pf-headers", "headers"], ["pf-caps", "capability_overrides"]]) { const el = $(id); if (el && el.value.trim()) { try { values[k] = JSON.parse(el.value); } catch (_) { throw new Error(`${k} must be valid JSON`); } } }
    const out = await api("/api/v1/models/connections", { provider_type: p.id, display_name: $("pname").value || p.display_name, values });
    for (const el of $("add-form").querySelectorAll("input[type=password]")) el.value = "";   // secrets never linger in the page
    const t = out.test || {};
    say(t.ok ? `Connected${t.models_found != null ? ` — ${t.models_found} models found` : ""}${t.latency_ms ? ` (${Math.round(t.latency_ms)} ms)` : ""}.` : `Saved, but the test failed: ${(t.error && t.error.message) || t.detail || t.state}`, !t.ok);
    await loadAll();
  }); });
  async function renderConnections() {
    const { connections } = await api("/api/v1/models/connections");
    const box = $("conn-cards"); box.replaceChildren();
    if (!connections.length) box.append(node("p", "No providers connected. Connect one below, or configure provider variables on the server.", "pp-empty"));
    for (const c of connections) {
      const card = node("article", undefined, "pp-card"), conn = c.connection;
      card.append(node("h3", conn.alias || conn.display_name), node("span", c.status, `pill ${stClass(c.status)}`));
      if (c.provider.verification !== "live") card.append(node("span", ` ${c.provider.verification}-verified`, "pill warn", { title: "This integration is verified against recorded/mock traffic in this repository, not a live account." }));
      const dl = node("dl");
      for (const [k, v] of [["Provider", `${c.provider.name} (${c.provider.type.toLowerCase().replace("_", " ")})`], ["Scope", conn.system ? "Platform (environment)" : conn.owner_scope.startsWith("org") ? "Organization" : "Personal"], ["Models found", String(c.models_found)], ["Last validated", when(conn.last_validated_at)], ["Catalog refreshed", ago(c.catalog_age_s)], ["Latency", c.health.latency_ms ? `${Math.round(c.health.latency_ms)} ms` : "unknown"]]) dl.append(node("dt", k), node("dd", v));
      if (c.health.cooldown_remaining_s > 0) dl.append(node("dt", "Cooling down"), node("dd", `${Math.round(c.health.cooldown_remaining_s)} s`));
      if (c.catalog_error) dl.append(node("dt", "Last refresh"), node("dd", `failed (${c.catalog_error})`));
      card.append(dl);
      const row = node("div", undefined, "pp-row");
      const add = (t, fn, cls = "secondary") => { const b = node("button", t, cls, { type: "button", "aria-label": `${t} ${conn.display_name}` }); b.addEventListener("click", () => act(fn)); row.append(b); };
      add("Test", async () => { const t = await api(`/api/v1/models/connections/${conn.id}/test`, {}); say(t.ok ? `Connection OK (${Math.round(t.latency_ms || 0)} ms), ${t.models_found ?? "?"} models.` : `Test failed: ${(t.error && t.error.message) || t.detail || t.state}`, !t.ok); await loadAll(); });
      add("Refresh models", async () => { const r = await api(`/api/v1/models/connections/${conn.id}/refresh`, {}); say(`${r.count} models found.`); await loadAll(); });
      if (!conn.system) {
        add(conn.enabled ? "Disable" : "Enable", async () => { await api(`/api/v1/models/connections/${conn.id}/update`, { enabled: !conn.enabled }); await loadAll(); });
        add("Remove", async () => { if (confirm(`Remove ${conn.display_name}? Past messages keep their model and provider record.`)) { await api(`/api/v1/models/connections/${conn.id}/remove`, {}); await loadAll(); } });
      }
      card.append(row); box.append(card);
    }
  }

  // ---------------------------------------------------------------- models
  function renderModels() {
    const q = $("mq").value.toLowerCase(), body = $("model-rows"); body.replaceChildren();
    const rows = catalog.models.filter((m) => !q || `${m.display_name} ${m.provider_model_id} ${m.provider_id} ${m.route}`.toLowerCase().includes(q));
    if (!rows.length) { const tr = node("tr"), td = node("td", "No models yet. Connect a provider and test it to discover models.", undefined, { colspan: "6" }); tr.append(td); body.append(tr); }
    for (const m of rows.slice(0, 300)) {
      const tr = node("tr"), c1 = node("td"), c2 = node("td"), c3 = node("td"), c4 = node("td"), c5 = node("td"), c6 = node("td");
      c1.append(node("strong", m.display_name), node("small", m.selectable_as_chat ? m.provider_model_id : `${m.provider_model_id} · typed decisions only, not a chat model`));
      c2.append(document.createTextNode(m.route), node("small", m.connection_name));
      c3.append(PP.badges(m));
      c4.append(node("span", m.availability === "available" ? (m.health || "").toLowerCase() || "ok" : m.availability));
      if (m.selectable_as_chat) {
        const s = node("select", undefined, undefined, { "aria-label": `Tier for ${m.display_name}` });
        for (const [v, t] of [["", `Auto (${m.tier})`], ["fast", "Fast"], ["balanced", "Balanced"], ["deep", "Deep"]]) s.append(node("option", t, undefined, { value: v }));
        s.value = (prefs.model_tiers || {})[keyOf(m)] || "";
        s.addEventListener("change", () => act(async () => { const t = { ...(prefs.model_tiers || {}) }; s.value ? (t[keyOf(m)] = s.value) : delete t[keyOf(m)]; prefs = (await api("/api/v1/models/preferences", { model_tiers: t })).preferences; }));
        c5.append(s);
        const d = node("details"); d.append(node("summary", "Test", undefined, { "aria-label": `Capability tests for ${m.display_name}` }));
        for (const [cap, t] of [["vision", "Vision"], ["tools", "Tools"], ["structured_output", "Structured"]]) {
          const b = node("button", t, "secondary", { type: "button" });
          b.addEventListener("click", () => act(async () => { b.disabled = true; const r = await api("/api/v1/models/capability-test", { connection_id: m.connection_id, model_id: m.provider_model_id, capability: cap }); say(r.ok ? `${t} confirmed by test.` : `${t} test did not pass${r.error ? ": " + r.error.message : ""}.`, !r.ok); b.disabled = false; await loadAll(); }));
          d.append(b);
        }
        c6.append(d);
      }
      tr.append(c1, c2, c3, c4, c5, c6); body.append(tr);
    }
  }
  $("mq").addEventListener("input", renderModels);
  $("refresh-all").addEventListener("click", () => act(async () => { await api("/api/v1/models/refresh-stale", {}); say("Stale catalogs refreshed."); await loadAll(); }));

  // ---------------------------------------------------------------- routing
  $("ctx").addEventListener("change", () => act(async () => { prefs = (await api("/api/v1/models/preferences", { context_strategy: $("ctx").value })).preferences; say("Saved."); }));
  $("why-go").addEventListener("click", () => act(async () => {
    const body = { text: $("why-text").value, data_class: "INTERNAL" };
    if ($("why-img").checked) body.attachments = [{ kind: "image", media_type: "image/png", data_b64: "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==" }];
    const r = await api("/api/v1/models/explain", body), out = $("why-out"); out.hidden = false; out.replaceChildren();
    out.append(node("strong", r.selected ? `Selected: ${r.selected}` : "No route available"), node("div", `Requires: ${r.requirements.join(", ")} · policy ${r.policy}${r.local_only ? " · local only" : ""} · ~${r.est_tokens} tokens (estimate)`));
    const ul = node("ul"); for (const l of r.explanation) ul.append(node("li", l)); for (const e of r.excluded.slice(0, 10)) ul.append(node("li", `Excluded ${e.model}: ${e.reason}`)); out.append(ul);
  }));

  // ---------------------------------------------------------------- fallbacks
  function renderFallbacks() {
    for (const r of document.querySelectorAll("input[name=fb]")) { r.checked = r.value === (prefs.fallback_mode || "AUTOMATIC"); }
    const list = $("fb-list"); list.replaceChildren();
    const order = prefs.preferred_routes || [];
    const byKey = new Map(catalog.models.map((m) => [keyOf(m), m]));
    order.forEach((k, i) => {
      const m = byKey.get(k), li = node("li");
      const span = node("span"); span.append(node("strong", m ? m.display_name : k), document.createTextNode(m ? ` · ${m.route}` : " · (no longer available)"));
      if (m) {
        span.append(PP.badges(m));
        const cloud = !m.local && m.privacy !== "organization";
        if ((prefs.local_only || prefs.routing_policy === "LOCAL_ONLY") && !m.local) span.append(node("div", "⚠ Violates Local only — it will be skipped.", "badge bad"));
        else if (cloud && prefs.routing_policy === "PRIVACY_FIRST") span.append(node("div", "⚠ Cloud route; Privacy first ranks it last.", "badge warn"));
      }
      li.append(span);
      const mv = (d) => act(async () => { const o = [...order]; const j = i + d; if (j < 0 || j >= o.length) return; [o[i], o[j]] = [o[j], o[i]]; prefs = (await api("/api/v1/models/preferences", { preferred_routes: o })).preferences; renderFallbacks(); });
      for (const [t, d, lab] of [["↑", -1, "Move up"], ["↓", 1, "Move down"]]) { const b = node("button", t, "secondary", { type: "button", "aria-label": `${lab}: ${m ? m.display_name : k}` }); b.addEventListener("click", () => mv(d)); li.append(b); }
      const rm = node("button", "✕", "secondary", { type: "button", "aria-label": `Remove from order: ${m ? m.display_name : k}` });
      rm.addEventListener("click", () => act(async () => { prefs = (await api("/api/v1/models/preferences", { preferred_routes: order.filter((x) => x !== k) })).preferences; renderFallbacks(); }));
      li.append(rm); list.append(li);
    });
    if (!order.length) list.append(node("li", "No preferred order set — PeoplePay uses its routing preference.", "pp-muted"));
    const add = $("fb-add"); add.replaceChildren();
    for (const m of catalog.models.filter((x) => x.selectable_as_chat && !order.includes(keyOf(x)))) add.append(node("option", `${m.display_name} — ${m.route}`, undefined, { value: keyOf(m) }));
  }
  for (const r of document.querySelectorAll("input[name=fb]")) r.addEventListener("change", () => act(async () => { prefs = (await api("/api/v1/models/preferences", { fallback_mode: r.value })).preferences; say("Fallback behaviour saved."); }));
  $("fb-add-btn").addEventListener("click", () => act(async () => { if (!$("fb-add").value) return; prefs = (await api("/api/v1/models/preferences", { preferred_routes: [...(prefs.preferred_routes || []), $("fb-add").value] })).preferences; renderFallbacks(); }));

  // ---------------------------------------------------------------- local / privacy
  async function renderLocal() {
    $("local-only").checked = !!prefs.local_only;
    $("local-note").textContent = deployment === "cloud"
      ? "This PeoplePay runs in the cloud, so it cannot reach a model on your own computer (localhost means the server). Use a self-hosted PeoplePay, or an Ollama/vLLM endpoint reachable from the server that an administrator has allow-listed."
      : "Self-hosted: the PeoplePay backend can reach local runtimes such as Ollama at the address you configure (default http://127.0.0.1:11434).";
    const { connections } = await api("/api/v1/models/connections"), box = $("local-cards"); box.replaceChildren();
    const locals = connections.filter((c) => c.provider.local);
    if (!locals.length) box.append(node("p", "No local runtime configured. Connect Ollama (or a local OpenAI-compatible server and mark its data boundary as local) above.", "pp-empty"));
    for (const c of locals) { const a = node("article", undefined, "pp-card"); a.append(node("h3", c.connection.display_name), node("span", c.status, `pill ${stClass(c.status)}`), node("p", `${c.models_found} local models · no cloud API quota (uses your hardware)`)); box.append(a); }
  }
  $("local-only").addEventListener("change", () => act(async () => { prefs = (await api("/api/v1/models/preferences", { local_only: $("local-only").checked })).preferences; say($("local-only").checked ? "Local only is on." : "Local only is off."); }));
  function renderPrivacy() { $("allow-cloud-sens").checked = !!prefs.allow_cloud_for_sensitive; $("allow-auto-fb-sens").checked = !!prefs.allow_auto_fallback_sensitive; $("ctx").value = prefs.context_strategy || "trim"; }
  for (const [id, k] of [["allow-cloud-sens", "allow_cloud_for_sensitive"], ["allow-auto-fb-sens", "allow_auto_fallback_sensitive"]]) $(id).addEventListener("change", () => act(async () => { prefs = (await api("/api/v1/models/preferences", { [k]: $(id).checked })).preferences; say("Privacy setting saved."); }));

  // ---------------------------------------------------------------- usage
  async function renderUsage() {
    const u = await api("/api/v1/models/usage"), body = $("usage-rows"); body.replaceChildren();
    const entries = Object.values(u.providers);
    if (!entries.length) { const tr = node("tr"); tr.append(node("td", "No usage recorded yet.", undefined, { colspan: "7" })); body.append(tr); }
    for (const v of entries) {
      const tr = node("tr"); const cell = (t, small) => { const td = node("td", t); if (small) td.append(node("small", small)); tr.append(td); };
      cell(v.connection_name, v.provider_id); cell(String(v.requests));
      cell(v.input_tokens == null ? "not reported" : `${v.input_tokens} / ${v.output_tokens}`);
      cell(v.estimated_cost == null ? "unknown" : v.estimated_cost.toFixed(4), v.cost_note);
      cell(String(v.errors)); cell(String(v.fallbacks)); cell(v.avg_latency_ms == null ? "—" : `${Math.round(v.avg_latency_ms)} ms`);
      body.append(tr);
    }
  }

  // ---------------------------------------------------------------- playground
  function renderCompare() {
    for (const id of ["cmp-a", "cmp-b", "cmp-c"]) {
      const s = $(id); s.replaceChildren(node("option", id === "cmp-a" ? "Choose model A" : "None", undefined, { value: "" }));
      for (const m of catalog.models.filter((x) => x.selectable_as_chat)) s.append(node("option", `${m.display_name} — ${m.route}`, undefined, { value: keyOf(m) }));
    }
  }
  $("cmp-run").addEventListener("click", () => act(async () => {
    const keys = ["cmp-a", "cmp-b", "cmp-c"].map((i) => $(i).value).filter(Boolean), text = $("cmp-text").value.trim();
    if (!text || keys.length < 2) { say("Enter a prompt and choose at least two models.", true); return; }
    if (!confirm(`Run this prompt on ${keys.length} models? Each call may cost money.`)) return;
    const out = $("cmp-out"); out.replaceChildren();
    for (const k of keys) {
      const card = node("article", undefined, "pp-card"); out.append(card);
      try {
        const { response: r } = await api("/api/v1/chat", { text, ephemeral: true, selection: { mode: "model", model: k, one_shot: true }, fallback_mode: "NONE" });
        card.append(node("h3", `${r.served_by.provider_model_id} · ${r.served_by.route}`), node("p", r.text, undefined), node("small", `${Math.round(r.latency_ms)} ms · tokens ${r.usage.input_tokens ?? "?"}/${r.usage.output_tokens ?? "?"} · cost ${r.usage.estimated_cost ?? "unknown"}`));
      } catch (e) { card.append(node("h3", k), node("p", e.detail && e.detail.message || e.message)); }
    }
  }));
  $("dev").checked = PP.devMode();
  $("dev").addEventListener("change", () => PP.setDevMode($("dev").checked));
  act(loadAll);
})();
