#!/usr/bin/env bash
# Cloudflare quick tunnel for Montra.
#
# Installs cloudflared if missing, runs the tunnel as a systemd service so it
# survives a reboot, then points the app at the URL Cloudflare hands back and
# redeploys.
#
# Safe to re-run. A quick tunnel gets a NEW random hostname every time it
# restarts, so after a reboot just run this again: it picks up the new URL and
# re-points the app at it.
#
#   ./montra-tunnel.sh
#   ./montra-tunnel.sh --new     # force a fresh URL
#
set -euo pipefail

APP_DIR="${APP_DIR:-$HOME/apps/montra}"
ENV_FILE="${ENV_FILE:-.env.uat}"
PROJECT="${PROJECT:-montra}"
SERVICE="montra-tunnel"
FORCE_NEW=0
[ "${1:-}" = "--new" ] && FORCE_NEW=1

say()  { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
fail() { printf '\n\033[31m%s\033[0m\n' "$*" >&2; exit 1; }

# --------------------------------------------------------------- preflight
say "Checking the deploy directory"
cd "$APP_DIR" 2>/dev/null || fail "$APP_DIR does not exist. Set APP_DIR=/path/to/it."
[ -f "$ENV_FILE" ]               || fail "$APP_DIR/$ENV_FILE not found."
[ -f docker-compose.prod.yml ]   || fail "$APP_DIR/docker-compose.prod.yml not found."
[ -x ./vm-deploy.sh ]            || fail "$APP_DIR/vm-deploy.sh not found or not executable."
command -v docker >/dev/null     || fail "docker is not installed."
command -v systemctl >/dev/null  || fail "this script needs systemd."
sudo -v || fail "sudo is required (installing a package and a service unit)."

PORT="$(sed -n 's/^PROXY_PORT=\(.*\)$/\1/p' "$ENV_FILE" | tail -1)"
PORT="${PORT:-8080}"
# Redeploy whatever is already running rather than moving the version as a
# side effect of setting up a tunnel.
VERSION="${VERSION:-$(curl -s --max-time 5 "localhost:${PORT}/api/v1/meta" 2>/dev/null \
          | sed -n 's/.*"version":"\([^"]*\)".*/\1/p')}"
VERSION="${VERSION:-latest}"
echo "    $APP_DIR, env $ENV_FILE, port $PORT, project $PROJECT"

# ------------------------------------------------------------ cloudflared
say "Checking cloudflared"
if command -v cloudflared >/dev/null 2>&1; then
  echo "    already installed: $(cloudflared --version 2>&1 | head -1)"
else
  case "$(uname -m)" in
    x86_64|amd64) ARCH=amd64 ;;
    aarch64|arm64) ARCH=arm64 ;;
    armv7l) ARCH=arm ;;
    *) fail "unsupported architecture: $(uname -m)" ;;
  esac
  echo "    not found — installing for $ARCH"
  URL="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${ARCH}.deb"
  if command -v dpkg >/dev/null 2>&1; then
    curl -fsSL -o /tmp/cloudflared.deb "$URL" || fail "download failed: $URL"
    sudo dpkg -i /tmp/cloudflared.deb >/dev/null || fail "dpkg install failed"
    rm -f /tmp/cloudflared.deb
  else
    # Not Debian-based: drop the raw binary in instead.
    curl -fsSL -o /tmp/cloudflared \
      "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${ARCH}" \
      || fail "download failed"
    sudo install -m 0755 /tmp/cloudflared /usr/local/bin/cloudflared
    rm -f /tmp/cloudflared
  fi
  echo "    installed: $(cloudflared --version 2>&1 | head -1)"
fi
CFD="$(command -v cloudflared)"

# --------------------------------------------------------- systemd service
say "Installing the $SERVICE service"
sudo tee "/etc/systemd/system/${SERVICE}.service" >/dev/null <<EOF
[Unit]
Description=Cloudflare quick tunnel for Montra
After=network-online.target docker.service
Wants=network-online.target

[Service]
ExecStart=${CFD} tunnel --url http://localhost:${PORT} --no-autoupdate
Restart=always
RestartSec=5
User=${USER}

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE" >/dev/null 2>&1 || true

if [ "$FORCE_NEW" = "1" ] || ! systemctl is-active --quiet "$SERVICE"; then
  sudo systemctl restart "$SERVICE"
  echo "    started"
else
  echo "    already running"
fi

# ----------------------------------------------------------------- the URL
say "Waiting for the tunnel URL"
# Only from the current run: a quick tunnel gets a new hostname each restart,
# and the journal still holds every previous one.
SINCE="$(systemctl show -p ActiveEnterTimestamp --value "$SERVICE")"
[ -n "$SINCE" ] || SINCE="-1 min"
TUNNEL=""
for _ in $(seq 30); do
  TUNNEL="$(sudo journalctl -u "$SERVICE" --since "$SINCE" --no-pager 2>/dev/null \
            | grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' | tail -1 || true)"
  [ -n "$TUNNEL" ] && break
  sleep 2
done
[ -n "$TUNNEL" ] || {
  sudo journalctl -u "$SERVICE" --since "$SINCE" --no-pager | tail -20
  fail "no tunnel URL after 60s — see the log above."
}
echo "    $TUNNEL"

# ------------------------------------------------------------- app origins
say "Pointing the app at it"
LAN_IP="$(ip route get 1.1.1.1 2>/dev/null | awk '{print $7; exit}')"
LAN="http://${LAN_IP:-localhost}:${PORT}"
cp "$ENV_FILE" "${ENV_FILE}.bak"

set_kv() {
  if grep -q "^$1=" "$ENV_FILE"; then
    sed -i "s|^$1=.*|$1=$2|" "$ENV_FILE"
  else
    # Without this a file lacking a trailing newline gets the new key glued
    # onto its last line.
    [ -n "$(tail -c 1 "$ENV_FILE")" ] && echo >> "$ENV_FILE"
    echo "$1=$2" >> "$ENV_FILE"
  fi
}

# Both origins stay valid: the CSRF check compares the browser's Origin
# against this list, so dropping the LAN entry would break local access.
set_kv CORS_ORIGINS "${LAN},${TUNNEL}"
set_kv SAME_ORIGINS "${LAN},${TUNNEL}"
# Takes a single value — an S3 signature covers the host, so attachments work
# on whichever origin this names. The tunnel is the useful one.
set_kv S3_PUBLIC_ENDPOINT_URL "$TUNNEL"
# The tunnel is HTTPS but the LAN is not, and this flag is global: marking the
# cookie Secure would silently break every http:// visit.
set_kv COOKIE_SECURE false
echo "    LAN    $LAN"
echo "    tunnel $TUNNEL"

# ---------------------------------------------------------------- redeploy
say "Redeploying so the API reads the new origins"
ENV_FILE="$ENV_FILE" PROJECT="$PROJECT" ./vm-deploy.sh "$VERSION"

# ------------------------------------------------------------------ verify
say "Checking it end to end"
code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 "$TUNNEL/" || echo 000)"
meta="$(curl -s --max-time 20 "$TUNNEL/api/v1/meta" || true)"
echo "    home  HTTP $code"
echo "    meta  ${meta:-<no response>}"
[ "$code" = "200" ] || fail "the tunnel did not serve the app. Check: sudo journalctl -u $SERVICE -n 40"

cat <<EOF

Done.

  Tunnel   $TUNNEL
  LAN      $LAN
  Backup   ${ENV_FILE}.bak

The hostname is random and changes whenever the tunnel restarts, so after a
reboot run this script again to pick up the new one. Force a fresh URL with:

  ./$(basename "$0") --new

Anyone with that URL reaches your sign-in page. Nothing but the password is in
front of it.
EOF
