import subprocess, json, os

token_path = os.path.join(os.path.dirname(__file__), '..', '.github_token')
try:
    with open(token_path) as f:
        token = f.read().strip()
except:
    token = os.environ.get("GITHUB_TOKEN", "")

if not token:
    print("ERROR: No GitHub token found")
    exit(1)

body_text = """## Nami Core v0.1.0 — Full Ecosystem Integration

### New Features
- **Scheduler Daemon**: nami-core runs as systemd service with periodic job scheduler
- **HTTP API**: REST API on port 8092 (GET /health, /workers, /scheduler; POST /dispatch)
- **12 Workers**: lottery, signal, status, proxy, trading, gateway, bridge, graphify, bot, miroshark, gold, default
- **6 Scheduled Jobs**: health check, Lao draw results, VIP lottery send, signal generation, gold prices, MiroShark health
- **Unified Dashboard**: https://nami.178.104.181.132.nip.io/dashboard.html
- **Public API**: https://nami-api.178.104.181.132.nip.io

### Integrations
- nami-bot: /vip, /status, /health, /agents route through nami-core API
- hanoi-bot: fetch_results routes through nami-core API
- MiroShark Oracle: wrapped as miroshark_worker
- Gold Signal OS: wrapped as gold_worker
- maxplus-proxy: proxy_worker uses as primary LLM provider
- LaoPatana DB: lottery_worker queries directly + vip action

### Cron Cleanup
- Deduplicated: 28 → 8 entries
- nami-core-managed jobs removed from crontab

### Tests
- 69 passed"""

payload = json.dumps({
    "tag_name": "v0.1.0",
    "name": "Nami Core v0.1.0 — Ecosystem Orchestrator",
    "body": body_text,
    "draft": False,
    "prerelease": False
})

r = subprocess.run([
    "curl", "-s", "-X", "POST",
    "-H", "Accept: application/vnd.github+json",
    "-H", f"Authorization: Bearer {token}",
    "https://api.github.com/repos/paopaonyapi-creator/nami-core/releases",
    "-d", payload
], capture_output=True, text=True)

d = json.loads(r.stdout)
url = d.get("html_url", "ERROR")
print(f"Release: {url}")
print(f"ID: {d.get('id', '?')}")
