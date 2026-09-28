const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

const state = {
  dashboard: null,
  selectedItemId: "overall-basket",
  selectedCityId: "san-francisco",
  markers: null,
  hasFitMap: false,
  receiptRequest: 0,
  urlSelectionApplied: false,
};

const OVERALL_ID = "overall-basket";
const OVERALL_ITEM = Object.freeze({
  id: OVERALL_ID,
  name: "Overall inflation",
  category: "DERIVED INDEX",
  unit: "equal-weight basket",
  status: "ACTIVE",
  match_terms: ["overall basket"],
});

const ITEM_VISUAL_RULES = [
  {terms: ["rent", "apartment", "house", "home"], icon: "🏠", noun: "home"},
  {terms: ["milk"], icon: "🥛", noun: "milk"},
  {terms: ["egg"], icon: "🥚", noun: "eggs"},
  {terms: ["bread", "loaf"], icon: "🍞", noun: "bread"},
  {terms: ["chicken", "poultry"], icon: "🍗", noun: "chicken"},
  {terms: ["gasoline", "fuel", "gas gallon"], icon: "⛽", noun: "fuel"},
  {terms: ["transit", "ticket", "transport"], icon: "🚇", noun: "transit"},
  {terms: ["cappuccino", "coffee"], icon: "☕", noun: "coffee"},
  {terms: ["apple"], icon: "🍎", noun: "apples"},
  {terms: ["banana"], icon: "🍌", noun: "bananas"},
  {terms: ["orange"], icon: "🍊", noun: "oranges"},
  {terms: ["cheese"], icon: "🧀", noun: "cheese"},
  {terms: ["beef", "steak"], icon: "🥩", noun: "beef"},
  {terms: ["rice"], icon: "🍚", noun: "rice"},
  {terms: ["potato"], icon: "🥔", noun: "potatoes"},
  {terms: ["tomato"], icon: "🍅", noun: "tomatoes"},
  {terms: ["water"], icon: "💧", noun: "water"},
  {terms: ["beer"], icon: "🍺", noun: "beer"},
  {terms: ["wine"], icon: "🍷", noun: "wine"},
  {terms: ["taxi"], icon: "🚕", noun: "taxi"},
  {terms: ["electric", "utilit"], icon: "⚡", noun: "utilities"},
];

const overviewZoom = window.innerWidth < 650 ? 3 : 4;
const map = L.map("map", {zoomControl: false, minZoom: 2, maxZoom: 11, attributionControl: true}).setView([39.2, -98.2], overviewZoom);
L.control.zoom({position: "bottomright"}).addTo(map);
state.markers = L.layerGroup().addTo(map);

function setText(selector, value) {
  const element = $(selector);
  if (element) element.textContent = value ?? "—";
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: {"Content-Type": "application/json", ...(options.headers || {})},
    ...options,
  });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try { detail = (await response.json()).detail || detail; } catch (_) { /* response was not JSON */ }
    throw new Error(detail);
  }
  return response.json();
}

let toastTimer;
function toast(message) {
  const element = $("#toast");
  element.textContent = message;
  element.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => element.classList.remove("show"), 4200);
}

function currency(value) {
  if (value == null || Number.isNaN(Number(value))) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency", currency: "USD",
    minimumFractionDigits: Number(value) >= 100 ? 0 : 2,
    maximumFractionDigits: Number(value) >= 100 ? 0 : 2,
  }).format(value);
}

function markerCurrency(value) {
  if (value >= 1000) return `$${(value / 1000).toFixed(1)}k`;
  if (value >= 100) return `$${Math.round(value)}`;
  return `$${value.toFixed(value >= 10 ? 1 : 2)}`;
}

function formatDate(value) {
  if (!value) return "NOT YET SYNCED";
  return new Intl.DateTimeFormat("en-US", {month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit"}).format(new Date(value)).toUpperCase();
}

function median(values) {
  const sorted = values.filter(Number.isFinite).sort((a, b) => a - b);
  if (!sorted.length) return null;
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
}

function itemVisual(item) {
  if (!item) return {icon: "🧺", noun: "basket"};
  const haystack = [item.id, item.name, item.category, ...(item.match_terms || [])].join(" ").toLowerCase();
  return ITEM_VISUAL_RULES.find((rule) => rule.terms.some((term) => haystack.includes(term))) || {icon: "🧺", noun: "basket"};
}

function isOverall(itemId = state.selectedItemId) {
  return itemId === OVERALL_ID;
}

function priceTier(row, comparisons = itemComparisons()) {
  if (!row || comparisons.length < 2) return "mid";
  const prices = comparisons.map((entry) => entry.current_price_usd);
  const minimum = Math.min(...prices);
  const maximum = Math.max(...prices);
  if (maximum === minimum) return "mid";
  const position = (row.current_price_usd - minimum) / (maximum - minimum);
  if (position <= 1 / 3) return "low";
  if (position >= 2 / 3) return "high";
  return "mid";
}

function tierLabel(tier, overall = isOverall()) {
  const noun = overall ? "INFLATION" : "PRICE";
  return tier === "high" ? `HIGH ${noun} TIER` : tier === "low" ? `LOW ${noun} TIER` : `MID ${noun} TIER`;
}

async function loadRuntime() {
  const fallback = {
    map_tile_url: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    map_attribution: "© OpenStreetMap contributors",
    map_max_zoom: 19,
  };
  try {
    const config = await api("/api/runtime");
    L.tileLayer(config.map_tile_url, {maxZoom: config.map_max_zoom, attribution: config.map_attribution}).addTo(map);
    $("#signoz-link").href = config.signoz_ui_url || "https://signoz.io";
  } catch (_) {
    L.tileLayer(fallback.map_tile_url, {maxZoom: fallback.map_max_zoom, attribution: fallback.map_attribution}).addTo(map);
    $("#signoz-link").href = "https://signoz.io";
  }
}

function activeItems() {
  return state.dashboard?.items.filter((item) => item.status === "ACTIVE") || [];
}

function selectedItem() {
  if (isOverall()) return OVERALL_ITEM;
  return state.dashboard?.items.find((item) => item.id === state.selectedItemId) || null;
}

function itemComparisons(itemId = state.selectedItemId) {
  if (itemId === OVERALL_ID) {
    return (state.dashboard?.overall_comparisons || []).map((row) => ({
      ...row,
      item_id: OVERALL_ID,
      previous_price_usd: row.previous_index,
      current_price_usd: row.current_index,
      change_usd: row.current_index - row.previous_index,
      change_pct: row.inflation_pct,
      is_overall: true,
    }));
  }
  return state.dashboard?.comparisons.filter((row) => row.item_id === itemId) || [];
}

function selectedComparison() {
  return itemComparisons().find((row) => row.city.id === state.selectedCityId) || itemComparisons()[0] || null;
}

function updateShareableUrl() {
  if (!state.selectedItemId || !state.selectedCityId) return;
  const url = new URL(window.location.href);
  url.searchParams.set("item", state.selectedItemId);
  url.searchParams.set("city", state.selectedCityId);
  window.history.replaceState({}, "", url);
}

function itemOrder(item) {
  if (item.id === OVERALL_ID) return -1;
  const preferred = ["rent-1br-center", "milk-gallon", "eggs-dozen", "bread-pound", "chicken-pound", "gas-gallon", "transit-ticket", "cappuccino"];
  const index = preferred.indexOf(item.id);
  return index < 0 ? 100 : index;
}

function renderDashboard() {
  const data = state.dashboard;
  if (!data) return;
  const active = activeItems().sort((a, b) => itemOrder(a) - itemOrder(b) || a.name.localeCompare(b.name));
  const lenses = [OVERALL_ITEM, ...active];
  if (!state.urlSelectionApplied) {
    const params = new URLSearchParams(window.location.search);
    const requestedItem = params.get("item");
    const requestedCity = params.get("city");
    if (lenses.some((item) => item.id === requestedItem)) state.selectedItemId = requestedItem;
    if (data.cities.some((city) => city.id === requestedCity)) state.selectedCityId = requestedCity;
    state.urlSelectionApplied = true;
  }
  if (!lenses.some((item) => item.id === state.selectedItemId)) state.selectedItemId = OVERALL_ID;
  if (!data.cities.some((city) => city.id === state.selectedCityId)) state.selectedCityId = data.cities[0]?.id;

  setText("#header-previous-year", data.previous_year);
  setText("#header-current-year", data.current_year);
  setText("#previous-year-label", data.previous_year);
  setText("#current-year-label", data.current_year);
  setText("#receipt-current-year", `${data.current_year} · LIVE`);
  setText("#receipt-previous-year", `${data.previous_year} · ARCHIVED`);
  setText("#active-item-count", active.length);
  setText("#city-count", data.snapshot?.city_count || data.cities.length);
  setText("#observation-count", data.snapshot?.observation_count || 0);
  setText("#provider-mode", data.modes.price_provider);
  setText("#last-sync", formatDate(data.snapshot?.retrieved_at));
  setText("#current-source", data.modes.price_provider);
  setText("#trace-id", data.snapshot?.trace_id ? data.snapshot.trace_id.slice(0, 16).toUpperCase() : "NO TRACE");
  renderItemList(lenses);
  renderMap();
  renderInspector();
  renderFactory();
}

function renderItemList(items) {
  const list = $("#item-list");
  list.replaceChildren();
  items.forEach((item, index) => {
    const comparisons = itemComparisons(item.id);
    const annualMedian = median(comparisons.map((row) => row.change_pct));
    const button = document.createElement("button");
    button.type = "button";
    button.className = `item-button${item.id === state.selectedItemId ? " active" : ""}${item.id === OVERALL_ID ? " overall" : ""}`;
    const visual = itemVisual(item);
    const icon = document.createElement("span");
    icon.className = "item-icon";
    icon.textContent = visual.icon;
    icon.dataset.index = String(index + 1).padStart(2, "0");
    icon.setAttribute("aria-hidden", "true");
    const copy = document.createElement("span");
    copy.className = "item-copy";
    const name = document.createElement("b");
    name.textContent = item.name;
    const unit = document.createElement("small");
    unit.textContent = item.id === OVERALL_ID
      ? `DERIVED INDEX · ${activeItems().length} ITEMS`
      : `${item.category} · ${item.unit}`;
    copy.append(name, unit);
    const change = document.createElement("span");
    change.className = `item-change${annualMedian != null && annualMedian < 0 ? " down" : ""}`;
    change.textContent = annualMedian == null ? "—" : `${annualMedian >= 0 ? "+" : ""}${annualMedian.toFixed(1)}%`;
    const cities = document.createElement("small");
    cities.textContent = `${comparisons.length} CITIES`;
    change.append(cities);
    button.append(icon, copy, change);
    button.addEventListener("click", () => selectItem(item.id));
    list.append(button);
  });
}

function selectItem(itemId) {
  state.selectedItemId = itemId;
  const comparisons = itemComparisons(itemId);
  if (!comparisons.some((row) => row.city.id === state.selectedCityId)) state.selectedCityId = comparisons[0]?.city.id || state.selectedCityId;
  updateShareableUrl();
  renderDashboard();
}

function selectCity(cityId, fly = false) {
  state.selectedCityId = cityId;
  updateShareableUrl();
  if (fly) {
    const city = state.dashboard.cities.find((row) => row.id === cityId);
    if (city) map.flyTo([city.latitude, city.longitude], 5.4, {duration: .7});
  }
  renderMap();
  renderInspector();
}

function fitUnitedStates() {
  map.flyTo([39.2, -98.2], overviewZoom, {duration: .7});
}

function resetMapLayout(center = L.latLng(39.2, -98.2), zoom = overviewZoom) {
  map.invalidateSize({pan: false});
  map.setView(center, zoom, {animate: false});
}

function renderMap() {
  state.markers.clearLayers();
  const item = selectedItem();
  const comparisons = itemComparisons();
  const visual = itemVisual(item);
  const overall = isOverall();
  setText("#map-eyebrow", overall ? "DERIVED CITY BASKET · NOT OFFICIAL CPI" : "ITEM-LEVEL INFLATION · OBSERVED USD");
  setText("#map-item-name", item?.name || "NO ITEM SELECTED");
  setText("#map-item-icon", visual.icon);
  setText("#map-item-unit", overall ? `EQUAL-WEIGHT BASKET · ${activeItems().length} ITEMS` : item?.unit || "—");
  const annualMedian = median(comparisons.map((row) => row.change_pct));
  setText("#map-median", annualMedian == null ? "NO COMPARISON" : `${annualMedian >= 0 ? "+" : ""}${annualMedian.toFixed(1)}%`);
  setText("#map-median-label", overall ? "median city basket inflation" : "median annual change");
  setText("#legend-high", overall ? "HIGHEST INFLATION" : "MOST EXPENSIVE");
  setText("#legend-mid", "MID RANGE");
  setText("#legend-low", overall ? "LOWEST INFLATION" : "LEAST EXPENSIVE");

  comparisons.forEach((row, index) => {
    const selected = row.city.id === state.selectedCityId;
    const tier = priceTier(row, comparisons);
    const directionClass = row.direction === "DOWN" ? "down" : row.direction === "UP" ? "up" : "flat";
    const markerValue = overall ? `${row.change_pct >= 0 ? "+" : ""}${row.change_pct.toFixed(1)}%` : markerCurrency(row.current_price_usd);
    const markerChange = overall ? `${row.item_count} ITEM BASKET` : `${row.change_pct >= 0 ? "↑" : "↓"} ${Math.abs(row.change_pct).toFixed(1)}%`;
    const html = `<div class="price-marker tier-${tier} ${directionClass}${selected ? " selected" : ""}" style="animation-delay:${index * 28}ms"><span class="marker-item-icon" aria-hidden="true">${visual.icon}</span><span class="marker-value">${markerValue}</span><b class="marker-city">${row.city.name.toUpperCase()}</b><em class="marker-change">${markerChange}</em></div>`;
    const marker = L.marker([row.city.latitude, row.city.longitude], {
      icon: L.divIcon({className: "price-div-icon", html, iconSize: [104, 72], iconAnchor: [52, 36]}),
      keyboard: true,
      riseOnHover: true,
      zIndexOffset: selected ? 1000 : 0,
      title: overall
        ? `${row.city.name}: ${row.change_pct}% overall basket inflation, ${row.item_count} items`
        : `${row.city.name}: ${currency(row.current_price_usd)}, ${tierLabel(tier, false).toLowerCase()}, ${row.change_pct}% year over year`,
    });
    marker.on("click", () => selectCity(row.city.id, true));
    marker.addTo(state.markers);
  });
  if (!state.hasFitMap && comparisons.length) {
    state.hasFitMap = true;
    setTimeout(() => resetMapLayout(), 80);
    setTimeout(() => resetMapLayout(), 700);
  }
}

function renderInspector() {
  const item = selectedItem();
  const comparison = selectedComparison();
  if (!item || !comparison) {
    setText("#city-name", "NO DATA");
    setText("#current-price", "—");
    setText("#previous-price", "—");
    setText("#dollar-change", "—");
    setText("#selected-unit", item?.unit || "—");
    $("#ranking-list").replaceChildren();
    return;
  }
  state.selectedCityId = comparison.city.id;
  const tier = priceTier(comparison);
  const overall = isOverall();
  setText("#city-name", `${comparison.city.name}, ${comparison.city.state}`);
  setText("#current-year-label", overall ? `${comparison.current_year} OVERALL INFLATION` : comparison.current_year);
  setText("#previous-year-label", overall ? `${comparison.previous_year} INDEX` : comparison.previous_year);
  setText("#current-price", overall ? `${comparison.change_pct >= 0 ? "+" : ""}${comparison.change_pct.toFixed(1)}%` : currency(comparison.current_price_usd));
  setText("#previous-price", overall ? comparison.previous_index.toFixed(1) : currency(comparison.previous_price_usd));
  setText("#change-label", overall ? `${comparison.current_year} INDEX` : "CHANGE");
  setText("#dollar-change", overall ? comparison.current_index.toFixed(1) : `${comparison.change_usd >= 0 ? "+" : "−"}${currency(Math.abs(comparison.change_usd))}`);
  setText("#selected-unit", overall ? `EQUAL-WEIGHT BASKET · ${comparison.item_count} ITEMS` : item.unit);
  setText("#inspector-item-icon", itemVisual(item).icon);
  setText("#price-tier-label", tierLabel(tier, overall));
  $(".price-hero").dataset.tier = tier;
  const badge = $("#change-badge");
  badge.dataset.direction = overall ? "FLAT" : comparison.direction;
  badge.textContent = overall ? `${comparison.item_count} ITEMS` : `${comparison.change_pct >= 0 ? "↑ " : "↓ "}${Math.abs(comparison.change_pct).toFixed(1)}%`;
  renderRankings();
  loadReceipts(comparison, item);
}

function renderRankings() {
  const comparisons = [...itemComparisons()].sort((a, b) => b.current_price_usd - a.current_price_usd);
  const maximum = Math.max(...comparisons.map((row) => row.current_price_usd), 1);
  const minimum = Math.min(...comparisons.map((row) => row.current_price_usd), maximum);
  const overall = isOverall();
  setText("#ranking-context", overall ? "HIGHEST INFLATION FIRST" : "HIGHEST PRICE FIRST");
  const list = $("#ranking-list");
  list.replaceChildren();
  comparisons.forEach((row, index) => {
    const tier = priceTier(row, comparisons);
    const button = document.createElement("button");
    button.type = "button";
    button.className = `rank-row${row.city.id === state.selectedCityId ? " active" : ""}`;
    button.dataset.tier = tier;
    const rank = document.createElement("span");
    rank.textContent = String(index + 1).padStart(2, "0");
    const name = document.createElement("b");
    name.textContent = row.city.name;
    const bar = document.createElement("span");
    bar.className = "rank-bar";
    const fill = document.createElement("i");
    fill.dataset.tier = tier;
    fill.style.width = overall
      ? `${maximum === minimum ? 55 : 18 + (row.current_price_usd - minimum) / (maximum - minimum) * 82}%`
      : `${Math.max(row.current_price_usd / maximum * 100, 4)}%`;
    bar.append(fill);
    const price = document.createElement("em");
    price.textContent = overall ? `${row.change_pct >= 0 ? "+" : ""}${row.change_pct.toFixed(1)}%` : markerCurrency(row.current_price_usd);
    button.append(rank, name, bar, price);
    button.addEventListener("click", () => selectCity(row.city.id, true));
    list.append(button);
  });
}

async function loadReceipts(comparison, item) {
  const requestId = ++state.receiptRequest;
  try {
    const overall = isOverall(item.id);
    const itemQuery = overall ? "" : `&item_id=${encodeURIComponent(item.id)}`;
    const observations = await api(`/api/snapshots/${state.dashboard.snapshot.id}/observations?city_id=${encodeURIComponent(comparison.city.id)}${itemQuery}`);
    if (requestId !== state.receiptRequest) return;
    const currentRows = observations.filter((row) => row.year === state.dashboard.current_year);
    const previousRows = observations.filter((row) => row.year === state.dashboard.previous_year);
    const current = currentRows[0];
    const previous = previousRows[0];
    $("#current-receipt").href = current?.source_url || "#";
    $("#archive-receipt").href = previous?.source_url || "#";
    setText("#receipt-count", `${observations.length} OBSERVATIONS`);
    setText("#receipt-current-title", overall ? `${currentRows.length} LIVE ITEM ROWS` : "LIVE CITY PRICE TABLE");
    setText("#receipt-previous-title", overall ? `${previousRows.length} ARCHIVED ITEM ROWS` : "ARCHIVED CITY PRICE TABLE");
    if (overall) {
      setText("#raw-source-note", `Equal-weight geometric index from ${comparison.item_count} item price relatives. Every item has the same influence; this derived basket is not official CPI.`);
    } else {
      const currentDetail = current ? `${current.raw_label} · raw ${currency(current.raw_price)} × ${current.conversion_multiplier}` : "Current source row unavailable.";
      const previousDetail = previous ? `${previous.raw_label} · raw ${currency(previous.raw_price)} × ${previous.conversion_multiplier}` : "Archived source row unavailable.";
      setText("#raw-source-note", `${currentDetail}. ${previousDetail}.`);
    }
  } catch (error) {
    setText("#raw-source-note", `Receipt lookup unavailable: ${error.message}`);
  }
}

function openFactory() {
  $("#factory-drawer").classList.add("open");
  $("#factory-drawer").setAttribute("aria-hidden", "false");
  renderFactory();
}

function closeFactory() {
  $("#factory-drawer").classList.remove("open");
  $("#factory-drawer").setAttribute("aria-hidden", "true");
}

function normalized(value) {
  return String(value).toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
}

function renderFactory() {
  const data = state.dashboard;
  if (!data) return;
  const active = data.items.filter((item) => item.status === "ACTIVE");
  const retired = data.items.filter((item) => item.status === "RETIRED");
  setText("#factory-active", active.length);
  setText("#factory-retired", retired.length);
  setText("#factory-source-count", data.source_catalog.length);
  setText("#factory-port-mode", data.modes.port);

  const tracked = new Set(data.items.flatMap((item) => item.match_terms.map(normalized)));
  const available = data.source_catalog.filter((row) => !tracked.has(normalized(row.label))).sort((a, b) => a.label.localeCompare(b.label));
  const select = $("#source-label-select");
  const previousValue = select.value;
  select.replaceChildren();
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = available.length ? "SELECT A DISCOVERED PRICE ROW" : "SYNC PRICES TO DISCOVER SOURCE ROWS";
  select.append(placeholder);
  available.forEach((row) => {
    const option = document.createElement("option");
    option.value = row.label;
    option.textContent = `${row.label.toUpperCase()} · ${currency(row.example_price_usd)}`;
    select.append(option);
  });
  if ([...select.options].some((option) => option.value === previousValue)) select.value = previousValue;

  const inventory = $("#factory-item-list");
  inventory.replaceChildren();
  [...data.items].sort((a, b) => a.status.localeCompare(b.status) || a.name.localeCompare(b.name)).forEach((item) => {
    const row = document.createElement("div");
    row.className = "inventory-row";
    row.dataset.status = item.status;
    const copy = document.createElement("div");
    const name = document.createElement("b");
    name.textContent = `${itemVisual(item).icon}  ${item.name}`;
    const detail = document.createElement("small");
    detail.textContent = `${item.category} · ${item.unit} · V${item.version}`;
    copy.append(name, detail);
    const status = document.createElement("span");
    status.textContent = item.status;
    const action = document.createElement("button");
    action.type = "button";
    action.textContent = item.status === "ACTIVE" ? "RETIRE" : "RESTORE";
    action.addEventListener("click", () => toggleItem(item));
    row.append(copy, status, action);
    inventory.append(row);
  });
}

async function createItem(event) {
  event.preventDefault();
  const button = $("#create-item");
  button.disabled = true;
  const payload = Object.fromEntries(new FormData(event.currentTarget).entries());
  payload.conversion_multiplier = Number(payload.conversion_multiplier);
  try {
    const item = await api("/api/items", {method: "POST", body: JSON.stringify(payload)});
    state.selectedItemId = item.id;
    toast(`${item.name} passed its source contract. Collecting it across every city now.`);
    event.currentTarget.reset();
    event.currentTarget.querySelector('[name="conversion_multiplier"]').value = "1";
    closeFactory();
    await syncPrices(false, "COLLECTING THE NEW ITEM", `${item.name} · current and archived city observations`);
  } catch (error) {
    toast(error.message);
  } finally {
    button.disabled = false;
  }
}

async function toggleItem(item) {
  try {
    if (item.status === "ACTIVE") {
      await api(`/api/items/${item.id}?actor=inflation-research-lead`, {method: "DELETE"});
      toast(`${item.name} retired. Its historical observations were preserved.`);
    } else {
      await api(`/api/items/${item.id}/restore?actor=inflation-research-lead`, {method: "POST"});
      toast(`${item.name} restored. Run a live sync to refresh it.`);
    }
    await loadDashboard(false, true);
  } catch (error) {
    toast(error.message);
  }
}

function setLoading(visible, title = "READING THE REAL WORLD", detail = "Current city pages → archived pages → normalized comparisons") {
  $("#loading-layer").hidden = !visible;
  setText("#loading-title", title);
  setText("#loading-detail", detail);
  $("#sync-prices").disabled = visible;
  $("#sync-prices").classList.toggle("syncing", visible);
}

async function syncPrices(initial = false, title, detail) {
  setLoading(true, title, detail);
  try {
    const snapshot = await api("/api/prices/sync", {method: "POST"});
    await loadDashboard(false, true);
    toast(`${snapshot.comparison_count} real city-item comparisons verified across ${snapshot.city_count} cities.`);
  } catch (error) {
    toast(error.message);
    if (initial) setText("#map-item-name", "LIVE SYNC UNAVAILABLE");
  } finally {
    setLoading(false);
  }
}

async function loadDashboard(autoSync = true, fresh = false) {
  try {
    state.dashboard = await api("/api/dashboard", fresh ? {cache: "no-store"} : {});
    renderDashboard();
    if (!state.dashboard.snapshot && autoSync) await syncPrices(true);
  } catch (error) {
    toast(`InflationForge unavailable: ${error.message}`);
  }
}

$("#sync-prices").addEventListener("click", () => syncPrices(false));
$("#open-factory").addEventListener("click", openFactory);
$("#rail-add-item").addEventListener("click", openFactory);
$$('[data-close-factory]').forEach((element) => element.addEventListener("click", closeFactory));
$("#item-form").addEventListener("submit", createItem);
$("#reset-map").addEventListener("click", fitUnitedStates);
$("#source-label-select").addEventListener("change", (event) => {
  const form = $("#item-form");
  const label = event.target.value;
  if (!label) return;
  const clean = label.replace(/\s*\([^)]*\)\s*/g, " ").replace(/\s+/g, " ").trim();
  if (!form.elements.name.value) form.elements.name.value = clean.slice(0, 80);
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeFactory();
});
let mapResizeTimer;
function scheduleMapLayoutReset() {
  clearTimeout(mapResizeTimer);
  const center = map.getCenter();
  const zoom = map.getZoom();
  mapResizeTimer = setTimeout(() => resetMapLayout(center, zoom), 100);
}
window.addEventListener("resize", scheduleMapLayoutReset);
if (window.ResizeObserver) new ResizeObserver(scheduleMapLayoutReset).observe($("#map"));

if (window.location.hash === "#factory") openFactory();
loadRuntime();
loadDashboard(true);
