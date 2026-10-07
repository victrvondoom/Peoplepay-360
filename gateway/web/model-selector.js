"use strict";
/* PeoplePay model selector + shared helpers. Everything shown comes from /api/v1/models (discovery/config);
   no model names are hardcoded here. DOM is built with textContent only (model names are untrusted strings). */
(function () {
  const PP = (window.PP = window.PP || {});
  PP.user = localStorage.getItem("peoplepay-user") || crypto.randomUUID();
  localStorage.setItem("peoplepay-user", PP.user);
  PP.token = () => sessionStorage.getItem("peoplepay-token") || "";
  PP.headers = () => ({ "Content-Type": "application/json", "X-Beacon-User": PP.user, ...(PP.token() ? { Authorization: `Bearer ${PP.token()}` } : {}) });
  PP.node = (tag, text, cls, attrs) => {
    const n = document.createElement(tag);
    if (text !== undefined && text !== null) n.textContent = text;
    if (cls) n.className = cls;
    for (const [k, v] of Object.entries(attrs || {})) n.setAttribute(k, v);
    return n;
  };
  PP.api = async (path, body, signal) => {
    const r = await fetch(path, { method: body === undefined ? "GET" : "POST", headers: PP.headers(), signal, ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
    let data;
    try { data = await r.json(); } catch (_) { throw Object.assign(new Error(`Unreadable response (${r.status})`), { status: r.status }); }
    if (!r.ok) throw Object.assign(new Error((data.error && (data.error.message || data.error)) || `Request failed (${r.status})`), { status: r.status, detail: data.error || {} });
    return data;
  };
  PP.devMode = () => { try { return localStorage.getItem("peoplepay-dev") === "1"; } catch (_) { return false; } };
  PP.setDevMode = (v) => { try { localStorage.setItem("peoplepay-dev", v ? "1" : "0"); } catch (_) {} };
  const CAP_LABEL = { vision: "Vision", tools: "Tools", reasoning: "Reasoning", structured_output: "Structured", long_context: "Long context", files: "Files", streaming: "Streaming" };
  PP.badges = (m) => {
    const wrap = PP.node("div", undefined, "pp-badges");
    wrap.append(PP.node("span", m.local ? "Local" : "Cloud", `badge ${m.local ? "local" : "cloud"}`));
    for (const [cap, ev] of Object.entries((m.capabilities && m.capabilities.items) || {})) {
      if (!CAP_LABEL[cap] || cap === "streaming") continue;
      const weak = ev === "static_fallback" || ev === "user_override";
      wrap.append(PP.node("span", CAP_LABEL[cap] + (weak ? "?" : ""), "badge" + (weak ? " weak" : ""), { title: `${CAP_LABEL[cap]} — evidence: ${ev.replace("_", " ")}` + (weak ? " (inferred or user-set; use Test to confirm)" : "") }));
    }
    if (m.context_window) wrap.append(PP.node("span", `${Math.round(m.context_window / 1000)}k ctx`, "badge"));
    if (m.health && !["HEALTHY", "UNKNOWN"].includes(m.health)) wrap.append(PP.node("span", m.health.replace("_", " ").toLowerCase(), "badge warn"));
    return wrap;
  };

  const MODES = [
    ["auto", "Auto", "PeoplePay chooses by task, capability, availability and your preferences."],
    ["fast", "Fast", "Prefers quicker, lighter models."],
    ["balanced", "Balanced", "A middle path between speed and depth."],
    ["deep", "Deep reasoning", "Prefers reasoning-capable models for harder work."],
    ["local", "Local", "Runs only on models inside your local boundary."],
  ];
  const STORE_KEY = "peoplepay-intelligence";
  const loadSel = () => { try { const s = JSON.parse(localStorage.getItem(STORE_KEY) || "null"); if (s && s.mode) return s; } catch (_) {} return { mode: "auto" }; };
  const saveSel = (s) => { try { localStorage.setItem(STORE_KEY, JSON.stringify(s.one_shot ? { mode: "auto" } : s)); } catch (_) {} };
  let uid = 0;

  PP.mountSelector = function (host, { onChange } = {}) {
    const id = `pp-sel-${++uid}`;
    const hadStored = (() => { try { return !!localStorage.getItem(STORE_KEY); } catch (_) { return false; } })();
    let sel = loadSel(), catalog = null, prefs = {}, open = false, more = false, filters = { q: "", vision: false, tools: false, reasoning: false, local: false };
    const btn = PP.node("button", undefined, "pp-sel-btn", { type: "button", "aria-haspopup": "dialog", "aria-expanded": "false", "aria-controls": id });
    const kick = PP.node("span", "Intelligence", "pp-sel-kicker"), label = PP.node("span", "Auto", "pp-sel-label"), caret = PP.node("span", "▾");
    caret.setAttribute("aria-hidden", "true");
    btn.append(kick, label, caret);
    const panel = PP.node("div", undefined, "pp-panel", { id, role: "dialog", "aria-label": "Choose intelligence", hidden: "" });
    host.classList.add("pp-sel");
    host.append(btn, panel);

    const nameOf = (s) => {
      if (s.mode !== "model") return (MODES.find((m) => m[0] === s.mode) || MODES[0])[1];
      const m = ((catalog && catalog.models) || []).find((x) => x.provider_model_id === s.model || `${x.connection_id}::${x.provider_model_id}` === s.model);
      return m ? m.display_name : s.model;
    };
    const refreshLabel = () => { label.textContent = nameOf(sel); btn.setAttribute("aria-label", `Intelligence: ${nameOf(sel)}. Change`); };
    const choose = (next) => {
      sel = next; saveSel(sel); refreshLabel(); close(true);
      if (onChange) onChange({ ...sel }, nameOf(sel));
    };
    const close = (refocus) => { open = false; panel.hidden = true; btn.setAttribute("aria-expanded", "false"); if (refocus) btn.focus(); };
    const options = () => Array.from(panel.querySelectorAll("button.pp-opt"));

    async function load() {
      const [c, p] = await Promise.all([PP.api("/api/v1/models/catalog"), PP.api("/api/v1/models/preferences")]);
      catalog = c; prefs = p.preferences || {};
      // No explicit choice yet on this device: start from the user's saved default model (if any), else Auto.
      if (!hadStored && !sel.model && prefs.default_model) { sel = { mode: "model", model: prefs.default_model }; if (onChange) onChange({ ...sel }, nameOf(sel)); }
      refreshLabel();
    }
    function row(main, sub, selected, onPick, badges) {
      const b = PP.node("button", undefined, "pp-opt", { type: "button", role: "option", "aria-selected": selected ? "true" : "false" });
      b.append(PP.node("strong", main));
      if (sub) b.append(PP.node("small", sub));
      if (badges) b.append(badges);
      b.addEventListener("click", onPick);
      return b;
    }
    function render() {
      panel.replaceChildren();
      const tier1 = PP.node("div", undefined, undefined, { role: "listbox", "aria-label": "Intelligence level" });
      panel.append(PP.node("h3", "Recommended"));
      for (const [mode, name, desc] of MODES) tier1.append(row(name, desc, sel.mode === mode, () => choose({ mode, one_shot: sel.one_shot })));
      panel.append(tier1);
      const models = (catalog && catalog.models || []).filter((m) => m.selectable_as_chat);
      const keyOf = (m) => `${m.connection_id}::${m.provider_model_id}`;
      const quick = [...new Set([...(prefs.favorites || []), ...(prefs.recent || [])])].map((k) => models.find((m) => keyOf(m) === k)).filter(Boolean).slice(0, 6);
      if (quick.length) {
        panel.append(PP.node("h3", "Favorites & recent"));
        const l = PP.node("div", undefined, undefined, { role: "listbox", "aria-label": "Favorites and recent models" });
        for (const m of quick) l.append(row(m.display_name, `${m.route}${m.local ? " · local" : ""}`, sel.model === keyOf(m), () => choose({ mode: "model", model: keyOf(m), one_shot: sel.one_shot })));
        panel.append(l);
      }
      if (!models.length) panel.append(PP.node("p", "No models found yet. Connect a provider or configure a local model in AI & Models settings.", "pp-muted"));
      const moreBtn = PP.node("button", more ? "Fewer models" : `More models${models.length ? ` (${models.length})` : ""}…`, "secondary", { type: "button", "aria-expanded": String(more) });
      moreBtn.addEventListener("click", () => { more = !more; render(); (more ? panel.querySelector("input[type=search]") : moreBtn) && (more ? panel.querySelector("input[type=search]") : panel.querySelector("button.secondary")).focus(); });
      panel.append(PP.node("div", undefined, "pp-foot")); panel.lastChild.append(moreBtn);
      if (more) renderBrowser(models, keyOf);
      const foot = PP.node("div", undefined, "pp-foot");
      const lab = PP.node("label"), cb = PP.node("input", undefined, undefined, { type: "checkbox" });
      cb.checked = !!sel.one_shot;
      cb.addEventListener("change", () => { sel = { ...sel, one_shot: cb.checked }; if (onChange) onChange({ ...sel }, nameOf(sel)); });
      lab.append(cb, document.createTextNode(" Use for the next message only, then return to Auto"));
      foot.append(lab, PP.node("p", "PeoplePay chooses based on task, capability, availability and preferences. Provider and model names are shown factually and imply no affiliation.", "pp-muted"));
      panel.append(foot);
    }
    function renderBrowser(models, keyOf) {
      const box = PP.node("div");
      box.append(PP.node("h3", "All connected models"));
      const q = PP.node("input", undefined, undefined, { type: "search", placeholder: "Search models, providers", "aria-label": "Search models", value: filters.q });
      q.addEventListener("input", () => { filters.q = q.value; renderList(); });
      const f = PP.node("div", undefined, "pp-filters", { role: "group", "aria-label": "Filter models" });
      for (const [k, t] of [["vision", "Vision"], ["tools", "Tools"], ["reasoning", "Reasoning"], ["local", "Local only"]]) {
        const l = PP.node("label"), c = PP.node("input", undefined, undefined, { type: "checkbox" });
        c.checked = filters[k]; c.addEventListener("change", () => { filters[k] = c.checked; renderList(); });
        l.append(c, document.createTextNode(t)); f.append(l);
      }
      const list = PP.node("div", undefined, undefined, { role: "listbox", "aria-label": "Models" });
      box.append(q, f, list); panel.append(box);
      function renderList() {
        list.replaceChildren();
        const groups = new Map();
        for (const m of models) {
          const t = `${m.display_name} ${m.provider_model_id} ${m.provider_id} ${m.route}`.toLowerCase();
          if (filters.q && !t.includes(filters.q.toLowerCase())) continue;
          if (filters.local && !m.local) continue;
          const has = (c) => m.capabilities && m.capabilities.items && c in m.capabilities.items;
          if ((filters.vision && !has("vision")) || (filters.tools && !has("tools")) || (filters.reasoning && !has("reasoning"))) continue;
          (groups.get(m.canonical_model_id) || groups.set(m.canonical_model_id, []).get(m.canonical_model_id)).push(m);
        }
        if (!groups.size) list.append(PP.node("p", "No models match.", "pp-muted"));
        for (const routes of Array.from(groups.values()).slice(0, 80)) {
          let cur = routes.find((r) => keyOf(r) === sel.model) || routes[0];
          const wrap = PP.node("div", undefined, "pp-model-row");
          const left = PP.node("div");
          const o = row(cur.display_name, `via ${cur.route}${cur.connection_name && cur.connection_name !== cur.route ? ` · ${cur.connection_name}` : ""}`, sel.model === keyOf(cur), () => choose({ mode: "model", model: keyOf(cur), connection_id: routes.length > 1 ? cur.connection_id : undefined, one_shot: sel.one_shot }), PP.badges(cur));
          left.append(o);
          if (routes.length > 1) {
            const s = PP.node("select", undefined, undefined, { "aria-label": `Provider route for ${cur.display_name}` });
            for (const r of routes) s.append(PP.node("option", `${r.route} (${r.connection_name})`, undefined, { value: keyOf(r) }));
            s.value = keyOf(cur); s.addEventListener("change", () => { cur = routes.find((r) => keyOf(r) === s.value); });
            const wr = PP.node("div", undefined, "pp-routes"); wr.append(PP.node("small", "Available through: ", "pp-muted"), s); left.append(wr);
          }
          const star = PP.node("button", (prefs.favorites || []).includes(keyOf(cur)) ? "★" : "☆", "pp-star", { type: "button", "aria-label": `Favorite ${cur.display_name}`, "aria-pressed": String((prefs.favorites || []).includes(keyOf(cur))) });
          star.addEventListener("click", async () => {
            const set = new Set(prefs.favorites || []); set.has(keyOf(cur)) ? set.delete(keyOf(cur)) : set.add(keyOf(cur));
            prefs = (await PP.api("/api/v1/models/preferences", { favorites: [...set] })).preferences; renderList();
          });
          wrap.append(left, star); list.append(wrap);
        }
      }
      renderList();
    }
    const focusFirst = () => { const o = options(); (o.find((x) => x.getAttribute("aria-selected") === "true") || o[0] || btn).focus(); };
    async function openPanel() {
      open = true; panel.hidden = false; btn.setAttribute("aria-expanded", "true");
      if (catalog) { render(); focusFirst(); return; }              // cached: instant, no refetch on every open
      panel.replaceChildren(PP.node("p", "Loading models…", "pp-muted"));
      try { await load(); } catch (e) { panel.replaceChildren(PP.node("p", `Could not load models: ${e.message}`)); return; }
      if (!open) return;
      render(); focusFirst();
    }
    btn.addEventListener("click", () => (open ? close(true) : openPanel()));
    panel.addEventListener("keydown", (e) => {
      if (e.key === "Escape") { e.preventDefault(); close(true); return; }
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        const o = options(), i = o.indexOf(document.activeElement);
        if (i >= 0) { e.preventDefault(); o[(i + (e.key === "ArrowDown" ? 1 : -1) + o.length) % o.length].focus(); }
      }
    });
    // composedPath() is captured at dispatch: a re-render that detaches e.target must not read as an outside click.
    document.addEventListener("click", (e) => { if (open && !e.composedPath().includes(host)) close(false); });
    load().then(refreshLabel).catch(() => {});
    refreshLabel();
    return { get selection() { return { ...sel }; }, reset() { if (sel.one_shot) { sel = { mode: "auto" }; saveSel(sel); refreshLabel(); if (onChange) onChange({ ...sel }, nameOf(sel)); } }, label: () => nameOf(sel), reload: load };
  };
})();
