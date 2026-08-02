"""Deploy /uimailbot docker stack on the VPS."""
import subprocess
import os
import time

os.environ["SSHPASS"] = "Vk7kEuf554rtP"

SSH = ["sshpass", "-e", "ssh", "-o", "StrictHostKeyChecking=no",
       "-o", "ConnectTimeout=8", "-p", "13882", "root@91.108.239.5"]


def ssh(cmd, timeout=40):
    try:
        r = subprocess.run(SSH + [cmd], capture_output=True, text=True, timeout=timeout)
        return (r.stdout or "")[:5000] + (("\n[stderr] " + r.stderr[:400]) if r.stderr.strip() else "")
    except subprocess.TimeoutExpired:
        return "[TIMEOUT]"


def section(title, out):
    print(f"\n===== {title} =====", flush=True)
    print(out, flush=True)


# 1. Stop + disable host nginx (frees port 80 for docker nginx)
section("STOP HOST NGINX", ssh("systemctl stop nginx; systemctl disable nginx 2>&1 | tail -2; ss -tlnp | grep ':80 ' || echo 'port 80 free'"))

# 2. Bring up stack without nginx (images already built earlier)
section("COMPOSE UP (no nginx)", ssh("cd /uimailbot && docker compose up -d postgres redis api worker bot miniapp 2>&1 | tail -20", timeout=180))

# 3. Wait for services to be healthy
print("\n=== WAITING FOR SERVICES ===", flush=True)
for i in range(6):
    time.sleep(15)
    st = ssh("cd /uimailbot && docker compose ps --format '{{.Service}} {{.Status}}' 2>&1")
    print(f"--- t={ (i+1)*15 }s ---", flush=True)
    print(st, flush=True)
    if 'postgres' in st and 'redis' in st and ('Up' in st or 'running' in st):
        if 'Unhealthy' not in st and 'restarting' not in st:
            break

# 4. Create dummy cert so nginx container can start (real cert comes via certbot later)
section("DUMMY CERT", ssh("""set -e
CDIR=/var/lib/docker/volumes/uimailbot_certbot_conf/_data/live/uimail.synergyflow.ru
mkdir -p "$CDIR"
if [ ! -f "$CDIR/fullchain.pem" ]; then
  openssl req -x509 -nodes -newkey rsa:2048 -days 30 \\
    -keyout "$CDIR/privkey.pem" -out "$CDIR/fullchain.pem" \\
    -subj "/CN=uimail.synergyflow.ru" 2>&1 | tail -1
fi
ls -la "$CDIR" 2>&1"""))

# 5. Start nginx
section("COMPOSE UP nginx", ssh("cd /uimailbot && docker compose up -d nginx 2>&1 | tail -8", timeout=120))

# 6. Wait a bit and verify
time.sleep(10)
section("COMPOSE PS", ssh("cd /uimailbot && docker compose ps --format '{{.Service}}\\t{{.Status}}\\t{{.Ports}}' 2>&1"))
section("API HEALTH", ssh("curl -s -m 5 http://127.0.0.1:8000/api/health 2>&1; echo"))
section("NGINX HTTP (expect 301)", ssh("curl -s -m 5 -o /dev/null -w 'http -> %{http_code}\\n' http://127.0.0.1:80/ 2>&1"))
section("NGINX HTTPS (dummy cert)", ssh("curl -sk -m 5 -o /dev/null -w 'https -> %{http_code}\\n' https://127.0.0.1:443/ 2>&1"))
section("BOT LOG TAIL", ssh("cd /uimailbot && docker compose logs bot --tail 15 2>&1"))
section("API LOG TAIL", ssh("cd /uimailbot && docker compose logs api --tail 15 2>&1"))
