#!/usr/bin/env bash
# One-time bootstrap for a fresh Oracle Cloud Ubuntu 22.04/24.04 VM (arm64 or x86_64).
# Run as the default "ubuntu" user:  bash deploy/oracle/setup.sh
# Safe to run again: every step checks whether it is already done.
set -euo pipefail

if [[ $EUID -eq 0 ]]; then
  echo "Run this as the normal 'ubuntu' user (it uses sudo where needed), not as root." >&2
  exit 1
fi

TARGET_USER="${USER}"
export DEBIAN_FRONTEND=noninteractive

log() { printf '\n==> %s\n' "$*"; }

# ---------------------------------------------------------------------------
log "Installing base packages"
sudo apt-get update -y
sudo apt-get install -y ca-certificates curl gnupg git iptables-persistent netfilter-persistent unattended-upgrades

# ---------------------------------------------------------------------------
log "Opening TCP 80 and 443 in the host firewall"
# Oracle's Ubuntu images ship iptables rules that end the INPUT chain with
# "-j REJECT --reject-with icmp-host-prohibited", so only SSH (22) is reachable.
# Insert ACCEPT rules just before that REJECT, live and in the saved rules file.
open_port() {
  local port="$1"
  if sudo iptables -C INPUT -p tcp -m state --state NEW -m tcp --dport "$port" -j ACCEPT 2>/dev/null; then
    echo "  port $port already open (live rules)"
  else
    local pos
    pos="$(sudo iptables -L INPUT --line-numbers -n | awk '$2=="REJECT"{print $1; exit}')"
    if [[ -n "$pos" ]]; then
      sudo iptables -I INPUT "$pos" -p tcp -m state --state NEW -m tcp --dport "$port" -j ACCEPT
    else
      sudo iptables -A INPUT -p tcp -m state --state NEW -m tcp --dport "$port" -j ACCEPT
    fi
    echo "  port $port opened (live rules)"
  fi
}
open_port 80
open_port 443

# Persist by editing /etc/iptables/rules.v4 directly instead of "netfilter-persistent save":
# a save would also freeze Docker's own (dynamic) chains into the file.
RULES=/etc/iptables/rules.v4
if [[ ! -f "$RULES" ]]; then
  sudo mkdir -p /etc/iptables
  sudo sh -c "iptables-save > $RULES"
fi
for port in 80 443; do
  rule="-A INPUT -p tcp -m state --state NEW -m tcp --dport $port -j ACCEPT"
  if sudo grep -qxF -- "$rule" "$RULES"; then
    echo "  port $port already persisted in $RULES"
  elif sudo grep -q -- '^-A INPUT -j REJECT' "$RULES"; then
    sudo sed -i "0,/^-A INPUT -j REJECT/s//${rule//\//\/}\n&/" "$RULES"
    echo "  port $port persisted in $RULES"
  else
    sudo sed -i "0,/^COMMIT/s//${rule//\//\/}\n&/" "$RULES"
    echo "  port $port persisted in $RULES"
  fi
done
sudo systemctl enable netfilter-persistent >/dev/null 2>&1 || true

# ---------------------------------------------------------------------------
log "Installing Docker Engine + compose plugin (official Docker apt repo)"
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  echo "  Docker already installed: $(docker --version)"
else
  sudo install -m 0755 -d /etc/apt/keyrings
  if [[ ! -f /etc/apt/keyrings/docker.asc ]]; then
    sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    sudo chmod a+r /etc/apt/keyrings/docker.asc
  fi
  # shellcheck disable=SC1091
  codename="$(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")"
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${codename} stable" \
    | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
  sudo apt-get update -y
  sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
sudo systemctl enable --now docker

if id -nG "$TARGET_USER" | grep -qw docker; then
  echo "  $TARGET_USER is already in the docker group"
else
  sudo usermod -aG docker "$TARGET_USER"
  echo "  added $TARGET_USER to the docker group (log out and back in to use docker without sudo)"
fi

# ---------------------------------------------------------------------------
log "Swap"
if [[ -n "$(swapon --show --noheadings)" ]]; then
  echo "  swap already active:"; swapon --show
else
  if [[ ! -f /swapfile ]]; then
    sudo fallocate -l 2G /swapfile || sudo dd if=/dev/zero of=/swapfile bs=1M count=2048
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
  fi
  sudo swapon /swapfile
  grep -qF '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
  echo "  2 GB swapfile enabled"
fi

# ---------------------------------------------------------------------------
log "Enabling unattended security upgrades"
sudo tee /etc/apt/apt.conf.d/20auto-upgrades >/dev/null <<'CONF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
CONF
sudo systemctl enable --now unattended-upgrades >/dev/null 2>&1 || true

# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$SCRIPT_DIR/data"

PUBLIC_IP="$(curl -fsS --max-time 5 https://ifconfig.me 2>/dev/null || true)"
HOST_HINT="${PUBLIC_IP:+${PUBLIC_IP//./-}.sslip.io}"

cat <<NEXT

Done. Next steps:
  1. Log out and back in (so the docker group applies):  exit  then ssh in again
  2. Make sure the VCN security list allows TCP 80 and 443 from 0.0.0.0/0 (Oracle console).
  3. Create the config file:
       cd $SCRIPT_DIR
       cp .env.example .env && nano .env
     Set PUBLIC_HOST=${HOST_HINT:-<your-ip-with-dashes>.sslip.io}
     and WEBAPP_URL=https://${HOST_HINT:-<PUBLIC_HOST>}
  4. (Optional) copy an existing finance.db into $SCRIPT_DIR/data/
  5. Stop any other running copy of the bot (e.g. Railway), then:
       docker compose up -d --build
       docker compose logs -f bot
NEXT
