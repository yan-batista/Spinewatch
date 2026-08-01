// ---------- low-level fetch helpers ----------

async function apiFetch(path, { method = "GET", body } = {}) {
  const headers = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (API_KEY) headers["X-API-Key"] = API_KEY;

  const response = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (!response.ok) {
    if (response.status === 401) {
      throw new Error("unauthorized — check API key in config.js");
    }
    let detail = `HTTP ${response.status}`;
    try {
      const errBody = await response.json();
      if (errBody && errBody.detail) detail = errBody.detail;
    } catch {
      // non-JSON error body -- keep the generic message
    }
    throw new Error(detail);
  }

  if (response.status === 204) return null;
  return response.json();
}

function setStatus(message, kind = "ok") {
  const el = document.getElementById("status");
  el.textContent = message;
  el.className = message ? kind : "";
}

function formatPrice(priceCents, currency) {
  if (priceCents === null || priceCents === undefined) return null;
  return `${currency || ""} ${(priceCents / 100).toFixed(2)}`.trim();
}

// ---------- view switching ----------

function showView(name) {
  for (const section of document.querySelectorAll(".view")) {
    section.classList.toggle("hidden", section.id !== `view-${name}`);
  }
  for (const btn of document.querySelectorAll(".nav-btn")) {
    if (btn.dataset.view === name) {
      btn.setAttribute("aria-current", "page");
    } else {
      btn.removeAttribute("aria-current");
    }
  }
  if (name === "stores") loadStores();
}

// ---------- dashboard ----------

let dashboardData = [];

async function loadDashboard() {
  const container = document.getElementById("book-cards");
  try {
    dashboardData = await apiFetch("/dashboard");
    renderDashboard();
    populateDetailBookSelect();
    // A book deleted elsewhere (e.g. from its dashboard card) shouldn't
    // leave a stale detail pane pointing at an id that no longer exists.
    if (currentBookId && !dashboardData.some((b) => b.id === currentBookId)) {
      document.getElementById("detail-book-select").value = "";
      await selectBookForDetail(null);
    }
  } catch (err) {
    container.innerHTML = "";
    container.appendChild(emptyState(`Could not load dashboard: ${err.message}`));
  }
}

function emptyState(text) {
  const p = document.createElement("p");
  p.className = "empty-state";
  p.textContent = text;
  return p;
}

function renderDashboard() {
  const container = document.getElementById("book-cards");
  container.innerHTML = "";

  if (dashboardData.length === 0) {
    container.appendChild(emptyState("No books tracked yet. Add one above."));
    return;
  }

  for (const book of dashboardData) {
    container.appendChild(buildBookCard(book));
  }
}

function buildBookCard(book) {
  const card = document.createElement("div");
  card.className = "book-card" + (book.active ? "" : " inactive");

  const header = document.createElement("div");
  header.className = "book-card-header";

  const title = document.createElement("div");
  title.className = "book-card-title";
  title.textContent = book.title || book.isbn13 || `Book #${book.id}`;
  header.appendChild(title);

  const badge = document.createElement("span");
  badge.className = "badge" + (book.active ? " active" : "");
  badge.textContent = book.active ? "active" : "disabled";
  header.appendChild(badge);

  card.appendChild(header);

  if (book.isbn13) {
    const isbn = document.createElement("p");
    isbn.className = "muted";
    isbn.textContent = book.isbn13;
    card.appendChild(isbn);
  }

  const listings = document.createElement("div");
  listings.className = "book-card-listings";
  if (!book.listings || book.listings.length === 0) {
    listings.appendChild(emptyState("No store listings linked."));
  } else {
    for (const listing of book.listings) {
      listings.appendChild(buildListingSummaryRow(listing));
    }
  }
  card.appendChild(listings);

  const actions = document.createElement("div");
  actions.className = "book-card-actions";

  const viewBtn = document.createElement("button");
  viewBtn.type = "button";
  viewBtn.textContent = "View details";
  viewBtn.addEventListener("click", () => {
    showView("detail");
    document.getElementById("detail-book-select").value = String(book.id);
    selectBookForDetail(book.id);
  });
  actions.appendChild(viewBtn);

  const toggleBtn = document.createElement("button");
  toggleBtn.type = "button";
  toggleBtn.textContent = book.active ? "Disable" : "Enable";
  toggleBtn.addEventListener("click", () => setBookActive(book.id, !book.active));
  actions.appendChild(toggleBtn);

  const deleteBtn = document.createElement("button");
  deleteBtn.type = "button";
  deleteBtn.className = "danger";
  deleteBtn.textContent = "Delete";
  deleteBtn.addEventListener("click", () => deleteBook(book.id, title.textContent));
  actions.appendChild(deleteBtn);

  card.appendChild(actions);
  return card;
}

function buildListingSummaryRow(listing) {
  const row = document.createElement("div");
  row.className = "listing-row";

  const store = document.createElement("span");
  store.textContent = listing.store_slug + (listing.active ? "" : " (disabled)");
  row.appendChild(store);

  const value = document.createElement("span");
  if (listing.status && listing.status !== "ok") {
    value.className = `status-text status-${listing.status}`;
    value.textContent = listing.status;
  } else {
    const price = formatPrice(listing.price_cents, listing.currency);
    value.className = "price";
    value.textContent = price ?? "—";
  }
  row.appendChild(value);

  return row;
}

async function setBookActive(bookId, active) {
  setStatus(active ? "Enabling book…" : "Disabling book…");
  try {
    await apiFetch(`/books/${bookId}`, { method: "PATCH", body: { active } });
    setStatus("");
    await loadDashboard();
  } catch (err) {
    setStatus(`Could not update book: ${err.message}`, "error");
  }
}

async function deleteBook(bookId, label) {
  if (!confirm(`Delete "${label}" and all its listings/history? This can't be undone.`)) return;
  setStatus("Deleting book…");
  try {
    await apiFetch(`/books/${bookId}`, { method: "DELETE" });
    setStatus("");
    await loadDashboard();
  } catch (err) {
    setStatus(`Could not delete book: ${err.message}`, "error");
  }
}

async function onAddBookSubmit(event) {
  event.preventDefault();
  const form = event.target;
  const data = Object.fromEntries(new FormData(form).entries());
  const body = {};
  for (const key of ["title", "alt_title", "isbn", "author"]) {
    const value = (data[key] || "").trim();
    if (value) body[key] = value;
  }
  if (!body.title && !body.isbn) {
    setStatus("Enter at least a title or an ISBN.", "error");
    return;
  }

  setStatus("Adding book…");
  try {
    await apiFetch("/books", { method: "POST", body });
    form.reset();
    document.getElementById("add-book-details").open = false;
    setStatus("Book added.");
    await loadDashboard();
  } catch (err) {
    setStatus(`Could not add book: ${err.message}`, "error");
  }
}

// ---------- book detail ----------

let currentBookId = null;
let currentListings = [];

function populateDetailBookSelect() {
  const select = document.getElementById("detail-book-select");
  const previous = select.value;
  select.innerHTML = '<option value="">Select a book…</option>';
  for (const book of dashboardData) {
    const option = document.createElement("option");
    option.value = book.id;
    option.textContent = book.title || book.isbn13 || `Book #${book.id}`;
    select.appendChild(option);
  }
  if (previous && dashboardData.some((b) => String(b.id) === previous)) {
    select.value = previous;
  }
}

async function selectBookForDetail(bookId) {
  currentBookId = bookId ? Number(bookId) : null;
  const emptyEl = document.getElementById("detail-empty");
  const contentEl = document.getElementById("detail-content");

  if (!currentBookId) {
    emptyEl.classList.remove("hidden");
    contentEl.classList.add("hidden");
    return;
  }

  emptyEl.classList.add("hidden");
  contentEl.classList.remove("hidden");

  const book = dashboardData.find((b) => b.id === currentBookId);
  document.getElementById("detail-title").textContent =
    (book && (book.title || book.isbn13)) || `Book #${currentBookId}`;
  document.getElementById("detail-isbn").textContent = book && book.isbn13 ? book.isbn13 : "";
  const activeToggle = document.getElementById("detail-active-toggle");
  activeToggle.checked = !!(book && book.active);

  await loadListings();
  await loadHistory();
}

async function loadListings() {
  const body = document.getElementById("listings-body");
  const storeSelect = document.getElementById("store-select");
  body.innerHTML = "";
  try {
    currentListings = await apiFetch(`/books/${currentBookId}/listings`);
    renderListings();
    populateStoreSelect(storeSelect, currentListings);
  } catch (err) {
    setStatus(`Could not load listings: ${err.message}`, "error");
  }
}

function renderListings() {
  const body = document.getElementById("listings-body");
  body.innerHTML = "";

  if (currentListings.length === 0) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 4;
    cell.className = "empty-state";
    cell.textContent = "No store listings linked yet.";
    row.appendChild(cell);
    body.appendChild(row);
    return;
  }

  for (const listing of currentListings) {
    const row = document.createElement("tr");

    const storeCell = document.createElement("td");
    storeCell.textContent = listing.store_slug;
    row.appendChild(storeCell);

    const urlCell = document.createElement("td");
    urlCell.className = "url-cell";
    const link = document.createElement("a");
    link.href = listing.url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = listing.url;
    urlCell.appendChild(link);
    row.appendChild(urlCell);

    const activeCell = document.createElement("td");
    activeCell.textContent = listing.active ? "yes" : "no";
    row.appendChild(activeCell);

    const actionCell = document.createElement("td");
    const toggleBtn = document.createElement("button");
    toggleBtn.type = "button";
    toggleBtn.textContent = listing.active ? "Unlink" : "Re-link";
    toggleBtn.addEventListener("click", () => setListingActive(listing.id, !listing.active));
    actionCell.appendChild(toggleBtn);
    row.appendChild(actionCell);

    body.appendChild(row);
  }
}

async function setListingActive(listingId, active) {
  setStatus(active ? "Re-linking listing…" : "Unlinking listing…");
  try {
    await apiFetch(`/books/${currentBookId}/listings/${listingId}`, {
      method: "PATCH",
      body: { active },
    });
    setStatus("");
    await loadListings();
    await loadHistory();
  } catch (err) {
    setStatus(`Could not update listing: ${err.message}`, "error");
  }
}

async function onAddListingSubmit(event) {
  event.preventDefault();
  if (!currentBookId) return;
  const form = event.target;
  const url = new FormData(form).get("url").trim();
  if (!url) return;

  setStatus("Adding listing…");
  try {
    await apiFetch(`/books/${currentBookId}/listings`, { method: "POST", body: { url } });
    form.reset();
    document.getElementById("add-listing-details").open = false;
    setStatus("Listing added.");
    await loadListings();
    await loadHistory();
  } catch (err) {
    setStatus(`Could not add listing: ${err.message}`, "error");
  }
}

async function onDetailActiveToggle(event) {
  if (!currentBookId) return;
  await setBookActive(currentBookId, event.target.checked);
  const book = dashboardData.find((b) => b.id === currentBookId);
  if (book) event.target.checked = book.active;
}

async function onDetailDelete() {
  if (!currentBookId) return;
  const title = document.getElementById("detail-title").textContent;
  if (!confirm(`Delete "${title}" and all its listings/history? This can't be undone.`)) return;
  setStatus("Deleting book…");
  try {
    await apiFetch(`/books/${currentBookId}`, { method: "DELETE" });
    setStatus("");
    currentBookId = null;
    await loadDashboard();
    document.getElementById("detail-book-select").value = "";
    await selectBookForDetail(null);
  } catch (err) {
    setStatus(`Could not delete book: ${err.message}`, "error");
  }
}

function populateStoreSelect(select, listings) {
  const previous = select.value;
  select.innerHTML = '<option value="">All stores</option>';
  const seen = new Set();
  for (const listing of listings) {
    if (seen.has(listing.store_slug)) continue;
    seen.add(listing.store_slug);
    const option = document.createElement("option");
    option.value = listing.store_slug;
    option.textContent = listing.store_slug;
    select.appendChild(option);
  }
  if (seen.has(previous)) select.value = previous;
}

function renderHistory(rows) {
  const body = document.getElementById("history-body");
  body.innerHTML = "";

  if (rows.length === 0) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 4;
    cell.className = "empty-state";
    cell.textContent = "No observations for this selection.";
    row.appendChild(cell);
    body.appendChild(row);
    return;
  }

  for (const obs of rows) {
    const row = document.createElement("tr");
    const price = formatPrice(obs.price_cents, obs.currency);

    const dateCell = document.createElement("td");
    dateCell.textContent = obs.observed_on;
    row.appendChild(dateCell);

    const storeCell = document.createElement("td");
    storeCell.textContent = obs.store_slug;
    row.appendChild(storeCell);

    const priceCell = document.createElement("td");
    priceCell.className = "num";
    priceCell.textContent = price ?? "—";
    row.appendChild(priceCell);

    const statusCell = document.createElement("td");
    if (obs.status !== "ok") statusCell.className = `status-text status-${obs.status}`;
    statusCell.textContent = obs.status;
    row.appendChild(statusCell);

    body.appendChild(row);
  }
}

async function loadHistory() {
  if (!currentBookId) {
    renderHistory([]);
    renderChart([]);
    return;
  }

  const store = document.getElementById("store-select").value;
  const days = document.getElementById("days-input").value;

  const params = new URLSearchParams();
  if (store) params.set("store", store);
  if (days) params.set("days", days);
  const query = params.toString() ? `?${params.toString()}` : "";

  try {
    const rows = await apiFetch(`/books/${currentBookId}/history${query}`);
    renderHistory(rows);
    renderChart(rows);
  } catch (err) {
    setStatus(`Could not load history: ${err.message}`, "error");
  }
}

// ---------- stores ----------

async function loadStores() {
  const body = document.getElementById("stores-body");
  try {
    const stores = await apiFetch("/stores");
    body.innerHTML = "";
    if (stores.length === 0) {
      const row = document.createElement("tr");
      const cell = document.createElement("td");
      cell.colSpan = 3;
      cell.className = "empty-state";
      cell.textContent = "No stores configured.";
      row.appendChild(cell);
      body.appendChild(row);
      return;
    }
    for (const store of stores) {
      body.appendChild(buildStoreRow(store));
    }
  } catch (err) {
    body.innerHTML = "";
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 3;
    cell.className = "empty-state";
    cell.textContent = `Could not load stores: ${err.message}`;
    row.appendChild(cell);
    body.appendChild(row);
  }
}

function buildStoreRow(store) {
  const row = document.createElement("tr");

  const nameCell = document.createElement("td");
  nameCell.textContent = store.name;
  row.appendChild(nameCell);

  const slugCell = document.createElement("td");
  slugCell.textContent = store.slug;
  row.appendChild(slugCell);

  const toggleCell = document.createElement("td");
  const label = document.createElement("label");
  label.className = "switch";
  const checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  checkbox.checked = store.enabled;
  checkbox.addEventListener("change", () => setStoreEnabled(store.slug, checkbox.checked, checkbox));
  label.appendChild(checkbox);
  label.appendChild(document.createTextNode("Enabled"));
  toggleCell.appendChild(label);
  row.appendChild(toggleCell);

  return row;
}

async function setStoreEnabled(slug, enabled, checkbox) {
  setStatus(enabled ? `Enabling ${slug}…` : `Disabling ${slug}…`);
  try {
    await apiFetch(`/stores/${slug}`, { method: "PATCH", body: { enabled } });
    setStatus("");
  } catch (err) {
    checkbox.checked = !enabled;
    setStatus(`Could not update store: ${err.message}`, "error");
  }
}

// ---------- chart (hand-rolled inline SVG, no charting library) ----------

const SVGNS = "http://www.w3.org/2000/svg";
const SERIES_COLOR_VARS = [
  "--series-1", "--series-2", "--series-3", "--series-4",
  "--series-5", "--series-6", "--series-7", "--series-8",
];

function svgEl(tag, attrs = {}) {
  const el = document.createElementNS(SVGNS, tag);
  for (const [key, value] of Object.entries(attrs)) el.setAttribute(key, value);
  return el;
}

// "Nice" tick step so y-axis labels land on round numbers.
function niceStep(roughStep) {
  const magnitude = 10 ** Math.floor(Math.log10(roughStep || 1));
  const residual = roughStep / magnitude;
  let step;
  if (residual <= 1) step = 1;
  else if (residual <= 2) step = 2;
  else if (residual <= 5) step = 5;
  else step = 10;
  return step * magnitude;
}

function renderChart(rows) {
  const container = document.getElementById("chart-container");
  container.innerHTML = "";

  const series = new Map(); // store_slug -> [{date: Date, iso, price, currency}]
  for (const row of rows) {
    if (row.status !== "ok" || row.price_cents == null) continue;
    const list = series.get(row.store_slug) || [];
    list.push({
      date: new Date(row.observed_on),
      iso: row.observed_on,
      price: row.price_cents / 100,
      currency: row.currency,
    });
    series.set(row.store_slug, list);
  }
  for (const list of series.values()) list.sort((a, b) => a.date - b.date);

  if (series.size === 0) {
    container.appendChild(emptyStateChart("No priced observations to chart for this selection."));
    return;
  }

  const width = 720;
  const height = 300;
  const showLegend = series.size > 1;
  const showEndLabels = series.size <= 4;
  const padding = {
    top: 16,
    right: showEndLabels ? 84 : 16,
    bottom: 30,
    left: 60,
  };
  const plotW = width - padding.left - padding.right;
  const plotH = height - padding.top - padding.bottom;

  const storeNames = [...series.keys()];
  const colorFor = (slug) => {
    const idx = storeNames.indexOf(slug);
    return idx < SERIES_COLOR_VARS.length
      ? `var(${SERIES_COLOR_VARS[idx]})`
      : "var(--series-other)";
  };

  const allPoints = [...series.values()].flat();
  const allDates = [...new Set(rows.filter((r) => r.status === "ok" && r.price_cents != null).map((r) => r.observed_on))]
    .sort();
  const minTime = Math.min(...allPoints.map((p) => p.date.getTime()));
  const maxTime = Math.max(...allPoints.map((p) => p.date.getTime()));
  const rawMinPrice = Math.min(...allPoints.map((p) => p.price));
  const rawMaxPrice = Math.max(...allPoints.map((p) => p.price));
  const step = niceStep((rawMaxPrice - rawMinPrice) / 4 || rawMaxPrice / 4 || 1);
  const minPrice = Math.max(0, Math.floor(rawMinPrice / step) * step - (rawMinPrice === rawMaxPrice ? step : 0));
  const maxPrice = Math.ceil(rawMaxPrice / step) * step + step;
  const currency = allPoints[0].currency || "";

  const xFor = (time) =>
    padding.left + (maxTime === minTime ? plotW / 2 : ((time - minTime) / (maxTime - minTime)) * plotW);
  const yFor = (price) =>
    padding.top + plotH - ((price - minPrice) / (maxPrice - minPrice || 1)) * plotH;

  const svg = svgEl("svg", {
    viewBox: `0 0 ${width} ${height}`,
    role: "img",
    "aria-label": "Price over time by store. Use arrow keys to step through dates once focused.",
    tabindex: "0",
  });
  // Attach immediately (not after building it) -- getBBox() below needs a
  // live, rendered DOM, and Firefox throws on a detached SVG element.
  container.appendChild(svg);

  // gridlines + y-axis ticks
  const tickCount = Math.round((maxPrice - minPrice) / step);
  for (let i = 0; i <= tickCount; i++) {
    const value = minPrice + i * step;
    const y = yFor(value);
    svg.appendChild(
      svgEl("line", {
        x1: padding.left, x2: width - padding.right, y1: y, y2: y,
        stroke: "var(--line)", "stroke-width": 1,
      })
    );
    const label = svgEl("text", {
      x: padding.left - 8, y: y + 3, "text-anchor": "end",
      fill: "var(--ink-muted)", "font-size": 10,
    });
    label.textContent = value.toFixed(step < 1 ? 2 : 0);
    svg.appendChild(label);
  }

  // x-axis: first and last date only, to stay legible
  for (const time of [minTime, maxTime]) {
    const x = xFor(time);
    const label = svgEl("text", {
      x, y: height - 8,
      "text-anchor": time === minTime ? "start" : "end",
      fill: "var(--ink-muted)", "font-size": 10,
    });
    label.textContent = new Date(time).toISOString().slice(0, 10);
    svg.appendChild(label);
  }

  // one polyline + end marker per series
  for (const slug of storeNames) {
    const points = series.get(slug);
    const color = colorFor(slug);

    if (points.length > 1) {
      const path = points.map((p) => `${xFor(p.date.getTime())},${yFor(p.price)}`).join(" ");
      svg.appendChild(
        svgEl("polyline", {
          points: path, fill: "none", stroke: color,
          "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round",
        })
      );
    }

    const last = points[points.length - 1];
    for (const p of points) {
      svg.appendChild(
        svgEl("circle", {
          cx: xFor(p.date.getTime()), cy: yFor(p.price), r: 4,
          fill: color, stroke: "var(--surface)", "stroke-width": 2,
        })
      );
    }

    if (showEndLabels) {
      const label = svgEl("text", {
        x: xFor(last.date.getTime()) + 8, y: yFor(last.price) + 3,
        fill: "var(--ink)", "font-size": 11, "font-weight": 600,
      });
      label.textContent = `${currency} ${last.price.toFixed(2)}`.trim();
      svg.appendChild(label);
      // Measure after insertion; if it would clip against the SVG's right
      // edge, drop it and let the legend + tooltip carry the value instead.
      if (label.getBBox().x + label.getBBox().width > width - 4) {
        label.remove();
      }
    }
  }

  // crosshair (hidden until hover/focus)
  const crosshair = svgEl("line", {
    x1: padding.left, x2: padding.left, y1: padding.top, y2: padding.top + plotH,
    stroke: "var(--ink-muted)", "stroke-width": 1, visibility: "hidden",
  });
  svg.appendChild(crosshair);

  // transparent hit-area overlay for pointer interaction
  const overlay = svgEl("rect", {
    x: padding.left, y: padding.top, width: plotW, height: plotH,
    fill: "transparent",
  });
  svg.appendChild(overlay);

  if (showLegend) {
    const legend = document.createElement("div");
    legend.className = "chart-legend";
    for (const slug of storeNames) {
      const item = document.createElement("div");
      item.className = "chart-legend-item";
      const swatch = document.createElement("span");
      swatch.className = "chart-legend-swatch";
      swatch.style.background = colorFor(slug);
      item.appendChild(swatch);
      const text = document.createElement("span");
      text.textContent = slug;
      item.appendChild(text);
      legend.appendChild(item);
    }
    container.appendChild(legend);
  }

  const tooltip = document.createElement("div");
  tooltip.className = "chart-tooltip hidden";
  container.style.position = "relative";
  container.appendChild(tooltip);

  function showTooltipForDate(iso, clientX, clientY) {
    const rowsAtDate = storeNames
      .map((slug) => ({ slug, point: series.get(slug).find((p) => p.iso === iso) }))
      .filter((r) => r.point);
    if (rowsAtDate.length === 0) return;

    tooltip.innerHTML = "";
    const dateLine = document.createElement("div");
    dateLine.className = "chart-tooltip-date";
    dateLine.textContent = iso;
    tooltip.appendChild(dateLine);

    for (const { slug, point } of rowsAtDate) {
      const line = document.createElement("div");
      line.className = "chart-tooltip-row";
      const key = document.createElement("span");
      key.className = "chart-tooltip-key";
      key.style.background = colorFor(slug);
      line.appendChild(key);
      const name = document.createElement("span");
      name.textContent = slug;
      line.appendChild(name);
      const value = document.createElement("span");
      value.className = "chart-tooltip-value";
      value.textContent = `${point.currency || ""} ${point.price.toFixed(2)}`.trim();
      line.appendChild(value);
      tooltip.appendChild(line);
    }

    tooltip.classList.remove("hidden");
    const containerRect = container.getBoundingClientRect();
    tooltip.style.left = `${clientX - containerRect.left + 12}px`;
    tooltip.style.top = `${clientY - containerRect.top - 10}px`;

    const time = new Date(iso).getTime();
    const x = xFor(time);
    crosshair.setAttribute("x1", x);
    crosshair.setAttribute("x2", x);
    crosshair.setAttribute("visibility", "visible");
  }

  function hideTooltip() {
    tooltip.classList.add("hidden");
    crosshair.setAttribute("visibility", "hidden");
  }

  function nearestDateIndexForX(clientX) {
    const rect = svg.getBoundingClientRect();
    const scaleX = width / rect.width;
    const svgX = (clientX - rect.left) * scaleX;
    const time = minTime + ((svgX - padding.left) / plotW) * (maxTime - minTime);
    let bestIdx = 0;
    let bestDiff = Infinity;
    allDates.forEach((iso, idx) => {
      const diff = Math.abs(new Date(iso).getTime() - time);
      if (diff < bestDiff) {
        bestDiff = diff;
        bestIdx = idx;
      }
    });
    return bestIdx;
  }

  overlay.addEventListener("pointermove", (event) => {
    const idx = nearestDateIndexForX(event.clientX);
    showTooltipForDate(allDates[idx], event.clientX, event.clientY);
  });
  overlay.addEventListener("pointerleave", hideTooltip);

  let focusIdx = allDates.length - 1;
  svg.addEventListener("focus", () => {
    const rect = svg.getBoundingClientRect();
    const x = xFor(new Date(allDates[focusIdx]).getTime());
    const scaleX = rect.width / width;
    showTooltipForDate(allDates[focusIdx], rect.left + x * scaleX, rect.top + height / 2);
  });
  svg.addEventListener("keydown", (event) => {
    if (event.key === "ArrowLeft") {
      focusIdx = Math.max(0, focusIdx - 1);
    } else if (event.key === "ArrowRight") {
      focusIdx = Math.min(allDates.length - 1, focusIdx + 1);
    } else if (event.key === "Escape") {
      hideTooltip();
      return;
    } else {
      return;
    }
    event.preventDefault();
    const rect = svg.getBoundingClientRect();
    const x = xFor(new Date(allDates[focusIdx]).getTime());
    const scaleX = rect.width / width;
    showTooltipForDate(allDates[focusIdx], rect.left + x * scaleX, rect.top + height / 2);
  });
  svg.addEventListener("blur", hideTooltip);
}

function emptyStateChart(text) {
  const p = document.createElement("p");
  p.className = "chart-empty";
  p.textContent = text;
  return p;
}

// ---------- init ----------

async function init() {
  for (const btn of document.querySelectorAll(".nav-btn")) {
    btn.addEventListener("click", () => showView(btn.dataset.view));
  }

  document.getElementById("add-book-form").addEventListener("submit", onAddBookSubmit);
  document.getElementById("add-listing-form").addEventListener("submit", onAddListingSubmit);
  document.getElementById("detail-active-toggle").addEventListener("change", onDetailActiveToggle);
  document.getElementById("detail-delete-btn").addEventListener("click", onDetailDelete);

  document.getElementById("detail-book-select").addEventListener("change", (event) => {
    selectBookForDetail(event.target.value);
  });
  document.getElementById("store-select").addEventListener("change", loadHistory);
  document.getElementById("days-input").addEventListener("change", loadHistory);

  await loadDashboard();
}

init().catch((err) => {
  setStatus(`Could not initialize: ${err.message}`, "error");
});
