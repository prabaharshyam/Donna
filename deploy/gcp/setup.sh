#!/usr/bin/env bash
# Donna: one-command setup for a Google Cloud e2-micro (Always Free) VM, Debian 12 or Ubuntu.
#
#   curl -fsSL https://raw.githubusercontent.com/prabaharshyam/Donna/main/deploy/gcp/setup.sh | sudo bash
#
# What it does (safe to re-run; re-running updates Donna to the latest code):
#   1. adds 2 GB swap (e2-micro has 1 GB RAM)
#   2. installs Docker, git and the firewall-friendly bits
#   3. clones/updates the repo into /opt/donna and builds the image
#   4. asks for your admin password + Claude API key once, stores them in /etc/donna/donna.env (root-only)
#   5. runs Donna (no public port) behind Caddy, which serves HTTPS with automatic certificates
#      at https://<your-ip>.sslip.io, or at your own domain if you set DONNA_DOMAIN
#   6. keeps everything running across reboots and takes a daily backup of Donna's data
#
# Optional environment variables (set them before `sudo -E bash`):
#   DONNA_DOMAIN=donna.example.com   use your own domain (point its A record at this VM first)
#   DONNA_REPO=https://github.com/<you>/Donna.git
#   DONNA_BRANCH=main
set -euo pipefail

REPO="${DONNA_REPO:-https://github.com/prabaharshyam/Donna.git}"
BRANCH="${DONNA_BRANCH:-main}"
APP_DIR=/opt/donna
ENV_DIR=/etc/donna
ENV_FILE="$ENV_DIR/donna.env"
CADDYFILE="$ENV_DIR/Caddyfile"
BACKUP_DIR=/var/backups/donna
NET=donna-net

say()  { printf '\n\033[1;35m▸ %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m! %s\033[0m\n' "$*"; }
die()  { printf '\033[1;31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "Run as root: curl -fsSL …/setup.sh | sudo bash"
command -v apt-get >/dev/null || die "This script supports Debian/Ubuntu images only."

# Prompts read from the terminal even when the script itself arrives through a pipe.
TTY=/dev/tty
ask() { # ask VAR "Prompt" [secret]
  local __v=""
  if [ -r "$TTY" ]; then
    if [ "${3:-}" = secret ]; then read -rsp "$2" __v <"$TTY"; echo >"$TTY"; else read -rp "$2" __v <"$TTY"; fi
  fi
  printf -v "$1" '%s' "$__v"
}

# ---------------------------------------------------------------- 1. swap
if ! swapon --show | grep -q .; then
  say "Adding 2 GB swap (the free VM has only 1 GB RAM)"
  fallocate -l 2G /swapfile 2>/dev/null || dd if=/dev/zero of=/swapfile bs=1M count=2048 status=none
  chmod 600 /swapfile && mkswap /swapfile >/dev/null && swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

# ---------------------------------------------------------------- 2. packages
say "Installing Docker and git"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq docker.io git curl ca-certificates >/dev/null
systemctl enable --now docker >/dev/null

# ---------------------------------------------------------------- 3. code
if [ -d "$APP_DIR/.git" ]; then
  say "Updating Donna from $BRANCH"
  git -C "$APP_DIR" fetch -q origin "$BRANCH" && git -C "$APP_DIR" reset -q --hard "origin/$BRANCH"
else
  say "Downloading Donna"
  git clone -q --branch "$BRANCH" "$REPO" "$APP_DIR"
fi
say "Building Donna (first time takes a few minutes on the free VM)"
docker build -q -t donna "$APP_DIR" >/dev/null

# ---------------------------------------------------------------- 4. address + secrets
meta() { curl -fs -H 'Metadata-Flavor: Google' "http://metadata.google.internal/computeMetadata/v1/$1" 2>/dev/null || true; }
IP="$(meta instance/network-interfaces/0/access-configs/0/external-ip)"
[ -n "$IP" ] || IP="$(curl -fs https://api.ipify.org || true)"
[ -n "$IP" ] || die "Couldn't find this VM's external IP. Does it have one? (VM → Edit → Network interface → External IPv4)"
HOST="${DONNA_DOMAIN:-${IP//./-}.sslip.io}"
URL="https://$HOST"

mkdir -p "$ENV_DIR" && chmod 700 "$ENV_DIR"
if [ ! -f "$ENV_FILE" ]; then
  say "One-time configuration"
  ask PW "Choose Donna's admin password (12+ characters, leave blank to generate one): " secret
  GENERATED=""
  if [ -z "$PW" ]; then PW="$(head -c 18 /dev/urandom | base64 | tr -d '/+=' | cut -c1-20)"; GENERATED=1; fi
  [ "${#PW}" -ge 12 ] || die "Password must be at least 12 characters."
  ask KEY "Paste your Claude API key (sk-ant-…), or leave blank to add it later in Admin → AI model: " secret
  if [ -n "$KEY" ] && [[ "$KEY" != sk-ant-* ]]; then warn "That doesn't look like a Claude API key (it should start with sk-ant-). Saving it anyway; fix it in Admin → AI model if needed."; fi
  umask 077
  {
    echo "DONNA_ADMIN_PASSWORD=$PW"
    [ -n "$KEY" ] && echo "ANTHROPIC_API_KEY=$KEY"
    echo "DONNA_PUBLIC_URL=$URL"
  } > "$ENV_FILE"
  chmod 600 "$ENV_FILE"
else
  # keep secrets, refresh the address in case the IP or domain changed
  sed -i "s#^DONNA_PUBLIC_URL=.*#DONNA_PUBLIC_URL=$URL#" "$ENV_FILE"
fi

# ---------------------------------------------------------------- 5. run
say "Starting Donna behind HTTPS at $URL"
docker network inspect "$NET" >/dev/null 2>&1 || docker network create "$NET" >/dev/null
docker rm -f donna >/dev/null 2>&1 || true
# No -p: Donna is reachable only through Caddy on the private Docker network.
docker run -d --name donna --network "$NET" --restart unless-stopped \
  -v donna-data:/data --env-file "$ENV_FILE" donna >/dev/null

cat > "$CADDYFILE" <<EOF
$HOST {
	encode gzip
	reverse_proxy donna:8765
}
EOF
docker rm -f donna-caddy >/dev/null 2>&1 || true
docker run -d --name donna-caddy --network "$NET" --restart unless-stopped \
  -p 80:80 -p 443:443 -v "$CADDYFILE:/etc/caddy/Caddyfile:ro" \
  -v caddy-data:/data -v caddy-config:/config caddy:2 >/dev/null

# ---------------------------------------------------------------- 6. backups + helper commands
mkdir -p "$BACKUP_DIR" && chmod 700 "$BACKUP_DIR"
cat > /usr/local/bin/donna-backup <<'EOF'
#!/usr/bin/env bash
# Daily snapshot of Donna's data volume; keeps the last 7.
set -euo pipefail
D=/var/backups/donna; mkdir -p "$D"
docker run --rm -v donna-data:/data:ro -v "$D":/out debian:12-slim \
  tar czf "/out/donna-$(date +%F).tgz" -C /data . 2>/dev/null
ls -1t "$D"/donna-*.tgz | tail -n +8 | xargs -r rm -f
EOF
cat > /usr/local/bin/donna-update <<EOF
#!/usr/bin/env bash
# Pull the latest Donna from GitHub, rebuild and restart (data is kept).
curl -fsSL https://raw.githubusercontent.com/prabaharshyam/Donna/$BRANCH/deploy/gcp/setup.sh | sudo bash
EOF
chmod 755 /usr/local/bin/donna-backup /usr/local/bin/donna-update
echo "17 3 * * * root /usr/local/bin/donna-backup" > /etc/cron.d/donna-backup

# ---------------------------------------------------------------- 7. health check
say "Waiting for HTTPS (certificate issuance can take up to a minute)"
ok=""
for _ in $(seq 1 30); do
  if curl -fs -o /dev/null "$URL/api/auth/status"; then ok=1; break; fi
  sleep 4
done

echo
if [ -n "$ok" ]; then
  printf '\033[1;32m✓ Donna is live at %s\033[0m\n' "$URL"
else
  warn "Donna is starting but HTTPS isn't answering yet."
  warn "Check that the VM allows HTTP and HTTPS traffic (VM → Edit → Firewalls), then run: sudo docker logs donna-caddy"
fi
if [ -n "${GENERATED:-}" ]; then
  echo; echo "  Your admin password (shown once; save it in a password manager):"; echo "    $PW"
fi
cat <<EOF

  Next:
   1. Open $URL and sign in with the admin password.
   2. On your Mac: Admin → Data → Download full backup. Stop the Mac copy (Ctrl-C).
   3. Here:      Admin → Data → Restore from backup, then Admin → Login & hosting → turn on 2FA.

  Handy commands on this server:
   sudo docker logs -f donna        live logs
   sudo donna-update                 update to the latest code from GitHub
   sudo donna-backup                 snapshot now (daily snapshots in $BACKUP_DIR)
EOF
