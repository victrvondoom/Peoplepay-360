"use strict";
(function () {
  const $ = (id) => document.getElementById(id);
  const { node, api } = PP;
  let conversationId = null, selector, attachment = null, abort = null, busy = false, last = null;
  $("dev").checked = PP.devMode();
  $("dev").addEventListener("change", () => PP.setDevMode($("dev").checked));
  const setStatus = (t) => { $("status").textContent = t || ""; };

  selector = PP.mountSelector($("selector"), { onChange: (sel, name) => setStatus(`Future replies will use ${name}${sel.one_shot ? " (next message only)" : ""}.`) });

  api("/api/v1/models/preferences").then((p) => { $("local-only").checked = !!(p.preferences || {}).local_only; });
  $("local-only").addEventListener("change", () => api("/api/v1/models/preferences", { local_only: $("local-only").checked }).then(() => setStatus($("local-only").checked ? "Local only is on. Requests stay on local models." : "Local only is off.")));
  api("/api/v1/models/connections").then((c) => { $("empty").hidden = c.connections.some((x) => x.models_found > 0); }).catch(() => {});

  $("image").addEventListener("change", () => {
    const f = $("image").files[0];
    if (!f) { attachment = null; return; }
    if (f.size > 4 * 1024 * 1024) { setStatus("Image is larger than 4 MB."); $("image").value = ""; return; }
    const r = new FileReader();
    r.onload = () => { attachment = { kind: "image", media_type: f.type, data_b64: String(r.result).split(",")[1] }; setStatus(`Image attached: ${f.name}`); };
    r.readAsDataURL(f);
  });

  function addMessage(role, text) {
    const m = node("div", text, `pp-msg ${role}`);
    $("log").append(m); $("log").scrollTop = $("log").scrollHeight;
    return m;
  }
  function metaFor(served, resp) {
    const meta = node("div", undefined, "pp-meta");
    const via = served.fallback_reason ? ` · requested ${served.requested || "another model"}` : "";
    meta.append(document.createTextNode(`${served.provider_model_id} · ${served.route}${resp && resp.latency_ms ? ` · ${Math.round(resp.latency_ms)} ms` : ""}${via}`));
    if (served.fallback_reason) meta.append(node("span", ` · switched provider (${served.fallback_reason.toLowerCase().replaceAll("_", " ")})`, "fb"));
    return meta;
  }
  function devPanel(resp, explain) {
    if (!PP.devMode()) return null;
    const d = node("div", undefined, "pp-dev");
    d.append(node("strong", "Why this model?"));
    const ul = node("ul");
    for (const line of (resp && resp.routing_explanation) || []) ul.append(node("li", line));
    d.append(ul);
    if (resp && resp.attempts) d.append(node("div", "Attempts: " + resp.attempts.map((a) => `${a.model_id} → ${a.status}${a.error_code ? ` (${a.error_code})` : a.reason ? ` (${a.reason})` : ""}`).join("; ")));
    if (resp && resp.usage) d.append(node("div", `Tokens in/out: ${resp.usage.input_tokens ?? "unknown"} / ${resp.usage.output_tokens ?? "unknown"} · Cost: ${resp.usage.estimated_cost ?? "unknown"}`));
    if (resp && resp.notes && resp.notes.length) d.append(node("div", "Notes: " + resp.notes.join("; ")));
    if (explain && explain.excluded && explain.excluded.length) {
      const ex = node("ul"); for (const e of explain.excluded.slice(0, 8)) ex.append(node("li", `Excluded ${e.model}: ${e.reason}`));
      d.append(node("div", "Considered but excluded:"), ex);
    }
    return d;
  }
  function showAlert(err, retry) {
    const box = $("alert"); box.replaceChildren(); box.hidden = false; box.className = "pp-alert";
    const d = err.detail || {};
    box.append(node("div", d.message || err.message));
    if (d.detail && PP.devMode()) box.append(node("div", `Detail: ${d.detail}`, "pp-meta"));
    const row = node("div", undefined, "pp-row");
    const btn = (t, fn, cls = "secondary") => { const b = node("button", t, cls, { type: "button" }); b.addEventListener("click", () => { box.hidden = true; fn(); }); row.append(b); };
    if (d.needs_consent === "drop_images") {
      btn("Choose another model", () => $("selector").querySelector("button").click());
      btn("Continue without image context", () => retry({ allow_drop_unsupported: true }), "primary");
    } else if (d.ask_privacy_change) {
      btn("Turn off Local only and retry", async () => { await api("/api/v1/models/preferences", { local_only: false }); $("local-only").checked = false; retry({}); }, "primary");
      btn("Keep Local only", () => {});
    } else if (d.ask_before_switching) {
      for (const a of d.alternatives || []) btn(`Switch to ${a.label}`, () => retry({ selection: { mode: "model", model: a.route_key, one_shot: true } }), "primary");
      btn("Use automatic fallback", () => retry({ fallback_mode: "AUTOMATIC" }));
    } else {
      btn("Retry", () => retry({}), "primary");
      btn("Switch model", () => $("selector").querySelector("button").click());
      if (["RATE_LIMITED", "PROVIDER_UNAVAILABLE", "TIMEOUT", "MODEL_UNAVAILABLE"].includes(d.code)) btn("Use fallback", () => retry({ fallback_mode: "AUTOMATIC" }));
    }
    box.append(row);
  }

  async function send(text, extra = {}) {
    if (busy) return;
    busy = true; $("send").disabled = true; $("stop").hidden = false; $("alert").hidden = true;
    const sel = extra.selection || selector.selection;
    const body = { text, conversation_id: conversationId, stream: true, selection: sel, data_class: $("data-class").value, ...(extra.fallback_mode ? { fallback_mode: extra.fallback_mode } : {}),
      ...(extra.allow_drop_unsupported ? { allow_drop_unsupported: true } : {}), ...($("policy").value ? { routing_policy: $("policy").value } : {}), ...(attachment ? { attachments: [attachment] } : {}) };
    last = { text, extra };
    const bubble = addMessage("assistant", "");
    bubble.setAttribute("aria-busy", "true");
    abort = new AbortController();
    let explain = null;
    if (PP.devMode()) { try { explain = await api("/api/v1/models/explain", { text, selection: sel, data_class: body.data_class, ...(attachment ? { attachments: [attachment] } : {}) }); } catch (_) {} }
    try {
      const r = await fetch("/api/v1/chat", { method: "POST", headers: PP.headers(), body: JSON.stringify(body), signal: abort.signal });
      if (!r.ok) { let e = {}; try { e = (await r.json()).error || {}; } catch (_) {} throw Object.assign(new Error(e.message || "Request failed"), { detail: e }); }
      const reader = r.body.getReader(), dec = new TextDecoder(); let buf = "", userShown = false, done = null, error = null;
      for (;;) {
        const { value, done: fin } = await reader.read();
        if (fin) break;
        buf += dec.decode(value, { stream: true });
        let i;
        while ((i = buf.indexOf("\n\n")) >= 0) {
          const chunk = buf.slice(0, i); buf = buf.slice(i + 2);
          if (!chunk.startsWith("data:")) continue;
          const ev = JSON.parse(chunk.slice(5));
          if (!userShown && ev.type === "text.delta") { userShown = true; }
          if (ev.type === "text.delta") { bubble.textContent += ev.text; $("log").scrollTop = $("log").scrollHeight; }
          else if (ev.type === "response.completed") done = ev;
          else if (ev.type === "error") error = ev;
        }
      }
      if (error) throw Object.assign(new Error(error.message), { detail: error });
      if (done) {
        conversationId = done.conversation_id;
        const resp = done.response, served = resp.served_by;
        bubble.textContent = resp.text || (resp.parts.some((p) => p.kind === "tool_call") ? "The model proposed an action. PeoplePay never executes consequential actions without your approval." : "");
        bubble.append(metaFor(served, resp));
        const dev = devPanel(resp, explain); if (dev) bubble.append(dev);
        $("text").value = ""; attachment = null; $("image").value = "";
        selector.reset();
        setStatus(`Answered by ${served.provider_model_id} via ${served.route}.`);
      }
    } catch (e) {
      bubble.remove();
      if (e.name === "AbortError") setStatus("Stopped.");
      else showAlert(e, (more) => { const c = { ...last.extra, ...more }; send(last.text, c); });
    } finally {
      bubble.removeAttribute("aria-busy"); busy = false; abort = null; $("send").disabled = false; $("stop").hidden = true;
    }
  }
  $("form").addEventListener("submit", (e) => {
    e.preventDefault();
    const text = $("text").value.trim(); if (!text) return;
    addMessage("user", text);
    send(text);
  });
  $("stop").addEventListener("click", () => { if (abort) abort.abort(); });
  $("new").addEventListener("click", () => { conversationId = null; $("log").replaceChildren(); $("alert").hidden = true; setStatus("New conversation."); });
  $("text").addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) $("form").requestSubmit(); });
})();
