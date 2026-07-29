async function fetchJSON(path) {
  const response = await fetch(`${API_BASE}${path}`);
  if (!response.ok) {
    throw new Error(`${path} -> HTTP ${response.status}`);
  }
  return response.json();
}

function setStatus(message) {
  document.getElementById("status").textContent = message;
}

async function loadBooks() {
  const select = document.getElementById("book-select");
  try {
    const books = await fetchJSON("/books");
    select.innerHTML = "";
    for (const book of books) {
      const option = document.createElement("option");
      option.value = book.id;
      option.textContent = book.title || book.isbn13;
      select.appendChild(option);
    }
  } catch (err) {
    setStatus(`Could not load books: ${err.message}`);
  }
}

async function loadStoresForBook(bookId) {
  const select = document.getElementById("store-select");
  select.innerHTML = '<option value="">All stores</option>';
  if (!bookId) return;

  const listings = await fetchJSON(`/books/${bookId}/listings`);
  const seen = new Set();
  for (const listing of listings) {
    if (seen.has(listing.store_slug)) continue;
    seen.add(listing.store_slug);
    const option = document.createElement("option");
    option.value = listing.store_slug;
    option.textContent = listing.store_slug;
    select.appendChild(option);
  }
}

function formatPrice(priceCents, currency) {
  if (priceCents === null || priceCents === undefined) return null;
  return `${currency || ""} ${(priceCents / 100).toFixed(2)}`.trim();
}

function renderHistory(rows) {
  const body = document.getElementById("history-body");
  body.innerHTML = "";

  if (rows.length === 0) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 4;
    cell.textContent = "No observations for this selection.";
    row.appendChild(cell);
    body.appendChild(row);
    return;
  }

  for (const obs of rows) {
    const row = document.createElement("tr");
    const price = formatPrice(obs.price_cents, obs.currency);
    const cellValues = [obs.observed_on, obs.store_slug, price ?? "—", obs.status];
    for (const text of cellValues) {
      const cell = document.createElement("td");
      cell.textContent = text;
      row.appendChild(cell);
    }
    body.appendChild(row);
  }
}

async function loadHistory() {
  const bookId = document.getElementById("book-select").value;
  if (!bookId) {
    renderHistory([]);
    return;
  }

  const store = document.getElementById("store-select").value;
  const days = document.getElementById("days-input").value;

  const params = new URLSearchParams();
  if (store) params.set("store", store);
  if (days) params.set("days", days);
  const query = params.toString() ? `?${params.toString()}` : "";

  setStatus("Loading…");
  try {
    const rows = await fetchJSON(`/books/${bookId}/history${query}`);
    renderHistory(rows);
    setStatus("");
  } catch (err) {
    setStatus(`Could not load history: ${err.message}`);
  }
}

async function onBookChange() {
  const bookId = document.getElementById("book-select").value;
  await loadStoresForBook(bookId);
  await loadHistory();
}

async function init() {
  await loadBooks();
  await onBookChange();

  document.getElementById("book-select").addEventListener("change", onBookChange);
  document.getElementById("store-select").addEventListener("change", loadHistory);
  document.getElementById("days-input").addEventListener("change", loadHistory);
}

init();
