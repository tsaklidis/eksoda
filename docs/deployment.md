# Deployment and operations

How to run Eksoda in production, back it up, restore it, and react when a
receipt provider changes its pages. The production stack is
`compose.yaml` plus `compose.prod.yaml` (TD §3.2). Everything runs in
Docker; the host needs only Docker with Compose v2, `make` and `git`.

**Network model:** Eksoda is a home service, reachable only from the
home network and through the VPN, never from the internet.

- **Name:** clients use a local name, for example `eksoda.lan`, that a
  local DNS record points at the host.
- **Certificate:** no public certificate authority can validate a private
  name. Caddy therefore signs the certificate with its own local CA, and
  each client device trusts that CA once (§3.1).
- **Outbound traffic:** the worker still needs internet access to fetch
  receipt pages. Nothing needs inbound access from outside.

## 1. What runs

| Service | Image | Notes |
|---|---|---|
| `proxy` | `caddy:2-alpine` | The only published service. HTTPS for `$DOMAIN` with a certificate from Caddy's local CA (renewed automatically), HTTP → HTTPS redirect, 1 MB body cap |
| `api` | backend `prod` target | gunicorn, `WEB_CONCURRENCY` workers (default 2), non-root user |
| `worker` | backend | Celery, `CELERY_CONCURRENCY` processes (default 1), queues `imports` and `maintenance` |
| `beat` | backend | Due imports every minute, daily maintenance |
| `migrate` | backend | One-shot `migrate` before the app services start |
| `db` | `postgres:17-alpine` | Volume `pgdata`. Not published |
| `redis` | `redis:7-alpine` | Broker and cache, no persistence, 64 MB cap that evicts only expiring cache keys |
| `backup` | `postgres:17-alpine` | `ops/backup.sh loop`: one `pg_dump -Fc` a day into `BACKUP_DIR`, 30-day rotation |

Every service restarts automatically (`unless-stopped`). Container logs are JSON (`LOG_FORMAT=json`), and Docker rotates them at 3 × 10 MB per service.

**Footprint** (measured on arm64 with the defaults, idle, 2026-11-15): about 400 MB of RAM in all.

| Service | RAM |
|---|---|
| `api` (2 workers) | 160 MB |
| `worker` | 100 MB |
| `beat` | 80 MB |
| `db` | 40 MB |
| `proxy` | 20 MB |
| `redis` | 10 MB |

CPU use is near zero between imports. An import is one or two HTTPS fetches and a small HTML parse.

## 2. Preparing the host

General:

- **Name:** add a local DNS record for `DOMAIN` that points at the host's LAN address. In Pi-hole: *Settings → Local DNS Records*, for example `eksoda.lan` → the host's LAN IP.
- **VPN:** VPN clients must use the same DNS server, which PiVPN does by default (Pi-hole). They reach the LAN address through the tunnel.
  - If a client cannot resolve the name, check the `DNS =` line of its WireGuard profile.
  - A split-tunnel profile must also route the LAN subnet.
- **Router:** do not forward the proxy's ports. The only port open to the internet is the VPN's.

### Raspberry Pi 4 (4 GB) notes

The stack fits comfortably next to Pi-hole and Home Assistant. Check these first:

1. **Port 443 is taken.**
   - Pi-hole v6 serves its web interface on 443 (and 8080).
   - The simplest fix is `HTTP_PORT=8081` and `HTTPS_PORT=8443` in `.env`; clients then use `https://eksoda.lan:8443`.
   - The alternative is to move Pi-hole's web server (`webserver.port` in `/etc/pihole/pihole.toml`) and keep 80/443 for Eksoda.
2. **Docker cannot enforce memory limits by default.**
   - Raspberry Pi OS boots with the cgroup memory controller off: `docker info` prints "No memory limit support", and the `mem_limit` values are ignored.
   - The limits stop a runaway container from starving Pi-hole, which is the DNS server for the whole network.
   - To enable them, add `cgroup_enable=memory cgroup_memory=1` to the single line in `/boot/firmware/cmdline.txt` and reboot.
3. **Swap.** The default swap file is 200 MB. 1 GB is safer: set `CONF_SWAPSIZE=1024` in `/etc/dphys-swapfile`, then run `sudo systemctl restart dphys-swapfile`.
4. **Storage.**
   - PostgreSQL writes steadily, which wears SD cards.
   - A USB SSD for Docker's data (or booting from it) is better.
   - Whatever the storage, set `BACKUP_DIR` to a different device, or copy the dumps off the Pi (§5).
5. **Building.** `make prod-up` builds the arm64 image on the Pi in a few minutes. All dependencies have arm64 wheels, so nothing compiles.
6. **DNS from containers.**
   - Pi-hole in its default "local requests only" mode silently drops queries from Docker's default bridge (172.17.0.0/16). Containers there time out on DNS.
   - Image builds are affected: `uv sync` could not download wheels. `compose.prod.yaml` therefore builds with `network: host`.
   - The running services are not affected. They are on compose's own network, whose embedded DNS forwards queries from the host, so Pi-hole answers. The worker resolves the receipt hosts normally.
   - Seen on the Pi on 2026-11-15.

## 3. First deployment

```bash
git clone <repository> eksoda && cd eksoda
cp .env.example .env
```

Edit `.env`:

| Variable | Value |
|---|---|
| `DJANGO_SECRET_KEY` | `python3 -c "import secrets; print(secrets.token_urlsafe(64))"` |
| `POSTGRES_PASSWORD` | A random password. Also put it in `DATABASE_URL` (`postgres://eksoda:<password>@db:5432/eksoda`) |
| `DOMAIN` | The local name, for example `eksoda.lan` (§2) |
| `DJANGO_ALLOWED_HOSTS` | `<DOMAIN>,localhost` (`localhost` is used by the container healthcheck) |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | `https://<DOMAIN>`, or `https://<DOMAIN>:<HTTPS_PORT>` when the port is not 443 (for example `https://eksoda.lan:8443`) |
| `DJANGO_ADMIN_PATH` | Something other than `admin/`, for example `manage-7f3a/` |
| `HTTP_PORT` / `HTTPS_PORT` | Only when 80/443 are taken on the host (§2) |
| `BACKUP_DIR` | A directory on another device, if available |
| `SENTRY_DSN` | Optional |

`DJANGO_SETTINGS_MODULE` and `LOG_FORMAT` are set by `compose.prod.yaml` and need no change. Then:

```bash
make prod-up                                                    # build, migrate, start everything
make bootstrap PROD=1 EMAIL=you@example.com HOUSEHOLD="Home"     # first owner (prompts for a password)
make prod-ps                                                    # all services healthy or running
make prod-ca                                                    # export the local root CA to eksoda-root-ca.crt
curl --cacert eksoda-root-ca.crt https://<DOMAIN>[:<HTTPS_PORT>]/readyz   # {"status": "ok"}
```

### 3.1 Trusting the local CA on client devices

`make prod-ca` writes `eksoda-root-ca.crt` and prints its SHA-256
fingerprint. The file is a public certificate, not a secret, and git
ignores it. Copy it to each device, check the fingerprint, and install
it as a trusted CA:

| Device | How |
|---|---|
| Android | *Settings → Security & privacy → More security settings → Encryption & credentials → Install a certificate → CA certificate*. Browsers then trust it. The Eksoda app needs one more change (below) |
| iPhone / iPad | Open the file (AirDrop or Files) to install the profile, then turn it on under *Settings → General → About → Certificate Trust Settings* |
| macOS | `sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain eksoda-root-ca.crt` |
| Windows | `certutil -addstore Root eksoda-root-ca.crt` (as administrator) |
| Firefox | Uses its own store: *Settings → Privacy & Security → Certificates → View Certificates → Authorities → Import* |

**The Eksoda Android app.** Since Android 7, apps ignore user-installed CAs unless their network security config allows them. The app's release configuration currently trusts only system CAs, so it must do one of these:

- **Bundle the root certificate** (stricter). Put `eksoda-root-ca.crt` in `res/raw/` and add a `<domain-config>` for the server's name with `<trust-anchors><certificates src="@raw/eksoda_root_ca"/></trust-anchors>`.
- **Trust user CAs for that domain:** `<certificates src="user"/>`.

See `docs/android-app.md` §10.

**Keep the CA:**

- **Where it lives:** the root key is in the `caddy_data` volume, and the root is valid for 10 years.
- **Safe:** `make prod-down` keeps volumes. Recreating the proxy keeps the CA too.
- **Destructive:** `docker compose down -v` creates a new CA, which must then be installed on every device again.
- **Leaf certificates:** Caddy renews them automatically, and clients never notice.

Admin: `https://<DOMAIN>/<DJANGO_ADMIN_PATH>`. Create a staff user with `make superuser PROD=1`, or pass `ARGS=--superuser` to `bootstrap`.

Swagger and the schema are available to staff only in production.

`make <target> PROD=1` runs any one-off command against the production stack: `manage`, `shell`, `migrate`, `bootstrap` and `backup`.

## 4. Updating

```bash
git pull
make prod-up          # rebuilds the image; the migrate service applies new migrations first
```

Notes:

- **Back up before an update with migrations:** `make backup PROD=1`.
- **After changing `ops/Caddyfile` or `ops/backup.sh`:** run `docker compose -f compose.yaml -f compose.prod.yaml up -d --force-recreate proxy backup`. They are single-file bind mounts, so a running container keeps seeing the old file.

## 5. Backups and restore

**Automatic:**

- **When:** the `backup` service writes `eksoda-YYYYMMDD-HHMMSS.dump` (custom format) once a day after `BACKUP_HOUR_UTC` (default 01:00 UTC). If it was down at that hour, it catches up when it starts.
- **Where:** into `BACKUP_DIR`, as a temporary file renamed when complete. The directory and the dumps belong to `BACKUP_OWNER` (default `1000:1000`, the Pi's first user) and are readable by that user only, so `make backup` and `make restore` work without `sudo`.
- **Retention:** dumps older than `BACKUP_RETENTION_DAYS` (30) are deleted after each new one.
- **Deleted data:** receipts a user deleted stay in older dumps until those dumps expire (requirements §15.4).
- **Off-host copies:** a dump on the same disk does not survive a dead disk. Copy `BACKUP_DIR` elsewhere regularly, for example with a cron job on another machine:

  ```bash
  rsync -a pi:eksoda/backups/ ~/eksoda-backups/
  ```

**Manual:** `make backup PROD=1` writes a dump to `backups/` (or `BACKUP_DIR=…`).

**Restore** (replaces the whole database):

```bash
make restore PROD=1 FILE=backups/eksoda-20261115-010000.dump CONFIRM=yes
```

The target runs these steps:

1. Takes a safety dump of the current database.
2. Stops `api`, `worker` and `beat`.
3. Drops and recreates the database.
4. Restores the dump in a single transaction.
5. Starts the stack again. The migrate service applies any newer migrations.

To restore on a new host, run `make prod-up`, then `make restore`.

**Restore test record:**

- **Date:** 2026-11-15, dev stack, the same commands without `PROD=1`.
- **Data:** 150 demo receipts, 428 lines and 15 products were dumped, 100 receipts were deleted, and the dump was restored. All 150, 428 and 15 rows came back, and the stack restarted healthy.
- **Production trial:** the `backup` service wrote a daily dump and pruned a 45-day-old dump while keeping a 26-day-old one.
- Repeat the test after major upgrades.

## 6. Monitoring

| What | Where |
|---|---|
| Liveness and readiness | `GET /healthz`; `GET /readyz` checks PostgreSQL and Redis, 503 when either is down |
| Logs | `make prod-logs ARGS="api worker"`. JSON with `request_id`, `user_id`, `household_id`, `job_id` and `provider`. Receipt URLs never appear: services log host and fingerprint, and a filter redacts any URL as a safety net |
| Import health | Admin → Receipt import jobs, filtered by status, provider and error code; receipts filtered by parser version |
| Errors | Optional Sentry (`SENTRY_DSN`) |

**What Sentry receives:**

- **Never sent:**
  - local variables
  - request bodies, query strings and cookies
  - the `Authorization`, `Cookie`, `Referer` and forwarding headers
- **Redacted:** every URL-shaped string left in an event or breadcrumb becomes `<url>`.
- **Tags:** request, task, job, household and provider ids.

## 7. Security notes

- **Exposure:** only the proxy is published, and only on the home network and the VPN. The router forwards nothing to it.
- **Client IPs:** Django trusts `X-Forwarded-Proto` and one hop of `X-Forwarded-For` (`NUM_PROXIES=1`) from Caddy. Never publish `api` directly.
- **Throttles:**
  - Login: 5 per minute per IP and email, 30 per minute per IP.
  - Admin login: 5 per minute per IP.
  - Imports and retries: 30 per minute and 500 per day per user.
- **Body limits:** API bodies over 16 KB get a 400; the proxy rejects anything over 1 MB.
- **Worker egress:** the worker makes outbound HTTPS requests on port 443, only to the provider hosts (`einvoice.impact.gr`, `e-invoicing.gr`, `www1.aade.gr`), and only to public addresses (the fetcher's SSRF checks, TD §10). A host firewall may restrict container egress to TCP 443 and DNS. Nothing else is needed.
- **Dependencies:** audit the locked runtime dependencies with this command (it needs network access; it found no known vulnerabilities on 2026-11-15):

  ```bash
  docker compose run --rm --no-deps api sh -c 'uv export --frozen --no-dev --no-hashes --no-emit-project -q > /tmp/req.txt && uvx pip-audit -r /tmp/req.txt --no-deps --disable-pip'
  ```

## 8. Runbook: a provider changed its page format

**Symptoms:**

- imports failing with `provider_format_changed` or `inconsistent_source` (admin filter by error code)
- `unknown field` log lines for a provider
- validation warnings on new receipts

**Steps:**

1. **Get a failing link** from the user. In the admin you see only the host and the fingerprint. Never paste receipt links into tickets or chat logs.
2. **Reproduce without the database:**

   ```bash
   make parse-receipt SRC="<url>"
   ```

   This fetches, parses and validates, and prints the error or the unknown fields. Save the raw page outside the repository.
3. **Turn it into a fixture:**

   ```bash
   make sanitize-fixture PROVIDER=<code> IN=/abs/raw.html OUT=tests/fixtures/<code>/<name>.html
   ```

4. **Fix the parser.** For a changed page, add a new layout to the provider under `apps/receipts/providers/<code>/` (TD §9.7). For a new label, extend `apps/receipts/vocabulary.py`. Then:
   - review the golden-file diff
   - run `make check`
   - deploy (§4)
5. **Retry the failed imports.** In the admin, select the jobs and run the retry action. Or call `POST /api/v1/receipt-imports/{id}/retry`; this counts against the import limits.
