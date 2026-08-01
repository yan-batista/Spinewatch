# Deploying spinewatch to a VM

This documents how to run spinewatch's nightly crawl on a single VM (target:
a free-tier box like Oracle Cloud's always-free `VM.Standard.E2.1.Micro` or
Google Cloud's always-free `e2-micro` — both land around 1 OCPU/vCPU and
1GB RAM — but none of this is provider-specific; any small Ubuntu/Debian-family
box works the same way). It does **not** cover provisioning the VM itself
(creating the instance, network/firewall rules) — only what happens once you
can SSH into a box with a fresh OS on it.

On Google Cloud, `e2-micro` only qualifies for the always-free allowance in
`us-west1`, `us-central1`, or `us-east1` — pick one of those regions when
creating the instance, and its default Debian image has SELinux off entirely
(`getenforce` isn't even installed), so the `:z` mount suffix in step 3 below
is a pure no-op there, not load-bearing the way it is on Oracle Linux.

There is no live deployment scripted here. Every step below is something you
run by hand against your own VM.

## 1. Install Docker on the VM

Standard Docker Engine install, nothing exotic:

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker "$USER"
```

Log out and back in (or `newgrp docker`) so your shell picks up the new group
membership. Confirm with:

```bash
docker run --rm hello-world
```

## 2. Add a 2GB swap file

A 1GB VM has no room to absorb a memory spike from the browser-fallback
crawl. Swap doesn't make anything faster — it turns a hard OOM kill (which
loses the entire night's run) into a slow-but-completing run. Cheap
insurance on a box this small:

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```

Persist it across reboots by adding this line to `/etc/fstab`:

```
/swapfile none swap sw 0 0
```

Verify with `free -h` — you should see 2.0G under `Swap`.

## 3. Create the data directory

The crawler's SQLite database is the only state that matters (nothing else
in the container is stateful). Give it a home on the VM's disk, outside the
container, so it survives image rebuilds and container restarts:

```bash
sudo mkdir -p /srv/spinewatch/data
```

Check `getenforce` before you mount this anywhere. On Oracle Linux (the
default OS image behind Oracle Cloud's always-free tier) it commonly reports
`Enforcing`, and SELinux will then block the container from opening anything
under a plain bind mount — every `-v /srv/spinewatch/data:/data` below
needs the `:z` relabel suffix (`-v /srv/spinewatch/data:/data:z`) or the
crawl fails with `OperationalError: unable to open database file`, an error
that reads like a corrupt database but is actually just SELinux denying
access. On Ubuntu/Debian, `getenforce` usually reports `Permissive` or isn't
installed at all, and `:z` is a harmless no-op there — so the simplest advice
is to just always include it, which is what the commands in this doc do.

## 4. Build the image (on your workstation, not the VM)

`runtime-browser` pulls and unpacks Chromium plus its OS-level dependencies,
weighing in at roughly 1.95GB as an image (measured in this session; expect
some drift as dependency versions change). Doing that on a 1/8-OCPU
always-free instance is slow and memory-pressured on the same box that's
supposed to be running crawls at 3am. Build locally instead:

```bash
docker build --target runtime-browser -t spinewatch:latest --platform linux/amd64 .
```

Use `--platform linux/amd64` if your workstation is Apple Silicon or another
non-amd64 architecture — the VM is amd64.

There's also a `runtime` target (no Playwright/Chromium, roughly 275MB as
measured in this session) that's useful for local development or CI, but
it's not what the VM runs — the crawler relies on the browser fallback
being available.

## 5. Get the image onto the VM

Two options; pick one.

### Option A: `docker save` over SSH (recommended for a single VM, no registry)

```bash
docker save spinewatch:latest | gzip | ssh <user>@<vm-host> 'gunzip | docker load'
```

One command, no registry account, no extra infrastructure — the right
default when there's exactly one VM to deploy to.

### Option B: push to a registry

```bash
docker tag spinewatch:latest <registry>/<namespace>/spinewatch:latest
docker push <registry>/<namespace>/spinewatch:latest
# on the VM:
docker pull <registry>/<namespace>/spinewatch:latest
docker tag <registry>/<namespace>/spinewatch:latest spinewatch:latest
```

Worth it if you end up with more than one host to deploy to, or want image
history/versioning. Overkill for a single box.

## 6. Set up the cron job

The crawler runs as a one-shot `docker run --rm` container, not a long-lived
daemon — a crash leaves nothing behind to clean up, memory is fully reclaimed
between runs, and nothing idles on a 1GB box between crawls.

Add this to the crontab (`crontab -e`) for the user in the `docker` group:

```cron
17 3 * * *  docker run --rm -v /srv/spinewatch/data:/data:z spinewatch:latest crawl >> /var/log/spinewatch.log 2>&1
```

3:17am rather than a round hour, to avoid the top-of-hour traffic spike that
every other cron job on the internet piles onto.

The container needs write access to `/var/log/spinewatch.log`, so either
pre-create it as the crontab's user (`sudo touch /var/log/spinewatch.log &&
sudo chown "$USER" /var/log/spinewatch.log`) or run the line with `sudo`
prepended if that's simpler for your setup.

## 7. Rotate the log

An appending cron job with no rotation will quietly fill the disk over
months. Add `/etc/logrotate.d/spinewatch`:

```
/var/log/spinewatch.log {
    weekly
    rotate 8
    compress
    missingok
    notifempty
    copytruncate
}
```

`copytruncate` matters here: the crawler process has already exited by the
time logrotate runs (it's a one-shot cron job, not a daemon holding the file
open), but using it anyway keeps this config correct even if that ever
changes, and avoids the trap of `rotate`'s default of expecting the process
to reopen the file. `weekly` + `rotate 8` keeps roughly two months of history
without much disk cost for a single crawl-per-night log.

## 8. Verify

Run the cron command by hand once, exactly as cron will invoke it, and check
the exit code and log output:

```bash
docker run --rm -v /srv/spinewatch/data:/data:z spinewatch:latest crawl
tail -50 /var/log/spinewatch.log   # after the first real cron run
```

`/srv/spinewatch/data/books.db` should exist after this and persist across
container runs and image upgrades — that's the whole point of the volume.

## 9. Deploying the read-only API

The frontend (`docs/frontend.md`) needs a JSON API reachable over HTTPS.
This is a second, independent deployment on the same VM — the crawl's cron
job above is untouched.

Build the `api` target locally, same as `runtime-browser` (step 4):

```bash
docker build --target api -t spinewatch-api:latest --platform linux/amd64 .
```

Transfer it the same way (step 5), then run it as a long-lived container,
not a one-shot `--rm` — the frontend can ask for data at any time, not just
at 03:17:

```bash
docker run -d --restart unless-stopped --name spinewatch-api \
  -v /srv/spinewatch/data:/data:z \
  -p 127.0.0.1:8000:8000 \
  spinewatch-api:latest
```

The API has no auth of its own — see §10. It must never be published on
anything but `127.0.0.1`.

The mount needs to be writable even for the read endpoints: SQLite's WAL
journal mode needs to create `-shm`/`-wal` sidecar files next to
`books.db`, which requires write access to the containing directory, not
just the database file. A read-only mount (`:ro`) makes every query fail
with `OperationalError: attempt to write a readonly database`. Binding to
`127.0.0.1:8000` rather than `0.0.0.0:8000` keeps the raw API port off the
public interface; only the reverse proxy below should be reachable from
outside the VM.

`SPINEWATCH_CORS_ORIGINS` is a comma-separated list of origins allowed to
call the API from a browser. With the single-domain Caddy setup in §10 the
frontend and the API share an origin, so it can stay unset — it is only
needed if the two are ever split across domains again, or for local
development (`http://127.0.0.1:8080`, see `frontend/README.md`).

## 10. Put Caddy in front (this is the only auth there is)

The app has no login, no API key, no auth code at all. A shared secret
compiled into a static page is readable by every visitor, so the gate lives
one layer up: `deploy/Caddyfile` terminates TLS, serves the frontend, proxies
the API, and puts HTTP basic auth in front of all of it — reads included.
Nothing here is meant for anonymous visitors.

Install it once (CI does not deploy it — it changes about once a year, and
wiring a live proxy config to every `git push` risks locking yourself out of
your own box):

```bash
# 1. Credentials, kept out of the public repo:
caddy hash-password                       # prompts, prints a bcrypt hash
sudo tee /etc/caddy/auth.conf <<'EOF'
basic_auth {
    yan <paste the hash>
}
EOF
sudo chown root:caddy /etc/caddy/auth.conf && sudo chmod 640 /etc/caddy/auth.conf

# 2. The config itself:
sudo cp deploy/Caddyfile /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

Verify both halves of the gate:

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://136-111-212-85.sslip.io/api/books      # 401
curl -s -o /dev/null -w '%{http_code}\n' -u yan:pw https://136-111-212-85.sslip.io/api/books  # 200
```

A `200` on the first command means auth is not applied — stop and fix it
before leaving the box up. Open only 443 in the VM's firewall; port 8000 is
bound to `127.0.0.1` and must stay unreachable from outside.

`config.js` on the VM needs no change: it already reads `API_BASE = "/api"`,
which matches the `handle_path` prefix. CI rsyncs the frontend but excludes
`config.js`, so the VM's copy is yours to edit and survives deploys — do
delete its now-defunct `API_KEY` line when you next touch it.

## Configuration

Everything tunable is an environment variable read by `config.py`, with
sane defaults baked into the image. Pass overrides with `-e` on `docker run`
if you ever need to, e.g.:

```bash
docker run --rm -v /srv/spinewatch/data:/data:z \
  -e SPINEWATCH_MAX_ESCALATIONS=5 \
  spinewatch:latest crawl
```

Variables: `SPINEWATCH_DB_PATH` (set to `/data/books.db` in the image already —
don't override unless you're changing the volume layout too),
`SPINEWATCH_REQUEST_DELAY_MIN` / `SPINEWATCH_REQUEST_DELAY_MAX`,
`SPINEWATCH_HTTP_TIMEOUT`, `SPINEWATCH_BROWSER_TIMEOUT`, `SPINEWATCH_MAX_ESCALATIONS`,
`SPINEWATCH_FIXTURE_DIR`, `SPINEWATCH_LOG_LEVEL`.

The image sets no `TZ`, so it runs on UTC, and `observed_on` is stamped using
the container's local date. If you run a manual crawl in the evening in a
timezone behind UTC, that can record tomorrow's date instead of today's. Add
`-e TZ=<Continent/City>` (e.g. `-e TZ=America/Sao_Paulo`) to the `docker run`
command if you want `observed_on` to reflect your local date instead —
`tzdata` is already in the image, so this needs no rebuild. The documented
03:17 cron entry avoids the problem in most timezones simply because it's
already past local midnight almost everywhere by then, but it's worth
setting `TZ` explicitly if you run crawls manually at other hours.

## Refreshing a broken parser

`docs/development-plan.md`'s "First week of operation" section tells you to
run `books fixture save <url>` when a store's markup changes, so you can fix
the parser against a saved fixture instead of live traffic. That command is
a development/workstation tool, not something to run inside the deployed
container as-is: `Settings.fixture_dir` defaults to the relative path
`tests/fixtures`, which resolves to `/app/tests/fixtures` inside the
container — a path that isn't part of the mounted `/data` volume, so it's
destroyed the moment a `--rm` container exits. The command will still exit
0 and print a path; the file just won't be there afterwards. Either run
`books fixture save` locally against your workstation's venv (the normal
way), or, if it has to run against the deployed image, add
`-e SPINEWATCH_FIXTURE_DIR=/data/fixtures` so the output lands on the
persistent volume instead of the container's ephemeral filesystem.

## Upgrading

Rebuild and re-transfer the image (steps 4-5), then just let the next cron
run pick up the new `spinewatch:latest` tag — no container to stop, since
nothing stays running between crawls. `/srv/spinewatch/data` is untouched
by an image rebuild.
