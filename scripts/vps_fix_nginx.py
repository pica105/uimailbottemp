"""Fix the nginx container config bug and verify the stack end-to-end."""
import subprocess
import os
import time

os.environ["SSHPASS"] = "Vk7kEuf554rtP"

SSH = ["sshpass", "-e", "ssh", "-o", "StrictHostKeyChecking=no",
       "-o", "ConnectTimeout=8", "-p", "13882", "root@91.108.239.5"]


def ssh(cmd, timeout=60):
    try:
        r = subprocess.run(SSH + [cmd], capture_output=True, text=True, timeout=timeout)
        return (r.stdout or "")[:5000] + (("\n[stderr] " + r.stderr[:400]) if r.stderr.strip() else "")
    except subprocess.TimeoutExpired:
        return "[TIMEOUT]"


def section(title, out):
    print(f"\n===== {title} =====", flush=True)
    print(out, flush=True)


# 1. Patch Dockerfile: remove base nginx.conf so entrypoint generates from template
section("PATCH Dockerfile", ssh(
    "cd /uimailbot && sed -i '/RUN rm \\/etc\\/nginx\\/conf.d\\/default.conf/a RUN rm -f /etc/nginx/nginx.conf' nginx/Dockerfile && grep -n 'rm ' nginx/Dockerfile"))

# 2. Rebuild nginx image and recreate container
section("REBUILD nginx", ssh("cd /uimailbot && docker compose up -d --build nginx 2>&1 | tail -10", timeout=240))

time.sleep(8)

# 3. Verify generated config + responses
section("GENERATED nginx.conf (server lines)",
        ssh("docker exec uimailbot-nginx-1 grep -nE 'listen|server_name|ssl_certificate ' /etc/nginx/nginx.conf | head -12"))
section("HTTP :80 (expect 301)", ssh("curl -s -m 8 -o /dev/null -w 'http -> %{http_code} redirect=%{redirect_url}\\n' http://127.0.0.1:80/ 2>&1"))
section("HTTPS :443 (expect 302 to /webapp/)", ssh("curl -sk -m 8 -o /dev/null -w 'https -> %{http_code} redirect=%{redirect_url}\\n' https://127.0.0.1:443/ 2>&1"))
section("HTTPS /webapp/ (expect 200)", ssh("curl -sk -m 8 -o /dev/null -w 'webapp -> %{http_code}\\n' https://127.0.0.1/webapp/ 2>&1"))
section("HTTPS /api/health via nginx (expect 200 json)", ssh("curl -sk -m 8 https://127.0.0.1/api/health 2>&1; echo"))
section("HTTPS /oauth/gmail/callback (route alive)", ssh("curl -sk -m 8 -o /dev/null -w 'oauth cb -> %{http_code}\\n' 'https://127.0.0.1/oauth/gmail/callback?code=x&state=y' 2>&1"))
section("MEM", ssh("free -m | head -2"))
