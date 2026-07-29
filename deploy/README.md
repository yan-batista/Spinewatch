# Deploying book-monitor to a VM

This documents how to run book-monitor's nightly crawl on a single VM (target:
Oracle Cloud's always-free `VM.Standard.E2.1.Micro` — 1 OCPU, 1GB RAM — but
none of this is Oracle-specific; any small Ubuntu/Debian-family box works the
same way). It does **not** cover provisioning the VM itself (creating the
instance, network/firewall rules) — only what happens once you can SSH into a
box with a fresh OS on it.

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
sudo mkdir -p /srv/book-monitor/data
```

## 4. Build the image (on your workstation, not the VM)

`runtime-browser` pulls and unpacks roughly 700MB of Chromium. Doing that on
a 1/8-OCPU always-free instance is slow and memory-pressured on the same box
that's supposed to be running crawls at 3am. Build locally instead:

```bash
docker build --target runtime-browser -t book-monitor:latest --platform linux/amd64 .
```

Use `--platform linux/amd64` if your workstation is Apple Silicon or another
non-amd64 architecture — the VM is amd64.

There's also a `runtime` target (no Playwright/Chromium, ~150MB) that's
useful for local development or CI, but it's not what the VM runs — the
crawler relies on the browser fallback being available.

## 5. Get the image onto the VM

Two options; pick one.

### Option A: `docker save` over SSH (recommended for a single VM, no registry)

```bash
docker save book-monitor:latest | gzip | ssh <user>@<vm-host> 'gunzip | docker load'
```

One command, no registry account, no extra infrastructure — the right
default when there's exactly one VM to deploy to.

### Option B: push to a registry

```bash
docker tag book-monitor:latest <registry>/<namespace>/book-monitor:latest
docker push <registry>/<namespace>/book-monitor:latest
# on the VM:
docker pull <registry>/<namespace>/book-monitor:latest
docker tag <registry>/<namespace>/book-monitor:latest book-monitor:latest
```

Worth it if you end up with more than one host to deploy to, or want image
history/versioning. Overkill for a single box.

## 6. Set up the cron job

The crawler runs as a one-shot `docker run --rm` container, not a long-lived
daemon — a crash leaves nothing behind to clean up, memory is fully reclaimed
between runs, and nothing idles on a 1GB box between crawls.

Add this to the crontab (`crontab -e`) for the user in the `docker` group:

```cron
17 3 * * *  docker run --rm -v /srv/book-monitor/data:/data book-monitor:latest crawl >> /var/log/book-monitor.log 2>&1
```

3:17am rather than a round hour, to avoid the top-of-hour traffic spike that
every other cron job on the internet piles onto.

The container needs write access to `/var/log/book-monitor.log`, so either
pre-create it as the crontab's user (`sudo touch /var/log/book-monitor.log &&
sudo chown "$USER" /var/log/book-monitor.log`) or run the line with `sudo`
prepended if that's simpler for your setup.

## 7. Rotate the log

An appending cron job with no rotation will quietly fill the disk over
months. Add `/etc/logrotate.d/book-monitor`:

```
/var/log/book-monitor.log {
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
docker run --rm -v /srv/book-monitor/data:/data book-monitor:latest crawl
tail -50 /var/log/book-monitor.log   # after the first real cron run
```

`/srv/book-monitor/data/books.db` should exist after this and persist across
container runs and image upgrades — that's the whole point of the volume.

## Configuration

Everything tunable is an environment variable read by `config.py`, with
sane defaults baked into the image. Pass overrides with `-e` on `docker run`
if you ever need to, e.g.:

```bash
docker run --rm -v /srv/book-monitor/data:/data \
  -e BOOKMON_MAX_ESCALATIONS=5 \
  book-monitor:latest crawl
```

Variables: `BOOKMON_DB_PATH` (set to `/data/books.db` in the image already —
don't override unless you're changing the volume layout too),
`BOOKMON_REQUEST_DELAY_MIN` / `BOOKMON_REQUEST_DELAY_MAX`,
`BOOKMON_HTTP_TIMEOUT`, `BOOKMON_BROWSER_TIMEOUT`, `BOOKMON_MAX_ESCALATIONS`,
`BOOKMON_FIXTURE_DIR`, `BOOKMON_LOG_LEVEL`.

## Upgrading

Rebuild and re-transfer the image (steps 4-5), then just let the next cron
run pick up the new `book-monitor:latest` tag — no container to stop, since
nothing stays running between crawls. `/srv/book-monitor/data` is untouched
by an image rebuild.
