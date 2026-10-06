"use strict";
async function loadExtensions() {
  const actor = localStorage.getItem("peoplepay-user") || crypto.randomUUID();
  localStorage.setItem("peoplepay-user", actor);
  const token = sessionStorage.getItem("peoplepay-token") || "";
  const response = await fetch("/api/v1/extensions", {headers: {"X-Beacon-User": actor, ...(token ? {Authorization: `Bearer ${token}`} : {})}});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Provider status unavailable");
  const container = document.getElementById("providers");
  container.replaceChildren();
  for (const provider of data.extensions) {
    const card = document.createElement("section");
    card.className = "card";
    const heading = document.createElement("h2"); heading.textContent = provider.id; card.append(heading);
    const entries = {Status: provider.status, Version: provider.version, Runtime: provider.runtime_type,
      Capabilities: Object.keys(provider.capabilities || {}).join(", "), Jurisdictions: (provider.jurisdictions || []).join(", "),
      Permissions: (provider.permissions || []).join(", ") || "No authority grants", Readiness: provider.readiness,
      "License reference": provider.license_reference};
    for (const [label, value] of Object.entries(entries)) {
      const row = document.createElement("p");
      const title = document.createElement("strong"); title.textContent = `${label}: `; row.append(title, document.createTextNode(value || "Unavailable")); card.append(row);
    }
    container.append(card);
  }
  document.getElementById("status").textContent = `${data.extensions.length} registered manifest entries. Health is reported when invoked; configuration alone does not establish readiness.`;
}
loadExtensions().catch(error => {document.getElementById("status").textContent = error.message;});
