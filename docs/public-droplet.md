# Public Droplet Mode

Kanfei can run in a *read-only public droplet* mode — a
publicly-accessible instance that displays live data from a private
station without exposing anything that would let a visitor change
state, poll the hardware, or pull anything the private operator
hasn't chosen to publish.

The same Kanfei `.deb` runs on both ends.  The private station stays
exactly as it is; the droplet just selects a different driver.

## Architecture

The public droplet uses a synthetic driver — **`public_relay`** —
whose `poll()` returns whatever snapshot was most recently pushed
into a small in-memory buffer.  The rest of Kanfei is unchanged: the
poller reads that buffer, the WebSocket broadcasts it, the frontend
renders it, `/api/current` returns it.  Nothing new to learn.

Selecting `public_relay` as the station driver is also what puts the
whole instance into read-only mode:

- A write-block middleware returns **403** for every `POST` / `PUT`
  / `DELETE` / `PATCH` outside a two-path allowlist (`/api/ingest/*`).
- `require_admin` bypasses auth so guests can *read* admin-only
  endpoints (Settings needs data to render) but still cannot write.
- The Settings UI hides Save buttons and destructive tabs so guests
  don't see levers they can't pull.

On the private side, `kanfei-logger` runs a **relay sender** as a
third uploader alongside Weather Underground and CWOP.  Each poll
cycle it re-reads its config, and — if enabled and the local driver
is not itself `public_relay` — POSTs the current `SensorSnapshot` to
the droplet's `/api/ingest/reading` endpoint with a shared bearer
credential.  On the first cycle after a config or driver change, it
also POSTs `/api/ingest/config` so the droplet's Station Status tile
shows the real upstream station name and firmware instead of the
generic "Public Relay" label.

## Setting up the droplet

1. Provision a small VM (a $6/mo droplet is enough) and install
   Kanfei from the standard `.deb`.  The droplet needs Kanfei's
   frontend + backend + logger unit exactly as a private install
   does — no special package.

2. Run the setup wizard on the droplet.

3. When prompted for **Driver Type**, pick
   **Public Relay (droplet demo)**.  The wizard's connection panel
   asks for one thing: the **ingest secret**.  Generate a strong
   one:

       openssl rand -base64 32

   Paste the same value into both the droplet's wizard field *and*
   the private station's Public Droplet Relay settings — the two
   must match byte-for-byte.

4. Complete the wizard.  The droplet's logger daemon starts with the
   `PublicRelayDriver`, which does no I/O until data arrives.
   `/api/current` returns nulls until the first push.

## nginx recipe

Terminate TLS at nginx in front of Kanfei and use an `allow` /
`deny` block to gate the ingest path to the private station's IP.
Sample at `reference/nginx-public-droplet.conf.example`.

The bearer secret is the app-layer credential; the IP allowlist is
the network-layer belt to that belt.  Keep both.

## Setting up the private station

1. In Settings → Station on the private station, scroll to
   **Public Droplet Relay** and turn on **Enable relay**.

2. **Target URL**: the droplet's HTTPS base URL, e.g.
   `https://droplet.example.com`.  No trailing slash needed; the
   sender appends `/api/ingest/reading` and `/api/ingest/config`
   itself.

3. **Shared secret**: paste the exact value you set on the droplet.

4. Save.  The relay task in `kanfei-logger` reads these fields on the
   next poll cycle and pushes.  No restart needed.

## Verifying the pipe

- **Droplet**: `curl -sS https://droplet.example.com/api/current | jq` —
  should return the same values you see on the private station,
  refreshing at the private station's poll interval.
- **Droplet Station Status tile**: shows the upstream station's
  identity ("Vantage Vue (fw 2.12)" etc.) — that's the identity push
  arriving.
- **Private side**: in Settings → Public Droplet Relay, the
  **Last push failure** banner stays empty.  If it fills, the message
  tells you which layer refused (HTTP status, transport error, etc.).

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Last push failure: `HTTP 401: Invalid ingest credentials` | Secret mismatch between droplet and station | Regenerate and paste to both sides |
| Last push failure: `HTTP 503: Ingest not configured` | Droplet has the driver set but no secret yet | Finish the droplet's setup wizard (or set `public_mode_ingest_secret` via Settings) |
| Last push failure: `HTTP 403: Kanfei is running in read-only public mode` | The relay is somehow hitting a non-allowlisted path — file a bug | — |
| Last push failure: `transport: ConnectError: ...` | nginx refused (IP allowlist), droplet down, TLS problem | Check nginx access/error logs; verify the private station's outbound IP is in the allowlist |
| Droplet `/api/current` returns nulls despite green push | Reading push succeeds but the poller hasn't picked it up yet — one poll cycle | Wait one interval |
| Droplet Station Status still says "Public Relay" | Identity push hasn't fired (or first cycle in progress) | Wait one interval; if it persists, check `journalctl -u kanfei-logger` on the droplet |

## Security notes

- **Rotating the secret**: change it in both places within one poll
  interval to avoid a brief window of failed pushes.  Kanfei masks
  the secret in `GET /api/config` on both sides, so viewing Settings
  never reveals it.
- **IP allowlist maintenance**: if the private station's outbound IP
  changes (dynamic ISP), update the nginx `allow` block; the bearer
  alone would still work, but the two-layer story is the point.
- **The droplet's `require_admin` bypass is safe.**  It only widens
  the *read* surface (Settings, config).  Writes are still gated by
  the middleware, and every masked secret stays masked on that path
  too.  A specific regression test pins this
  (`test_secret_masked_in_public_mode_get_config`).
- **No inbound WebSocket writes exist today.**  If a future feature
  adds one, it needs its own gate — the HTTP middleware only
  protects HTTP methods.
- **Rate-limiting**: not enforced by the app.  Rely on nginx (`limit_req`)
  for the ingest paths on the droplet if it's exposed beyond the
  intended source IP.

## Phase history

- Phase 1 (PR #337): `PublicRelayDriver` skeleton + read-only middleware
  + `require_admin` guest bypass.
- Phase 2 (PR #339): bearer-gated ingest endpoints.
- Phase 3+4+5 (this PR): private-side relay sender, Settings UI
  audit, and these docs.
