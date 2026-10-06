"use strict";
const $ = (id) => document.getElementById(id);
let user = localStorage.getItem("peoplepay-user") || crypto.randomUUID();
localStorage.setItem("peoplepay-user", user);
let token = sessionStorage.getItem("peoplepay-token") || "",
  selected = null,
  transactions = [],
  context = {},
  record = {},
  busy = false;
const account = $("account");
account.elements.user.value = user;
const message = (text) => {
  $("notice").textContent = text;
};
const json = (value) => JSON.stringify(value, null, 2);
const money = (minor) => (minor / 100).toFixed(2);
function minor(value) {
  if (!/^\d{1,10}(\.\d{1,2})?$/.test(value))
    throw Error("Enter a non-negative amount with at most two decimal places");
  const [a, b = ""] = value.split(".");
  return Number(a) * 100 + Number(b.padEnd(2, "0"));
}
async function api(path, body) {
  const response = await fetch(path, {
    method: body === undefined ? "GET" : "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Beacon-User": user,
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  const data = await response.json();
  if (!response.ok) throw Error(data.error || `HTTP ${response.status}`);
  return data;
}
async function run(action) {
  if (busy) return;
  busy = true;
  document.querySelectorAll("button").forEach((b) => (b.disabled = true));
  try {
    await action();
  } catch (error) {
    message(error.message);
  } finally {
    busy = false;
    document.querySelectorAll("button").forEach((b) => (b.disabled = false));
    syncControls();
  }
}
function syncControls() {
  const cancelled = record.transaction?.state === "CANCELLED";
  const ordered = Boolean(context.fulfillment?.order);
  $("cart-form")
    .querySelectorAll("input,select,button")
    .forEach((element) => {
      element.disabled = cancelled || ordered;
    });
  $("checkout").disabled = cancelled || ordered || !context.product?.cart;
  $("confirm").disabled = $("checkout").disabled;
  $("cancel").disabled = cancelled;
  $("plan-form")
    .querySelectorAll("input,textarea,select,button")
    .forEach((element) => {
      element.disabled = cancelled;
    });
}
function tab(name) {
  document.querySelectorAll(".view").forEach((v) => (v.hidden = v.id !== name));
  document
    .querySelectorAll("[data-tab]")
    .forEach((b) =>
      b.setAttribute("aria-current", String(b.dataset.tab === name)),
    );
}
document
  .querySelectorAll("[data-tab]")
  .forEach((b) => (b.onclick = () => tab(b.dataset.tab)));
tab("plan");
function list() {
  $("transactions").replaceChildren();
  const query = $("search").value.toLowerCase();
  for (const t of transactions.filter((t) =>
    (t.raw_utterance || t.transaction_id).toLowerCase().includes(query),
  )) {
    const b = document.createElement("button");
    b.textContent = t.raw_utterance || t.transaction_id;
    b.className = t.transaction_id === selected ? "selected" : "";
    b.onclick = () => run(() => load(t.transaction_id));
    $("transactions").append(b);
  }
}
async function refresh() {
  const data = await api("/transactions");
  transactions = data.transactions;
  list();
}
async function loadModules() {
  const response = await fetch("/product/modules");
  if (!response.ok) throw Error(`Product directory unavailable (${response.status})`);
  const { modules } = await response.json();
  const directory = $("modules");
  directory.replaceChildren();
  for (const module of modules) {
    const card = document.createElement(module.url ? "a" : "div");
    card.className = "module-card";
    if (module.url) {
      card.href = module.url;
      card.target = "_blank";
      card.rel = "noopener noreferrer";
      card.setAttribute("aria-label", `Open ${module.name} in a new tab`);
    } else {
      card.setAttribute("aria-disabled", "true");
      card.title = `Set the service URL to enable ${module.name}`;
    }
    const name = document.createElement("strong");
    name.textContent = module.name;
    const description = document.createElement("span");
    description.textContent = module.description;
    const status = document.createElement("small");
    status.textContent = module.url ? "OPEN WORKSPACE ↗" : "SERVICE NOT CONFIGURED";
    card.append(name, description, status);
    directory.append(card);
  }
}
async function load(id) {
  selected = id;
  const t = await api(`/transactions/${id}`);
  context = (await api(`/transactions/${id}/context`)).context;
  record = { transaction: t, context };
  $("empty").hidden = true;
  $("detail").hidden = false;
  $("title").textContent = t.raw_utterance || id;
  $("status").textContent = t.state;
  list();
  const p = t.plan || {};
  const f = $("plan-form").elements;
  f.summary.value = p.summary || "";
  f.steps.value = (p.steps || []).join("\n");
  f.amount.value = money(p.estimated_amount?.minor || 0);
  f.currency.value = p.estimated_amount?.currency || "INR";
  $("validation").textContent = "";
  const cart = context.product?.cart;
  $("items").replaceChildren();
  (cart?.items || [{}]).forEach(addItem);
  const c = $("cart-form").elements;
  c.currency.value = cart?.currency || "INR";
  c.shipping.value = money(cart?.shipping_minor || 0);
  c.tax.value = money(cart?.tax_minor || 0);
  $("confirm").checked = false;
  total();
  const order = context.fulfillment?.order;
  $("order-summary").textContent = order
    ? `SANDBOX | ${order.order_id}\n${order.status} | ${order.cart.currency} ${money(order.cart.total.minor)}\nNo money moved. Updates are user-recorded.\n${json(order.updates)}`
    : "No order recorded.";
  const statuses = {
    PLACED: ["SHIPPED", "CANCELLED"],
    SHIPPED: ["DELIVERED", "DELIVERY_FAILED"],
    DELIVERY_FAILED: ["SHIPPED", "CANCELLED"],
  };
  const select = $("delivery").elements.status;
  select.replaceChildren();
  for (const status of statuses[order?.status] || []) {
    const option = document.createElement("option");
    option.value = option.textContent = status;
    select.append(option);
  }
  $("delivery").hidden = !select.options.length;
  $("dispute").hidden = !order;
  const dispute = context.fulfillment?.dispute;
  $("delivery").elements.note.value = "";
  $("dispute").elements.issue.value = dispute?.issue || "";
  $("dispute").elements.remedy.value = dispute?.remedy || "";
  $("capability-result").textContent = "";
  $("draft").textContent = dispute
    ? `DRAFT - not submitted\n\n${dispute.draft}`
    : "";
  $("download-draft").hidden = !dispute;
  record.evidence = await api(`/transactions/${id}/evidence`);
  record.activity = await api(`/transactions/${id}/timeline`);
  $("evidence-data").textContent = json({
    evidence: record.evidence,
    activity: record.activity,
  });
}
async function action(name, body) {
  const result = await api(`/transactions/${selected}/${name}`, body);
  await refresh();
  await load(selected);
  message("Saved successfully.");
  return result;
}
$("search").oninput = list;
$("refresh").onclick = () =>
  run(async () => {
    await refresh();
    if (selected) await load(selected);
    await health();
  });
$("create").onsubmit = (e) => {
  e.preventDefault();
  run(async () => {
    const t = await api("/transactions", {
      raw_utterance: e.target.elements.raw_utterance.value,
    });
    await refresh();
    await load(t.transaction_id);
    e.target.reset();
    message("Transaction created.");
  });
};
account.onsubmit = (e) => {
  e.preventDefault();
  run(async () => {
    user = account.elements.user.value.trim();
    token = account.elements.token.value;
    sessionStorage.setItem("peoplepay-token", token);
    localStorage.setItem("peoplepay-user", user);
    selected = null;
    transactions = [];
    context = {};
    record = {};
    list();
    $("detail").hidden = true;
    $("empty").hidden = false;
    await refresh();
    await health();
    message("Connection updated.");
  });
};
$("plan-form").onsubmit = (e) => {
  e.preventDefault();
  run(async () => {
    const f = e.target.elements;
    await action("plan", {
      summary: f.summary.value,
      steps: f.steps.value.split("\n").filter((s) => s.trim()),
      amount_minor: minor(f.amount.value),
      currency: f.currency.value,
    });
  });
};
$("validate").onclick = () =>
  run(async () => {
    const result = await action("validate", {});
    $("validation").textContent = json(result);
    message(
      result.valid ? "Validation passed." : "Validation requires attention.",
    );
  });
$("cancel").onclick = () => {
  if (
    confirm(
      "Cancel this transaction? This does not cancel an external order or refund a payment.",
    )
  )
    run(() => action("cancel", {}));
};
function addItem(item = {}) {
  const row = document.createElement("div");
  row.className = "item";
  for (const [name, label, value, type] of [
    ["title", "Product", item.title || "", "text"],
    ["merchant", "Merchant", item.merchant || "", "text"],
    ["variant", "Variant", item.variant || "Standard", "text"],
    ["quantity", "Quantity", item.quantity || 1, "number"],
    ["price", "Unit price", money(item.unit_price_minor || 0), "text"],
    ["url", "Product URL (optional)", item.url || "", "url"],
  ]) {
    const l = document.createElement("label");
    l.textContent = label;
    const input = document.createElement("input");
    input.name = name;
    input.value = value;
    input.type = type;
    input.required = name !== "url";
    if (name === "quantity") {
      input.min = 1;
      input.max = 100;
    }
    l.append(input);
    row.append(l);
  }
  const remove = document.createElement("button");
  remove.type = "button";
  remove.textContent = "Remove item";
  remove.onclick = () => {
    row.remove();
    total();
  };
  row.append(remove);
  $("items").append(row);
}
function cartBody() {
  const f = $("cart-form").elements;
  return {
    currency: f.currency.value,
    shipping_minor: minor(f.shipping.value),
    tax_minor: minor(f.tax.value),
    items: [...$("items").children].map((row) => {
      const get = (name) => row.querySelector(`[name=${name}]`).value;
      return {
        title: get("title"),
        merchant: get("merchant"),
        variant: get("variant"),
        quantity: Number(get("quantity")),
        unit_price_minor: minor(get("price")),
        url: get("url"),
      };
    }),
  };
}
function total() {
  try {
    const c = cartBody();
    $("total").textContent =
      `Total: ${c.currency} ${money(c.items.reduce((sum, i) => sum + i.quantity * i.unit_price_minor, c.shipping_minor + c.tax_minor))}`;
  } catch {
    $("total").textContent = "Enter valid amounts to calculate total.";
  }
}
$("add-item").onclick = () => {
  addItem();
  total();
  $("confirm").checked = false;
};
$("cart-form").oninput = () => {
  total();
  $("confirm").checked = false;
};
$("cart-form").onsubmit = (e) => {
  e.preventDefault();
  run(() => action("cart", cartBody()));
};
$("checkout").onclick = () =>
  run(async () => {
    const saved = context.product?.cart;
    if (!saved) throw Error("Save your cart first");
    const current = cartBody();
    if (
      json(current) !==
      json({
        currency: saved.currency,
        shipping_minor: saved.shipping_minor,
        tax_minor: saved.tax_minor,
        items: saved.items,
      })
    )
      throw Error("Save your changed cart before checkout");
    await action("sandbox-checkout", {
      cart_hash: saved.cart_hash,
      confirm_sandbox: $("confirm").checked,
    });
    tab("order");
    message("Sandbox order recorded. No money moved.");
  });
$("delivery").onsubmit = (e) => {
  e.preventDefault();
  run(() =>
    action("delivery", {
      status: e.target.elements.status.value,
      note: e.target.elements.note.value,
    }),
  );
};
$("dispute").onsubmit = (e) => {
  e.preventDefault();
  run(() =>
    action("dispute", {
      issue: e.target.elements.issue.value,
      remedy: e.target.elements.remedy.value,
    }),
  );
};
function download(name, text, type) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
$("export").onclick = () =>
  download(`peoplepay-${selected}.json`, json(record), "application/json");
$("download-draft").onclick = () =>
  download("dispute-draft.txt", $("draft").textContent, "text/plain");
async function health() {
  const h = await api("/health/integrations");
  $("connection").textContent =
    `${h.auth.mode} | Local workspace | Payments unavailable`;
  $("health").replaceChildren();
  for (const c of h.capabilities) {
    const p = document.createElement("p");
    p.textContent = `${c.name}: ${c.mode} - ${c.detail || ""}`;
    $("health").append(p);
  }
}
$("capability").onsubmit = (e) => {
  e.preventDefault();
  run(async () => {
    const f = e.target.elements,
      name = f.name.value,
      q = f.query.value;
    const body =
      name === "market"
        ? { item_query: q }
        : name === "property"
          ? { address: q }
          : name === "resolution"
            ? { action: "ask", question: q }
            : { room: JSON.parse(q) };
    const result = await action(`capabilities/${name}`, body);
    $("capability-result").textContent = json(result);
  });
};
run(async () => {
  await loadModules();
  await health();
  await refresh();
  if (transactions.length)
    await load(transactions[transactions.length - 1].transaction_id);
  message("Local workspace ready. Live payments are unavailable.");
});
