"""Fast VPS state probe — split into small chunks with per-call timeouts."""
import subprocess
import os
import sys

os.environ["SSHPASS"] = "Vk7kEuf554rtP"

SSH = ["sshpass", "-e", "ssh", "-o", "StrictHostKeyChecking=no",
       "-o", "ConnectTimeout=8", "-o", "ServerAliveInterval=5",
       "-p", "13882", "root@91.108.239.5"]


def ssh(cmd, timeout=12):
    try:
        r = subprocess.run(SSH + [cmd], capture_output=True, text=True, timeout=timeout)
        return (r.stdout or "")[:3000] + (("\n[stderr] " + r.stderr[:300]) if r.stderr.strip() else "")
    except subprocess.TimeoutExpired:
        return "[TIMEOUT]"


def section(title, out):
    print(f"\n=== {title} ===", flush=True)
    print(out, flush=True)


section("UFW", ssh("ufw status verbose 2>&1"))
section("LISTENERS", ssh("ss -tln | grep -E ':(80|443|8000|8009|13882) ' || echo NONE"))
section("NGINX ACTIVE", ssh("systemctl is-active nginx; systemctl is-enabled nginx 2>&1"))
section("DOCKER PS", ssh("docker ps -a --format 'table {{.Names}}\\t{{.Status}}\\t{{.Ports}}' 2>&1 | head -15"))
section("CERTBOT", ssh("certbot certificates 2>&1 | head -15"))
section("UIMAILBOT LS", ssh("ls -la /uimailbot 2>&1"))
section("COMPOSE", ssh("cat /uimailbot/docker-compose.yml 2>&1 | head -120"))
section("ENV KEYS", ssh("grep -oE '^[A-Za-z_]+=' /uimailbot/.env 2>&1 || echo 'no .env'"))
section("GIT", ssh("git -C /uimailbot remote -v 2>&1 | head -3; git -C /uimailbot log --oneline -3 2>&1"))
section("OPT/MAILHUB", ssh("ls /opt/mailhub 2>&1 | head; echo '---ENV---'; grep -oE '^[A-Za-z_]+=' /opt/mailhub/mailhub/.env 2>&1; echo '---PROC---'; ps aux | grep '[m]ailhub/main' | head -3; echo '---8009---'; ss -tln | grep 8009 || echo 'nothing on 8009'"))
section("NGINX SITE", ssh("ls /etc/nginx/sites-enabled/ 2>&1; echo '---'; cat /etc/nginx/sites-enabled/uimail 2>/dev/null || echo 'no uimail site'"))
