// Points the page at the backend API. Edit this one line to switch
// backends (local dev, staging, production) -- no rebuild needed, since
// this is a static site with no build step.
// Local development only -- CI excludes this file from the rsync, so the
// deployed copy on the VM is edited in place and survives deploys. There it
// reads "/api", matching the handle_path prefix in deploy/Caddyfile.
//
// There is deliberately no API key here: anything in this file is served to
// every visitor. Auth is the basic_auth block in deploy/Caddyfile.
const API_BASE = "http://127.0.0.1:8000";
