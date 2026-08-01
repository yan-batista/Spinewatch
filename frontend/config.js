// Points the page at the backend API. Edit this one line to switch
// backends (local dev, staging, production) -- no rebuild needed, since
// this is a static site with no build step.
const API_BASE = "http://127.0.0.1:8000";

// Optional shared-secret sent as `X-API-Key` on every write request
// (POST/PATCH/DELETE). Matches the server-side `SPINEWATCH_API_KEY` env var.
// Leave empty ("") if the operator hasn't configured one -- the header is
// omitted entirely rather than sent blank.
const API_KEY = "";
