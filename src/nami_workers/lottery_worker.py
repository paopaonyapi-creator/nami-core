"""Lottery Worker — Hanoi + Lao lottery AI prediction engine.

Migrated from /opt/hanoi-bot and /opt/laopatana-stat-lab.
Shared prediction engine for both Hanoi (Vietnam) and Lao lotteries.

Actions:
  - predict: Generate lottery prediction for a region
  - send_prediction: Format and send prediction to channel
  - fetch_results: Fetch latest draw results
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Any

import subprocess

try:
    import psycopg
    from psycopg.rows import dict_row
    _HAS_PSYCOPG = True
except ImportError:  # pragma: no cover - environments without psycopg fall back to psql shell-out
    psycopg = None
    dict_row = None
    _HAS_PSYCOPG = False

from .utils import ai_chat_completion, telegram_send

logger = logging.getLogger(__name__)

# ── VPS Lottery API (from /opt/hanoi-bot) ──
LOTTERY_API_BASE = os.environ.get("LOTTERY_API_BASE", "http://127.0.0.1:3000/api")
HANOI_API_BASE = os.environ.get("HANOI_API_BASE", "http://127.0.0.1:3002/api")

# ── LaoPatana DB (from /opt/nami-army/vip_lottery_sender.py) ──
LAO_DB_NAME = os.environ.get("LAO_DB_NAME", "laopatana_stat_lab")
LAO_DB_HOST = os.environ.get("LAO_DB_HOST", "127.0.0.1")
LAO_DB_USER = os.environ.get("LAO_DB_USER", "postgres")
LAO_DB_PASS_FILE = os.environ.get("LAO_DB_PASS_FILE", "/etc/nami-harness/postgres_password")
VIP_TOKEN_FILE = os.environ.get("VIP_TOKEN_FILE", "/etc/nami-harness/vip_telegram_token")
VIP_CHANNEL = os.environ.get("VIP_CHANNEL", "-1003736959465")


def _read_secret(path: str, default: str = "") -> str:
    try:
        with open(path) as f:
            return f.read().strip()
    except (FileNotFoundError, PermissionError):
        return default


def _lao_db_connect():
    """Open a psycopg connection to LaoPatana DB. Returns None on failure.

    Tries Unix-socket peer auth first (works when running as `postgres`
    system user — matches the `local all postgres peer` rule in pg_hba.conf).
    Falls back to TCP with password from `LAO_DB_PASS_FILE` for environments
    where peer auth is not available.
    """
    if not _HAS_PSYCOPG:
        return None
    # Attempt 1: Unix socket peer auth (no host).
    try:
        return psycopg.connect(
            user=LAO_DB_USER,
            dbname=LAO_DB_NAME,
            connect_timeout=5,
            row_factory=dict_row,
        )
    except psycopg.Error as e:
        logger.info("psycopg socket connect failed (will try TCP): %s", e)

    # Attempt 2: TCP with password from secret file.
    pw = _read_secret(LAO_DB_PASS_FILE)
    if not pw:
        logger.warning("No DB password found at %s", LAO_DB_PASS_FILE)
        return None
    try:
        return psycopg.connect(
            host=LAO_DB_HOST,
            user=LAO_DB_USER,
            password=pw,
            dbname=LAO_DB_NAME,
            connect_timeout=5,
            row_factory=dict_row,
        )
    except psycopg.Error as e:
        logger.warning("psycopg TCP connect failed: %s", e)
        return None


def _lao_db_query(sql: str, params: tuple | list | None = None) -> list[dict[str, Any]] | None:
    """Run a query against LaoPatana DB and return rows as list of dicts.

    Prefers psycopg with parameterised queries; falls back to psql shell-out
    only when psycopg is unavailable AND no params are provided (legacy paths).
    """
    if _HAS_PSYCOPG:
        conn = _lao_db_connect()
        if conn is None:
            return None
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params or ())
                if cur.description is None:
                    return []
                return list(cur.fetchall())
        except psycopg.Error as e:
            logger.warning("DB query failed: %s", e)
            return None
        finally:
            conn.close()

    # Legacy psql fallback (no parameter support)
    if params:
        logger.error("psycopg unavailable; cannot run parameterised query safely")
        return None
    pw = _read_secret(LAO_DB_PASS_FILE)
    if not pw:
        logger.warning("No DB password found at %s", LAO_DB_PASS_FILE)
        return None
    env = {**os.environ, "PGPASSWORD": pw}
    cmd = ["psql", "-h", LAO_DB_HOST, "-U", LAO_DB_USER, "-d", LAO_DB_NAME,
           "-A", "-F", "|", "-P", "footer=off", "-c", sql]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=15)
        if r.returncode != 0:
            logger.warning("DB error: %s", r.stderr[:200])
            return None
        lines = [l for l in r.stdout.strip().split("\n") if l]
        if not lines:
            return []
        cols = [c.strip() for c in lines[0].split("|")]
        result = []
        for line in lines[1:]:
            vals = [v.strip() for v in line.split("|")]
            row = {}
            for i, col in enumerate(cols):
                row[col] = vals[i] if i < len(vals) else ""
            result.append(row)
        return result
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        logger.warning("DB query failed: %s", e)
        return None


def fetch_lao_predictions() -> dict[str, Any]:
    """Fetch latest locked Lao predictions from LaoPatana DB."""
    rows = _lao_db_query("""
        SELECT p.id, p.target_draw_date, p.status,
               rv.config_json->>'engineVersion' as engine_ver
        FROM predictions p
        JOIN rule_versions rv ON p.rule_version_id = rv.id
        WHERE p.status = 'locked'
        ORDER BY p.created_at DESC LIMIT 1
    """)
    if not rows:
        return {"error": "no locked predictions"}

    pred_id = rows[0].get("id", "")
    engine = rows[0].get("engine_ver", "unknown")

    items = _lao_db_query(
        """
        SELECT bet_type, number, rank, score, category
        FROM prediction_items
        WHERE prediction_id = %s AND is_rejected = false
        ORDER BY bet_type, rank
        """,
        (pred_id,),
    )
    if not items:
        return {"error": "no prediction items", "engine": engine}

    picks: dict[str, list[str]] = {"1d": [], "2d_main": [], "2d_secondary": [], "3d": []}
    for item in items:
        bt = item.get("bet_type", "")
        num = item.get("number", "")
        cat = item.get("category", "")
        if bt == "1d":
            picks["1d"].append(num)
        elif bt == "2d" and cat == "main":
            picks["2d_main"].append(num)
        elif bt == "2d" and cat == "secondary":
            picks["2d_secondary"].append(num)
        elif bt == "3d" and cat == "main":
            picks["3d"].append(num)

    return {
        "engine": f"Engine {engine}",
        "target_date": rows[0].get("target_draw_date", ""),
        "1d": picks["1d"][:3],
        "2d_main": picks["2d_main"][:5],
        "2d_secondary": picks["2d_secondary"][:5],
        "3d": picks["3d"][:5],
    }


def fetch_lao_draws(limit: int = 5) -> list[dict[str, Any]]:
    """Fetch latest Lao draw results from LaoPatana DB."""
    rows = _lao_db_query(
        """
        SELECT draw_date, lao_last4, lao_last2, lao_last3, status
        FROM draws
        WHERE status = 'drawn' AND lao_last2 IS NOT NULL
        ORDER BY draw_date DESC LIMIT %s
        """,
        (limit,),
    )
    return rows or []

REGION_CONFIG = {
    "hanoi": {"name_th": "ฮานอย", "draw_types": ["special", "normal", "vip"]},
    "lao": {"name_th": "ลาว", "draw_types": ["main"]},
}


def fetch_draw_results(region: str = "hanoi", limit: int = 30) -> list[dict[str, Any]]:
    """Fetch recent draw results from VPS lottery API."""
    base = HANOI_API_BASE if region == "hanoi" else LOTTERY_API_BASE
    try:
        url = f"{base}/results?limit={limit}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, json.JSONDecodeError):
        logger.warning("Lottery API unavailable for %s results", region)
        return []


def fetch_predictions(region: str = "hanoi") -> dict[str, Any]:
    """Fetch AI predictions from VPS lottery API."""
    base = HANOI_API_BASE if region == "hanoi" else LOTTERY_API_BASE
    preds = {}
    cfg = REGION_CONFIG.get(region, REGION_CONFIG["hanoi"])
    for draw_type in cfg.get("draw_types", ["special"]):
        try:
            url = f"{base}/predict/{draw_type}"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=15) as resp:
                preds[draw_type] = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, json.JSONDecodeError) as e:
            logger.warning("Lottery predict %s unavailable: %s", draw_type, e)
            preds[draw_type] = {"error": str(e)}
    return preds

PREDICTION_SYSTEM_PROMPT = """You are a lottery statistical analysis AI.
Analyze historical patterns for the given region lottery and provide predictions.

You MUST respond in this exact JSON format:
{
  "numbers": [n1, n2, n3, n4, n5, n6],
  "method": "statistical method name",
  "confidence": "Low" or "Very Low",
  "analysis": "brief explanation of the statistical approach"
}

Rules:
- Provide numbers within the valid range for the region
- Never claim high confidence or guarantee results
- Always include risk disclaimer
- This is for entertainment and statistical research only
"""

PREDICTION_TEMPLATE = """🎰 Nami Lottery Prediction — {region}

Numbers: {prediction}
Method: {method}
Confidence: {confidence}

⚠️ หมายเหตุ: AI statistical analysis ไม่ใช่การันตีผล
จัดการ risk ตามความเหมาะสม"""

REGIONS = {
    "hanoi": {"name": "Hanoi (Hà Nội)", "format": "6 numbers", "range": "1-99"},
    "lao": {"name": "Lao (ລາວ)", "format": "5 numbers", "range": "1-55"},
}


def predict(payload: dict[str, Any]) -> dict[str, Any]:
    """Generate lottery prediction for a region.

    Payload keys:
      - region: "hanoi" or "lao"

    Returns dict with: prediction, region, method, confidence
    """
    region = payload.get("region", "hanoi")

    if region not in REGIONS:
        return {"error": f"unknown region: {region}", "valid_regions": list(REGIONS.keys())}

    region_info = REGIONS[region]

    logger.info("Prediction request for %s", region_info["name"])

    # For Lao: use LaoPatana DB engine predictions directly
    if region == "lao":
        lao_preds = fetch_lao_predictions()
        if "error" not in lao_preds:
            lao_draws = fetch_lao_draws(5)
            numbers = lao_preds.get("1d", [])[:6]
            if not numbers:
                import random
                numbers = sorted(random.sample(range(1, 56), 5))
            return {
                "prediction": ", ".join(str(n) for n in numbers),
                "region": "lao",
                "method": lao_preds.get("engine", "LaoPatana Engine"),
                "confidence": "Low",
                "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "db_picks": lao_preds,
                "recent_draws": lao_draws[:3],
            }

    # For Hanoi: try VPS lottery API predictions first
    vps_preds = fetch_predictions(region)
    vps_results = fetch_draw_results(region, limit=10)

    # Build enriched prompt with VPS data
    context = f"Generate prediction for {region_info['name']} lottery. Format: {region_info['format']}, Range: {region_info['range']}"
    if vps_preds and not all("error" in v for v in vps_preds.values()):
        context += f"\n\n=== VPS Engine Predictions ===\n{json.dumps(vps_preds, ensure_ascii=False)[:800]}"
    if vps_results:
        context += f"\n\n=== Recent Results (last 5) ===\n{json.dumps(vps_results[:5], ensure_ascii=False)[:500]}"

    messages = [
        {"role": "system", "content": PREDICTION_SYSTEM_PROMPT},
        {"role": "user", "content": context},
    ]

    ai_result = ai_chat_completion(messages, model="claude-3-sonnet")
    content = ai_result.get("content", "")

    # Parse AI response
    try:
        json_str = content
        if "```json" in content:
            json_str = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            json_str = content.split("```")[1].split("```")[0]
        data = json.loads(json_str.strip())
        numbers = data.get("numbers", [])
        method = data.get("method", "AI statistical analysis")
        confidence = data.get("confidence", "Low")
    except (json.JSONDecodeError, IndexError):
        # Fallback: random numbers
        import random
        max_num = 100 if region == "hanoi" else 56
        count = 6 if region == "hanoi" else 5
        numbers = sorted(random.sample(range(1, max_num), count))
        method = "AI statistical analysis"
        confidence = "Low"

    prediction = ", ".join(str(n) for n in numbers)

    return {
        "prediction": prediction,
        "region": region,
        "method": method,
        "confidence": confidence,
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }


def send_prediction(payload: dict[str, Any]) -> dict[str, Any]:
    """Format and send prediction to subscriber channel.

    Payload keys:
      - prediction: prediction dict from predict()
      - channel: target Telegram channel/chat ID

    Returns dict with: sent, message
    """
    pred_data = payload.get("prediction", {})
    channel = payload.get("channel", os.environ.get("LOTTERY_CHANNEL", ""))

    if not pred_data.get("prediction"):
        return {"sent": False, "message": "No prediction data provided"}

    if not channel:
        return {"sent": False, "message": "No target channel configured"}

    message = PREDICTION_TEMPLATE.format(
        region=REGIONS.get(pred_data.get("region", "hanoi"), {}).get("name", "Unknown"),
        prediction=pred_data.get("prediction", "N/A"),
        method=pred_data.get("method", "N/A"),
        confidence=pred_data.get("confidence", "N/A"),
    )

    result = telegram_send(channel, message)

    if result.get("ok"):
        logger.info("Prediction sent to channel %s", channel)
        return {"sent": True, "message": message, "channel": channel}
    else:
        return {"sent": False, "message": f"Send failed: {result.get('error')}", "channel": channel}


def fetch_results(payload: dict[str, Any]) -> dict[str, Any]:
    """Fetch latest draw results for a region.

    Payload keys:
      - region: "hanoi" or "lao"

    Returns dict with: results, region, draw_date
    """
    region = payload.get("region", "hanoi")

    if region not in REGIONS:
        return {"error": f"unknown region: {region}"}

    # For Lao: use LaoPatana DB directly
    if region == "lao":
        draws = fetch_lao_draws(30)
        logger.info("Fetched %d Lao draws from DB", len(draws))
        return {
            "results": draws[:10],
            "total": len(draws),
            "region": "lao",
            "draw_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        }

    # Use VPS lottery API (from /opt/hanoi-bot/hanoi_scraper_kqxs.py)
    results = fetch_draw_results(region, limit=30)
    logger.info("Fetched %d results for %s", len(results), region)

    return {
        "results": results[:10],
        "total": len(results),
        "region": region,
        "draw_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }


def vip(payload: dict[str, Any]) -> dict[str, Any]:
    """Fetch Lao VIP prediction from LaoPatana DB and optionally send to channel.

    Payload keys:
      - send: (optional) if true, send formatted message to VIP channel

    Returns dict with: engine, picks, latest_draw, sent
    """
    preds = fetch_lao_predictions()
    draws = fetch_lao_draws(1)

    if "error" in preds:
        return {"error": preds["error"], "engine": preds.get("engine", "unknown")}

    latest = draws[0] if draws else {}

    result = {
        "engine": preds.get("engine", "unknown"),
        "target_date": preds.get("target_date", ""),
        "1d": preds.get("1d", []),
        "2d_main": preds.get("2d_main", []),
        "2d_secondary": preds.get("2d_secondary", []),
        "3d": preds.get("3d", []),
        "latest_draw": latest,
    }

    if payload.get("send"):
        msg = f"🎯 LaoPatana VIP — {preds.get('target_date', '')}\n"
        msg += f"🔮 {preds.get('engine', '')}\n\n━━━━━━━━━━━━━━\n\n"
        if preds.get("1d"):
            msg += f"🔥 *1D วิ่ง:* `{', '.join(preds['1d'])}`\n"
        if preds.get("2d_main"):
            msg += f"🎲 *2D หลัก:* `{', '.join(preds['2d_main'])}`\n"
        if preds.get("2d_secondary"):
            msg += f"🎲 *2D รอง:* `{', '.join(preds['2d_secondary'])}`\n"
        if preds.get("3d"):
            msg += f"🎰 *3D Exact:* `{', '.join(preds['3d'])}`\n"
        msg += "\n━━━━━━━━━━━━━━\n\n"
        msg += "⚠️ AI statistical analysis ไม่ใช่การันตีผล\n"
        msg += "🌸 @LuxkyLaosbypao_bot"

        token = _read_secret(VIP_TOKEN_FILE)
        if token:
            send_result = telegram_send(VIP_CHANNEL, msg, bot_token=token)
            result["sent"] = send_result.get("ok", False)
        else:
            result["sent"] = False
            result["send_error"] = "no VIP bot token"

    return result


def latest_prediction(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the latest prediction in tile-friendly shape.

    Payload keys:
      - region: 'lao' (DB-backed locked picks) or 'hanoi' (live VPS API top picks)

    Returns:
      - lao   → { source: 'laopatana_db', data: { engine, target_date, 1d, 2d_main, 2d_secondary, 3d, latest_draw }, timestamp }
      - hanoi → { source: 'hanoi_api',    data: { engine, target_date, draw_types: {special, normal, vip}, latest_results }, timestamp }
    """
    region = payload.get("region", "lao")
    now_iso = datetime.now(timezone.utc).isoformat()

    if region == "hanoi":
        preds = fetch_predictions(region="hanoi")
        draw_types: dict[str, Any] = {}
        latest_results: dict[str, str | None] = {}
        any_ok = False
        for dt, raw in (preds or {}).items():
            if not isinstance(raw, dict) or "error" in raw:
                draw_types[dt] = {"error": (raw or {}).get("error", "unavailable") if isinstance(raw, dict) else "unavailable"}
                latest_results[dt] = None
                continue
            top = (raw.get("predictions") or [])[:5]
            draw_types[dt] = {
                "top": [
                    {
                        "number": str(p.get("number", "")),
                        "confidence": round(float(p.get("confidence", 0.0)), 1),
                        "label": p.get("label"),
                    }
                    for p in top
                ],
                "generated_at": raw.get("generatedAt"),
                "record_count": raw.get("recordCount"),
            }
            latest_results[dt] = raw.get("latestResult")
            any_ok = True
        if not any_ok:
            return {
                "source": "hanoi_api",
                "data": None,
                "timestamp": now_iso,
                "error": "Hanoi predict API unavailable",
            }
        return {
            "source": "hanoi_api",
            "data": {
                "engine": "hanoi-stats",
                "target_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "draw_types": draw_types,
                "latest_results": latest_results,
            },
            "timestamp": now_iso,
        }

    if region != "lao":
        return {
            "source": "unsupported",
            "data": None,
            "timestamp": now_iso,
            "note": f"region {region} ไม่รองรับ (มีแค่ lao | hanoi)",
        }

    preds = fetch_lao_predictions()
    if "error" in preds:
        return {
            "source": "laopatana_db",
            "data": None,
            "timestamp": now_iso,
            "error": preds["error"],
        }

    draws = fetch_lao_draws(1)
    return {
        "source": "laopatana_db",
        "data": {**preds, "latest_draw": draws[0] if draws else None},
        "timestamp": now_iso,
    }


def accuracy_stats(payload: dict[str, Any]) -> dict[str, Any]:
    """Compute hit-rate per bet_type over the last N completed draws.

    A 1d "hit" = predicted digit appears in draws.lao_last2.
    A 2d "hit" = predicted 2-digit number == draws.lao_last2.
    A 3d "hit" = predicted 3-digit number == draws.lao_last3.

    Payload keys:
      - region: 'lao' (default)
      - last_n: window size (default 30)

    Returns: { hit_rate, hits, total, by_bet_type:{1d,2d,3d}, streak, last_hit_date }
    """
    region = payload.get("region", "lao")
    last_n = int(payload.get("last_n", 30))

    if region != "lao":
        return {"error": f"region {region} ไม่รองรับ accuracy_stats"}

    rows = _lao_db_query(
        """
        SELECT p.id, p.target_draw_date, d.lao_last2, d.lao_last3
        FROM predictions p
        JOIN draws d ON d.draw_date = p.target_draw_date
        WHERE p.status = 'locked' AND d.status = 'drawn'
              AND d.lao_last2 IS NOT NULL
        ORDER BY p.target_draw_date DESC
        LIMIT %s
        """,
        (last_n,),
    )
    if rows is None:
        return {"error": "DB unavailable"}
    if not rows:
        return {"hit_rate": 0.0, "hits": 0, "total": 0, "by_bet_type": {},
                "streak": 0, "last_hit_date": None, "window": last_n}

    by_bt = {"1d": {"hits": 0, "total": 0}, "2d": {"hits": 0, "total": 0},
             "3d": {"hits": 0, "total": 0}}
    per_draw_hits: list[tuple[str, bool]] = []  # (date, any_hit)
    last_hit_date: str | None = None

    for row in rows:
        pid = row.get("id", "")
        last2 = str(row.get("lao_last2") or "").strip()
        last3 = str(row.get("lao_last3") or "").strip()
        date_str = str(row.get("target_draw_date") or "")
        items = _lao_db_query(
            """
            SELECT bet_type, number, category
            FROM prediction_items
            WHERE prediction_id = %s AND is_rejected = false
            """,
            (pid,),
        ) or []
        any_hit = False
        for it in items:
            bt = it.get("bet_type", "")
            num = str(it.get("number") or "").strip()
            if bt not in by_bt:
                continue
            by_bt[bt]["total"] += 1
            hit = False
            if bt == "1d" and num and last2 and num in last2:
                hit = True
            elif bt == "2d" and num and last2 and num == last2:
                hit = True
            elif bt == "3d" and num and last3 and num == last3:
                hit = True
            if hit:
                by_bt[bt]["hits"] += 1
                any_hit = True
        per_draw_hits.append((date_str, any_hit))
        if any_hit and last_hit_date is None:
            last_hit_date = date_str

    total_hits = sum(v["hits"] for v in by_bt.values())
    total_items = sum(v["total"] for v in by_bt.values())
    rate = (total_hits / total_items) if total_items else 0.0

    streak = 0
    for _, hit in per_draw_hits:
        if hit:
            streak += 1
        else:
            break

    return {
        "region": region,
        "window": last_n,
        "hit_rate": round(rate, 4),
        "hits": total_hits,
        "total": total_items,
        "by_bet_type": {k: {"hits": v["hits"], "total": v["total"],
                            "rate": round(v["hits"] / v["total"], 4) if v["total"] else 0.0}
                        for k, v in by_bt.items()},
        "streak": streak,
        "last_hit_date": last_hit_date,
    }


def history(payload: dict[str, Any]) -> dict[str, Any]:
    """Return last N predictions paired with the actual draw + per-row hit/miss flag.

    Payload keys:
      - region: 'lao' (default)
      - limit: 20

    Returns: { region, items: [{date, picks:{1d,2d_main,2d_secondary,3d}, draw:{lao_last2,lao_last3,lao_last4}, any_hit:bool}] }
    """
    region = payload.get("region", "lao")
    limit = int(payload.get("limit", 20))

    if region != "lao":
        return {"error": f"region {region} ไม่รองรับ history"}

    rows = _lao_db_query(
        """
        SELECT p.id, p.target_draw_date,
               d.lao_last2, d.lao_last3, d.lao_last4
        FROM predictions p
        LEFT JOIN draws d ON d.draw_date = p.target_draw_date
        WHERE p.status = 'locked'
        ORDER BY p.target_draw_date DESC
        LIMIT %s
        """,
        (limit,),
    )
    if rows is None:
        return {"error": "DB unavailable"}

    items = []
    for row in rows:
        pid = row.get("id", "")
        last2 = str(row.get("lao_last2") or "").strip()
        last3 = str(row.get("lao_last3") or "").strip()
        last4 = str(row.get("lao_last4") or "").strip()
        ipicks = _lao_db_query(
            """
            SELECT bet_type, number, category, rank
            FROM prediction_items
            WHERE prediction_id = %s AND is_rejected = false
            ORDER BY bet_type, rank
            """,
            (pid,),
        ) or []
        picks = {"1d": [], "2d_main": [], "2d_secondary": [], "3d": []}
        for it in ipicks:
            bt = it.get("bet_type", "")
            cat = it.get("category", "")
            num = str(it.get("number") or "")
            if bt == "1d":
                picks["1d"].append(num)
            elif bt == "2d" and cat == "main":
                picks["2d_main"].append(num)
            elif bt == "2d" and cat == "secondary":
                picks["2d_secondary"].append(num)
            elif bt == "3d":
                picks["3d"].append(num)

        any_hit = False
        if last2:
            if any(d and d in last2 for d in picks["1d"]):
                any_hit = True
            if last2 in picks["2d_main"] or last2 in picks["2d_secondary"]:
                any_hit = True
        if last3 and last3 in picks["3d"]:
            any_hit = True

        items.append({
            "date": str(row.get("target_draw_date") or ""),
            "picks": picks,
            "draw": {"lao_last2": last2, "lao_last3": last3, "lao_last4": last4} if last2 else None,
            "any_hit": any_hit,
        })

    return {"region": region, "items": items, "count": len(items)}


def hot_cold(payload: dict[str, Any]) -> dict[str, Any]:
    """Compute digit frequency from draws.lao_last2 over a window of days.

    Payload keys:
      - region: 'lao' (default)
      - window_days: 90

    Returns: { window_days, total_draws, hot:[{digit,count}...], cold:[...], all:[...] }
    """
    region = payload.get("region", "lao")
    window_days = int(payload.get("window_days", 90))

    if region != "lao":
        return {"error": f"region {region} ไม่รองรับ hot_cold"}

    rows = _lao_db_query(
        """
        SELECT lao_last2, lao_last4
        FROM draws
        WHERE status = 'drawn'
              AND draw_date >= (CURRENT_DATE - (%s || ' days')::interval)
              AND lao_last2 IS NOT NULL
        """,
        (window_days,),
    )
    if rows is None:
        return {"error": "DB unavailable"}

    counts = {str(d): 0 for d in range(10)}
    for r in rows:
        for src_key in ("lao_last2", "lao_last4"):
            v = str(r.get(src_key) or "")
            for ch in v:
                if ch.isdigit():
                    counts[ch] = counts.get(ch, 0) + 1

    sorted_desc = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    return {
        "region": region,
        "window_days": window_days,
        "total_draws": len(rows),
        "hot": [{"digit": d, "count": c} for d, c in sorted_desc[:3]],
        "cold": [{"digit": d, "count": c} for d, c in sorted_desc[-3:]],
        "all": [{"digit": d, "count": c} for d, c in sorted_desc],
    }


ACTIONS: dict[str, callable] = {
    "predict": predict,
    "send_prediction": send_prediction,
    "fetch_results": fetch_results,
    "vip": vip,
    "latest_prediction": latest_prediction,
    "accuracy_stats": accuracy_stats,
    "history": history,
    "hot_cold": hot_cold,
}


def lottery_worker(payload: dict[str, Any]) -> dict[str, Any]:
    """Main worker entry point."""
    action = payload.get("action", "predict")

    handler = ACTIONS.get(action)
    if handler is None:
        return {"error": f"unknown action: {action}"}

    return handler(payload)
