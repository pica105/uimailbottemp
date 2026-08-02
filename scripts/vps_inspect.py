"""Fetch /uimailbot stack details from the VPS (secrets masked)."""
import subprocess
import os
import re

os.environ["SSHPASS"] = "Vk7kEuf554rtP"

SSH = ["sshpass", "-e", "ssh", "-o", "StrictHostKeyChecking=no",
       "-o", "ConnectTimeout=8", "-p", "13882", "root@91.108.239.5"]


def ssh(cmd, timeout=20):
    try:
        r = subprocess.run(SSH + [cmd], capture_output=True, text=True, timeout=timeout)
        return (r.stdout or "")[:6000]
    except subprocess.TimeoutExpired:
        return "[TIMEOUT]"


def section(title, out):
    print(f"\n===== {title} =====", flush=True)
    print(out, flush=True)


section("FULL docker-compose.yml",
        ssh("cat /uimailbot/docker-compose.yml 2>&1"))

section("nginx dir",
        ssh("ls -la /uimailbot/nginx/ 2>&1; echo '--- nginx.conf ---'; cat /uimailbot/nginx/nginx.conf 2>&1"))

section("nginx entrypoint.sh",
        ssh("cat /uimailbot/nginx/entrypoint.sh 2>&1"))

section("miniapp nginx conf",
        ssh("cat /uimailbot/nginx/miniapp.nginx.conf 2>&1"))

section("env (non-secret values shown)",
        ssh("""grep -vE 'SECRET|PASSWORD|TOKEN|_KEY' /uimailbot/.env 2>&1; echo '--- secret keys present? ---'; grep -cE 'SECRET|PASSWORD|TOKEN|_KEY' /uimailbot/.env 2>&1"""))

section("README TLS section",
        ssh("grep -n -i -A 20 'TLS\\|certbot\\|Let' /uimailbot/README.md 2>&1 | head -60"))

section("SWAP / MEM",
        ssh("free -m 2>&1; echo '---'; cat /proc/swaps 2>&1; echo '---'; ls -la /swapfile /var/swap* 2>&1 | head -5 || echo 'no swap file'"))
