#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/gold-signal-os}"
SERVICE="${SERVICE:-gold-signal-os}"

python3 - <<'PY'
from pathlib import Path
import os

app_dir = Path(os.environ.get('APP_DIR', '/opt/gold-signal-os'))

paper = app_dir / 'app/api/routes_paper_wallet.py'
s = paper.read_text()
s = s.replace('router = APIRouter(dependencies=[Depends(require_admin_or_local)])', 'router = APIRouter()')
s = s.replace('@router.post("/reset-safe")\n', '@router.post("/reset-safe", dependencies=[Depends(require_admin_or_local)])\n')
if '@router.post("/reset-safe", dependencies=[Depends(require_admin_or_local)])' not in s:
    raise SystemExit('reset-safe admin dependency missing after patch')
paper.write_text(s)

signals = app_dir / 'app/api/routes_signals.py'
s = signals.read_text()
s = s.replace('@router.get("/", dependencies=[Depends(require_admin_or_local)])', '@router.get("/")')
if '@router.get("/", dependencies=[Depends(require_admin_or_local)])' in s:
    raise SystemExit('signals list route still requires Basic auth')
signals.write_text(s)
PY

python3 -m py_compile \
  "$APP_DIR/app/api/routes_paper_wallet.py" \
  "$APP_DIR/app/api/routes_signals.py"

systemctl restart "$SERVICE"
sleep 3
systemctl is-active "$SERVICE"

curl -sk -o /dev/null -w 'paper_wallet=%{http_code}\n' https://goldsignalos.178.104.181.132.nip.io/api/paper-wallet
curl -sk -o /dev/null -w 'signals=%{http_code}\n' "https://goldsignalos.178.104.181.132.nip.io/api/signals/?limit=1"