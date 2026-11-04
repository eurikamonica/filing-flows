#!/bin/bash
# One-step install of a server for the static site (deploy/README.md). Generic Ubuntu/Debian with systemd: it uses
# nothing of one hosting company, so the same command sets up a server anywhere. Safe to run again (it skips what is
# done and refreshes the helper scripts).
#
#   curl -fsSL https://raw.githubusercontent.com/eurikamonica/filing-flows/main/deploy/server/setup.sh | sudo bash
#   … | sudo bash -s -- --domain example.com --no-swap --fail2ban
#
# What it does:
#   1. packages: Caddy (its official apt repository; Ubuntu's own package if that fails), rsync, python3, ufw,
#      unattended-upgrades, dnsutils
#   2. the user "deploy" (no password, no sudo) and the site folders /srv/filing-flows/{stage,releases,state}
#   3. the helper commands in /usr/local/bin: ff-deploy-gate, ff-publish, ff-status, ff-site, ff-deploy-key,
#      ff-ssh-lockdown
#   4. the deploy key for GitHub Actions (only allowed to run ff-deploy-gate; print it with: sudo ff-deploy-key show)
#   5. Caddy in "staging" mode (plain HTTP, noindex) until the domain points here: sudo ff-site live / origin
#   6. firewall: only 22 (SSH), 80 and 443 (web) open
#   7. automatic security updates (with a reboot at 08:10 UTC when an update needs one)
#   8. log limits: Caddy's access log rolls at 50 MB (5 kept), the system journal stays under 300 MB
#   9. a 2 GB swap file (--no-swap to skip); fail2ban for SSH with --fail2ban
# It does NOT turn off password login: do that with "sudo ff-ssh-lockdown" after logging in with your key works.
set -euo pipefail

REPO="eurikamonica/filing-flows"
REF="main"
DOMAIN="filing-flows.com"
SITE_NAME="Filing Flows"
SWAP=yes
FAIL2BAN=no
HOST_IP=""
BASE="/srv/filing-flows"
DEPLOY_USER="deploy"

while [ $# -gt 0 ]; do
  case "$1" in
    --domain) DOMAIN="$2"; shift 2 ;;
    --site-name) SITE_NAME="$2"; shift 2 ;;
    --repo) REPO="$2"; shift 2 ;;
    --ref) REF="$2"; shift 2 ;;
    --host) HOST_IP="$2"; shift 2 ;;
    --no-swap) SWAP=no; shift ;;
    --fail2ban) FAIL2BAN=yes; shift ;;
    -h|--help) sed -n '2,24p' "$0" 2>/dev/null | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

say() { printf '\n\033[1m▶ %s\033[0m\n' "$*"; }
ok() { printf '  ✔ %s\n' "$*"; }

if [ "$(id -u)" -ne 0 ]; then echo "请用 sudo 运行 / run with sudo" >&2; exit 1; fi
command -v apt-get >/dev/null || { echo "needs Ubuntu or Debian (apt-get)" >&2; exit 1; }
command -v systemctl >/dev/null || { echo "needs systemd" >&2; exit 1; }
export DEBIAN_FRONTEND=noninteractive
# a new server is often still running its own first updates: wait for apt's lock (up to 10 minutes) instead of failing
apt_get() { apt-get -o DPkg::Lock::Timeout=600 "$@"; }

# ---------------------------------------------------------------- 1. packages
say "1/9 安装软件 / packages"
apt_get update -q
apt_get install -y -q ca-certificates curl gnupg rsync python3 ufw unattended-upgrades openssl util-linux \
  openssh-server >/dev/null
apt_get install -y -q bind9-dnsutils >/dev/null 2>&1 || apt_get install -y -q dnsutils >/dev/null 2>&1 || true
if ! command -v caddy >/dev/null; then
  if curl -fsSL https://dl.cloudsmith.io/public/caddy/stable/gpg.key \
       | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg \
     && curl -fsSL https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt \
       -o /etc/apt/sources.list.d/caddy-stable.list; then
    chmod o+r /usr/share/keyrings/caddy-stable-archive-keyring.gpg /etc/apt/sources.list.d/caddy-stable.list
    apt_get update -q
  fi
  apt_get install -y -q caddy >/dev/null
fi
ok "Caddy $(caddy version | cut -d' ' -f1), rsync $(rsync --version | head -1 | awk '{print $3}')"
RRSYNC=$(command -v rrsync || true)
if [ -z "$RRSYNC" ]; then                     # older rsync packages ship it as documentation only
  for f in /usr/share/doc/rsync/scripts/rrsync /usr/share/doc/rsync/scripts/rrsync.gz; do
    if [ -f "$f" ]; then
      case "$f" in *.gz) gunzip -c "$f" > /usr/local/bin/rrsync ;; *) cp "$f" /usr/local/bin/rrsync ;; esac
      chmod 755 /usr/local/bin/rrsync
      RRSYNC=/usr/local/bin/rrsync
      break
    fi
  done
fi
[ -n "$RRSYNC" ] || { echo "rrsync not found (part of the rsync package)" >&2; exit 1; }
ok "rrsync: $RRSYNC"

# ---------------------------------------------------------------- 2. user and folders
say "2/9 部署用户和网站目录 / deploy user and folders"
if ! id "$DEPLOY_USER" >/dev/null 2>&1; then
  useradd --create-home --shell /bin/sh --comment "site uploads from GitHub Actions" "$DEPLOY_USER"
fi
# no password at all ("*", not "!": sshd without PAM refuses keys of a locked account)
usermod -p '*' "$DEPLOY_USER"
gpasswd -d "$DEPLOY_USER" sudo >/dev/null 2>&1 || true
install -d -m 755 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "$BASE" "$BASE/stage" "$BASE/releases" "$BASE/state"
ok "用户 $DEPLOY_USER（无密码、无 sudo），目录 $BASE"

# ---------------------------------------------------------------- 3. helper commands
say "3/9 辅助命令 / helper commands"
here=""
if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "${BASH_SOURCE[0]}" ]; then
  here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
fi
for name in ff-deploy-gate ff-publish ff-status ff-site ff-deploy-key ff-ssh-lockdown; do
  if [ -n "$here" ] && [ -f "$here/bin/$name" ]; then
    install -m 755 "$here/bin/$name" "/usr/local/bin/$name"
  else
    curl -fsSL "https://raw.githubusercontent.com/$REPO/$REF/deploy/server/bin/$name" -o "/usr/local/bin/$name.new"
    install -m 755 "/usr/local/bin/$name.new" "/usr/local/bin/$name"
    rm -f "/usr/local/bin/$name.new"
  fi
done
ok "ff-deploy-gate ff-publish ff-status ff-site ff-deploy-key ff-ssh-lockdown"

if [ -z "$HOST_IP" ]; then
  HOST_IP=$(ip -4 -o addr show scope global | awk '{print $4}' | cut -d/ -f1 | head -1)
fi
IPV6=$(ip -6 -o addr show scope global 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | head -1)
install -d -m 755 /etc/filing-flows
CONF=/etc/filing-flows/site.conf
mode="staging"
test_host=""
if [ -f "$CONF" ]; then
  mode=$(sed -n 's/^MODE=//p' "$CONF" | tail -1 | tr -d '"')
  test_host=$(sed -n 's/^TEST_HOST=//p' "$CONF" | tail -1 | tr -d '"')
fi
cat > "$CONF" <<EOF
# Filing Flows server settings (setup.sh writes it; ff-site changes MODE and TEST_HOST)
DOMAIN="$DOMAIN"
SITE_NAME="$SITE_NAME"
BASE="$BASE"
IPV4="$HOST_IP"
IPV6="$IPV6"
MODE="${mode:-staging}"
TEST_HOST="$test_host"
EOF
ok "$CONF（域名 $DOMAIN，IPv4 $HOST_IP）"

# ---------------------------------------------------------------- 4. deploy key
say "4/9 GitHub Actions 部署钥匙 / deploy key"
deploy_keys="$(getent passwd "$DEPLOY_USER" | cut -d: -f6)/.ssh/authorized_keys"
if [ -s "$deploy_keys" ]; then
  # keep the key, refresh the restrictions in front of it
  pub=$(grep -o 'ssh-ed25519 [A-Za-z0-9+/=]*.*$' "$deploy_keys" | head -1)
  if [ -n "$pub" ]; then
    printf 'restrict,command="/usr/local/bin/ff-deploy-gate" %s\n' "$pub" > "$deploy_keys"
  fi
  ok "已有部署钥匙，保留 / kept"
else
  ff-deploy-key new >/dev/null
  ok "已生成（之后用 sudo ff-deploy-key show 查看要填进 GitHub 的内容）"
fi

# ---------------------------------------------------------------- 5. web server
say "5/9 Caddy 网站配置 / web server"
install -d -m 755 -o caddy -g caddy /var/log/caddy
ff-site "${mode:-staging}" >/dev/null
systemctl enable -q caddy
ok "模式 ${mode:-staging}；网站根目录 $BASE/current"

# ---------------------------------------------------------------- 6. firewall
say "6/9 防火墙 / firewall"
ufw allow 22/tcp >/dev/null
for p in $(sshd -T 2>/dev/null | awk '$1 == "port" {print $2}'); do ufw allow "$p/tcp" >/dev/null; done   # SSH on another port too
ufw allow 80/tcp >/dev/null
ufw allow 443/tcp >/dev/null
ufw allow 443/udp >/dev/null        # HTTP/3 on the same port
ufw default deny incoming >/dev/null
ufw default allow outgoing >/dev/null
ufw --force enable >/dev/null
ok "只开放 22（SSH）、80、443（网站）"

# ---------------------------------------------------------------- 7. automatic updates
say "7/9 自动安全更新 / automatic security updates"
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
EOF
cat > /etc/apt/apt.conf.d/52filing-flows-upgrades <<'EOF'
// Filing Flows: also Caddy's own repository, and a reboot at a quiet hour when an update needs one
Unattended-Upgrade::Origins-Pattern {
        "origin=cloudsmith/caddy/stable";
};
Unattended-Upgrade::Automatic-Reboot "true";
Unattended-Upgrade::Automatic-Reboot-Time "08:10";
Unattended-Upgrade::Remove-Unused-Dependencies "true";
EOF
systemctl enable -q --now unattended-upgrades 2>/dev/null || true
ok "每天自动安装安全更新；需要重启时在 08:10 UTC 自动重启（约 1 分钟）"

# ---------------------------------------------------------------- 8. logs
say "8/9 日志轮转 / logs"
install -d -m 755 /etc/systemd/journald.conf.d
cat > /etc/systemd/journald.conf.d/filing-flows.conf <<'EOF'
[Journal]
SystemMaxUse=300M
EOF
systemctl restart systemd-journald
ok "Caddy 访问日志满 50MB 换新文件、留 5 个；系统日志最多 300MB"

# ---------------------------------------------------------------- 9. swap, fail2ban
say "9/9 swap / fail2ban"
if [ "$SWAP" = yes ] && ! swapon --show | grep -q .; then
  if fallocate -l 2G /swapfile 2>/dev/null || dd if=/dev/zero of=/swapfile bs=1M count=2048 status=none; then
    chmod 600 /swapfile
    mkswap /swapfile >/dev/null
    swapon /swapfile
    grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
    echo 'vm.swappiness=10' > /etc/sysctl.d/90-filing-flows-swap.conf
    sysctl -q -p /etc/sysctl.d/90-filing-flows-swap.conf || true
    ok "2GB swap"
  fi
elif [ "$SWAP" = yes ]; then
  ok "已有 swap / swap already on"
else
  ok "跳过 swap / no swap (--no-swap)"
fi
if [ "$FAIL2BAN" = yes ]; then
  apt_get install -y -q fail2ban >/dev/null
  systemctl enable -q --now fail2ban
  ok "fail2ban（SSH 多次失败的地址会被暂时封禁）"
fi

admin="${SUDO_USER:-}"
if [ -n "$admin" ] && [ "$admin" != root ]; then
  if [ -s "$(getent passwd "$admin" | cut -d: -f6)/.ssh/authorized_keys" ]; then
    ok "管理员 $admin 已有 SSH 钥匙"
  else
    echo "  ! 管理员 $admin 还没有 SSH 钥匙：先别运行 ff-ssh-lockdown"
  fi
fi

cat <<EOF

────────────────────────────────────────────────────────
✔ 安装完成 / done.
  网站目录 $BASE/current（第一次部署之后才有内容）
  现在是 staging 模式：浏览器打开 http://$HOST_IP/ 可以预览（不会被搜索引擎收录）。
  下一步：sudo ff-deploy-key show   （把显示的 3 个机密填进 GitHub）
────────────────────────────────────────────────────────
EOF
