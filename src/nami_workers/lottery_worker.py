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
from itertools import product
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



def _ensure_v6_log_table() -> bool:
    """Create v6_prediction_log table if not exists. Returns True on success.

    Idempotent ALTER also adds `is_backfill` column for older installs.
    """
    if not _HAS_PSYCOPG:
        return False
    conn = _lao_db_connect()
    if conn is None:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS v6_prediction_log (
                    id SERIAL PRIMARY KEY,
                    target_date DATE NOT NULL UNIQUE,
                    picks_1d TEXT[] DEFAULT '{}',
                    picks_2d TEXT[] DEFAULT '{}',
                    picks_3d TEXT[] DEFAULT '{}',
                    scores JSONB DEFAULT '{}',
                    is_backfill BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            cur.execute("""
                ALTER TABLE v6_prediction_log
                ADD COLUMN IF NOT EXISTS is_backfill BOOLEAN DEFAULT FALSE
            """)
        conn.commit()
        return True
    except Exception as e:
        logger.warning("v6_log table create failed: %s", e)
        return False
    finally:
        conn.close()


def _save_v6_prediction(
    target_date: str,
    picks_1d: list,
    picks_2d: list,
    picks_3d: list,
    scores: dict,
    is_backfill: bool = False,
    force: bool = True,
) -> str:
    """Upsert a v6 prediction row into v6_prediction_log.

    Returns one of: "inserted", "updated", "skipped", "failed".
    - force=True (default for live predict_v6): ON CONFLICT DO UPDATE overwrites existing row.
    - force=False (used by backtest_v6): ON CONFLICT DO NOTHING preserves real predictions.
    """
    if not _HAS_PSYCOPG:
        return "failed"
    _ensure_v6_log_table()
    conn = _lao_db_connect()
    if conn is None:
        return "failed"
    try:
        with conn.cursor() as cur:
            if force:
                cur.execute(
                    """
                    INSERT INTO v6_prediction_log (target_date, picks_1d, picks_2d, picks_3d, scores, is_backfill)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (target_date) DO UPDATE
                    SET picks_1d = EXCLUDED.picks_1d,
                        picks_2d = EXCLUDED.picks_2d,
                        picks_3d = EXCLUDED.picks_3d,
                        scores   = EXCLUDED.scores,
                        is_backfill = EXCLUDED.is_backfill
                    RETURNING (xmax = 0) AS inserted
                    """,
                    (target_date, picks_1d, picks_2d, picks_3d, json.dumps(scores), is_backfill),
                )
                row = cur.fetchone()
                conn.commit()
                if row is None:
                    return "failed"
                inserted = row["inserted"] if isinstance(row, dict) else row[0]
                return "inserted" if inserted else "updated"
            else:
                cur.execute(
                    """
                    INSERT INTO v6_prediction_log (target_date, picks_1d, picks_2d, picks_3d, scores, is_backfill)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (target_date) DO NOTHING
                    """,
                    (target_date, picks_1d, picks_2d, picks_3d, json.dumps(scores), is_backfill),
                )
                rc = cur.rowcount
                conn.commit()
                return "inserted" if rc > 0 else "skipped"
    except Exception as e:
        logger.warning("save_v6_prediction failed: %s", e)
        return "failed"
    finally:
        conn.close()


DEFAULT_V6_WEIGHTS: dict[str, float] = {
    "freq_30d": 1.0,
    "freq_7d": 2.0,
    "digit_count": 0.5,
    "markov": 10.0,
    "gap": 0.0,
    "pair": 0.0,
}


def _normalize_v6_weights(value: Any = None) -> dict[str, float]:
    weights = dict(DEFAULT_V6_WEIGHTS)
    if not isinstance(value, dict):
        return weights
    for key in weights:
        raw = value.get(key)
        if raw is None:
            continue
        try:
            weights[key] = max(-100.0, min(100.0, float(raw)))
        except (TypeError, ValueError):
            continue
    return weights


def _v6_compute(history_draws: list[dict[str, Any]], weights: dict[str, Any] | None = None) -> dict[str, Any]:
    """Pure v6 ensemble: takes history (DESC order, latest-first) and returns picks.

    No DB writes, no `datetime.now()` calls. Used by both live predict_v6 and backtest_v6.
    """
    weights_used = _normalize_v6_weights(weights)
    if not history_draws:
        return {"1d": [], "2d": [], "3d": [], "scores": {}, "weights_used": weights_used}

    freq_30d = {str(d): 0 for d in range(10)}
    for draw in history_draws[:30]:
        for src in ("lao_last2", "lao_last4"):
            v = str(draw.get(src) or "")
            for ch in v:
                if ch.isdigit():
                    freq_30d[ch] = freq_30d.get(ch, 0) + 1

    freq_7d = {str(d): 0 for d in range(10)}
    for i, draw in enumerate(history_draws[:7]):
        weight = 3 - i * 0.3
        for src in ("lao_last2", "lao_last4"):
            v = str(draw.get(src) or "")
            for ch in v:
                if ch.isdigit():
                    freq_7d[ch] = freq_7d.get(ch, 0) + weight

    transitions: dict[str, dict[str, float]] = {}
    digit_counts: dict[str, int] = {}
    for draw in history_draws:
        last4 = str(draw.get("lao_last4") or "")
        if len(last4) < 4:
            continue
        for i, ch in enumerate(last4):
            if not ch.isdigit():
                continue
            digit_counts[ch] = digit_counts.get(ch, 0) + 1
            if i + 1 < len(last4):
                nxt = last4[i + 1]
                if not nxt.isdigit():
                    continue
                if ch not in transitions:
                    transitions[ch] = {}
                transitions[ch][nxt] = transitions[ch].get(nxt, 0) + 1

    for ch, nxt_map in transitions.items():
        total = sum(nxt_map.values())
        if total:
            for nxt, cnt in nxt_map.items():
                nxt_map[nxt] = cnt / total

    latest_draw = history_draws[0] if history_draws else {}
    latest_last4 = str(latest_draw.get("lao_last4") or "")
    latest_last_digit = latest_last4[-1] if latest_last4 and latest_last4[-1].isdigit() else None

    digit_scores: dict[str, float] = {}
    gap_scores: dict[str, float] = {str(d): 0.0 for d in range(10)}
    if weights_used["gap"]:
        positions: dict[str, list[int]] = {str(d): [] for d in range(10)}
        for idx, draw in enumerate(history_draws):
            seen_in_draw: set[str] = set()
            for src in ("lao_last2", "lao_last4"):
                v = str(draw.get(src) or "")
                for ch in v:
                    if ch.isdigit():
                        seen_in_draw.add(ch)
            for ch in seen_in_draw:
                positions.setdefault(ch, []).append(idx)
        for ds, pos in positions.items():
            if not pos:
                gap_scores[ds] = float(len(history_draws))
                continue
            current_gap = float(pos[0])
            if len(pos) >= 2:
                diffs = [pos[i + 1] - pos[i] for i in range(len(pos) - 1)]
                avg_gap = sum(diffs) / len(diffs)
            else:
                avg_gap = max(1.0, float(len(history_draws)))
            gap_scores[ds] = current_gap / max(1.0, avg_gap)

    for d in range(10):
        ds = str(d)
        score = 0.0
        score += freq_30d.get(ds, 0) * weights_used["freq_30d"]
        score += freq_7d.get(ds, 0) * weights_used["freq_7d"]
        score += digit_counts.get(ds, 0) * weights_used["digit_count"]
        if latest_last_digit and latest_last_digit in transitions:
            score += transitions[latest_last_digit].get(ds, 0) * weights_used["markov"]
        score += gap_scores.get(ds, 0.0) * weights_used["gap"]
        digit_scores[ds] = score

    top_digits = sorted(digit_scores.items(), key=lambda kv: kv[1], reverse=True)
    top_1d = [d for d, _ in top_digits[:3]]

    top_2d: list[str] = []
    if weights_used["pair"]:
        pair_counts: dict[str, int] = {}
        for draw in history_draws[:14]:
            last2 = str(draw.get("lao_last2") or "")
            if len(last2) == 2 and last2.isdigit():
                pair_counts[last2] = pair_counts.get(last2, 0) + 1
        candidates: list[tuple[str, float]] = []
        top_digit_scores = dict(top_digits)
        for d1, _ in top_digits[:5]:
            for d2, _ in top_digits[:5]:
                num = f"{d1}{d2}"
                score = top_digit_scores.get(d1, 0.0) + top_digit_scores.get(d2, 0.0)
                score += pair_counts.get(num, 0) * weights_used["pair"]
                candidates.append((num, score))
        top_2d = [num for num, _ in sorted(candidates, key=lambda kv: kv[1], reverse=True)[:4]]
    else:
        seen_2d: set[str] = set()
        for d1, _ in top_digits[:5]:
            for d2, _ in top_digits[:5]:
                num = f"{d1}{d2}"
                if num not in seen_2d:
                    seen_2d.add(num)
                    top_2d.append(num)
                if len(top_2d) >= 4:
                    break
            if len(top_2d) >= 4:
                break

    top_3d: list[str] = []
    seen_3d: set[str] = set()
    for d1, _ in top_digits[:4]:
        for d2, _ in top_digits[:4]:
            for d3, _ in top_digits[:4]:
                num = f"{d1}{d2}{d3}"
                if num not in seen_3d:
                    seen_3d.add(num)
                    top_3d.append(num)
                if len(top_3d) >= 2:
                    break
            if len(top_3d) >= 2:
                break
        if len(top_3d) >= 2:
            break

    return {
        "1d": top_1d,
        "2d": top_2d,
        "3d": top_3d,
        "scores": {d: round(s, 2) for d, s in top_digits[:5]},
        "weights_used": weights_used,
    }


def predict_v6(payload):
    if payload.get("test_mode") and os.environ.get("NAMI_BACKTEST_TEST_MODE") == "1":
        return {"ok": True, "test_mode": True}


    region = payload.get("region", "lao")
    if region != "lao":
        return {"error": "v6 engine currently supports only lao", "region": region}
    draws = fetch_lao_draws(100)
    if not draws:
        return {"error": "no draw data available", "region": region}

    picks = _v6_compute(draws, payload.get("weights"))
    top_1d = picks["1d"]
    top_2d = picks["2d"]
    top_3d = picks["3d"]
    scores_top = picks["scores"]

    target_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if payload.get("save", True):
        _save_v6_prediction(target_date, top_1d, top_2d, top_3d, scores_top, is_backfill=False, force=True)

    return {
        "engine": "Engine v6 (ensemble)",
        "target_date": target_date,
        "1d": top_1d,
        "2d_main": top_2d,
        "2d_secondary": [],
        "3d": top_3d,
        "scores": scores_top,
        "weights_used": picks.get("weights_used", DEFAULT_V6_WEIGHTS),
    }


def _load_lao_backtest_rows() -> list[dict[str, Any]] | None:
    return _lao_db_query(
        """
        SELECT draw_date, lao_last4, lao_last2, lao_last3
        FROM draws
        WHERE status = 'drawn' AND lao_last2 IS NOT NULL
        ORDER BY draw_date ASC
        """,
        (),
    )


def _run_v6_backtest_rows(
    rows: list[dict[str, Any]],
    *,
    region: str,
    days: int,
    min_history: int,
    dry_run: bool,
    force: bool,
    weights: dict[str, Any] | None = None,
) -> dict[str, Any]:
    weights_used = _normalize_v6_weights(weights)
    if not rows:
        return {"error": "no drawn results available"}

    total_draws = len(rows)
    if total_draws <= min_history:
        return {
            "error": f"need >{min_history} drawn results to backtest, have {total_draws}",
            "total_draws_available": total_draws,
            "min_history": min_history,
        }

    if days > 0:
        start_idx = max(min_history, total_draws - days)
    else:
        start_idx = min_history

    eligible = total_draws - start_idx
    inserted = updated = skipped = failed = 0
    hits_1d = hits_2d = hits_3d = 0
    samples: list[dict[str, Any]] = []

    for i in range(start_idx, total_draws):
        target = rows[i]
        target_date_str = str(target.get("draw_date") or "")
        history = list(reversed(rows[:i]))  # DESC: latest-first

        picks = _v6_compute(history, weights_used)
        p1 = picks["1d"]
        p2 = picks["2d"]
        p3 = picks["3d"]

        last2 = str(target.get("lao_last2") or "").strip()
        last3 = str(target.get("lao_last3") or "").strip()
        hit1 = any(d in last2 for d in p1 if d)
        hit2 = any(n == last2 for n in p2 if n)
        hit3 = any(n == last3 for n in p3 if n)
        if hit1:
            hits_1d += 1
        if hit2:
            hits_2d += 1
        if hit3:
            hits_3d += 1

        if not dry_run:
            status = _save_v6_prediction(
                target_date_str, p1, p2, p3, picks["scores"],
                is_backfill=True, force=force,
            )
            if status == "inserted":
                inserted += 1
            elif status == "updated":
                updated += 1
            elif status == "skipped":
                skipped += 1
            else:
                failed += 1

        samples.append({
            "date": target_date_str,
            "picks_1d": p1,
            "picks_2d": p2[:3],
            "picks_3d": p3[:2],
            "actual_last2": last2,
            "actual_last3": last3,
            "hit_1d": hit1,
            "hit_2d": hit2,
            "hit_3d": hit3,
        })

    return {
        "region": region,
        "dry_run": dry_run,
        "force": force,
        "weights_used": weights_used,
        "total_draws_available": total_draws,
        "min_history": min_history,
        "eligible_draws": eligible,
        "inserted": inserted,
        "updated": updated,
        "skipped_existing": skipped,
        "failed": failed,
        "date_range": [str(rows[start_idx].get("draw_date") or ""), str(rows[-1].get("draw_date") or "")] if eligible else None,
        "backtest_accuracy": {
            "total": eligible,
            "hits_1d": hits_1d,
            "hits_2d": hits_2d,
            "hits_3d": hits_3d,
            "hit_rate_1d": round(hits_1d / eligible, 4) if eligible else 0.0,
            "hit_rate_2d": round(hits_2d / eligible, 4) if eligible else 0.0,
            "hit_rate_3d": round(hits_3d / eligible, 4) if eligible else 0.0,
        },
        "samples": samples[-20:],
    }


def backtest_v6(payload: dict[str, Any]) -> dict[str, Any]:
    """Replay v6 engine against historical draws and (optionally) backfill v6_prediction_log.

    Payload keys:
      - region: only 'lao' supported (default)
      - days: how many recent draws to evaluate (default 60, 0 = all)
      - min_history: minimum draws needed before predicting (default 30)
      - dry_run: if true, compute results without writing to DB (default false)
      - force: if true, overwrite existing predictions for those dates (default false)

    Returns a summary including backtest hit rates and per-date samples.
    """
    if payload.get("test_mode") and os.environ.get("NAMI_BACKTEST_TEST_MODE") == "1":
        return {"ok": True, "test_mode": True}

    region = payload.get("region", "lao")
    if region != "lao":
        return {"error": "backtest only supports lao", "region": region}

    days = max(0, min(365, int(payload.get("days", 60))))
    min_history = max(10, min(180, int(payload.get("min_history", 30))))
    dry_run = bool(payload.get("dry_run", False))
    force = bool(payload.get("force", False))
    weights = payload.get("weights") if isinstance(payload.get("weights"), dict) else None
    weights_used = _normalize_v6_weights(weights)
    if not dry_run and weights_used != DEFAULT_V6_WEIGHTS:
        return {"error": "custom weights are dry-run only; refusing to write tuned backfill rows", "weights_used": weights_used}

    rows = _load_lao_backtest_rows()
    if rows is None:
        return {"error": "DB unavailable"}
    return _run_v6_backtest_rows(
        rows,
        region=region,
        days=days,
        min_history=min_history,
        dry_run=dry_run,
        force=force,
        weights=weights_used,
    )


def _grid_candidates(grid: dict[str, Any]) -> list[dict[str, float]]:
    keys = [key for key in DEFAULT_V6_WEIGHTS if isinstance(grid.get(key), list) and grid.get(key)]
    if not keys:
        return [dict(DEFAULT_V6_WEIGHTS)]
    value_lists: list[list[float]] = []
    for key in keys:
        values: list[float] = []
        for raw in grid.get(key, []):
            try:
                values.append(max(-100.0, min(100.0, float(raw))))
            except (TypeError, ValueError):
                continue
        if not values:
            values = [DEFAULT_V6_WEIGHTS[key]]
        value_lists.append(values[:8])
    candidates: list[dict[str, float]] = []
    for combo in product(*value_lists):
        weights = dict(DEFAULT_V6_WEIGHTS)
        for idx, key in enumerate(keys):
            weights[key] = combo[idx]
        candidates.append(weights)
        if len(candidates) >= 64:
            break
    return candidates


def _preset_grid(name: str) -> dict[str, list[float]]:
    if name == "fine":
        return {
            "freq_30d": [0.9, 1.1],
            "freq_7d": [1.8, 2.2],
            "digit_count": [0.4, 0.6],
            "markov": [8.0, 12.0],
            "gap": [0.0, 0.5],
            "pair": [0.0],
        }
    return {
        "freq_30d": [0.8, 1.2],
        "freq_7d": [1.5, 2.5],
        "digit_count": [0.3, 0.7],
        "markov": [6.0, 12.0],
        "gap": [0.0, 0.8],
        "pair": [0.0, 1.5],
    }


def sweep_v6_weights(payload: dict[str, Any]) -> dict[str, Any]:
    region = payload.get("region", "lao")
    if region != "lao":
        return {"error": "sweep only supports lao", "region": region}

    days = max(30, min(365, int(payload.get("days", 90))))
    min_history = max(10, min(180, int(payload.get("min_history", 30))))
    top_k = max(1, min(10, int(payload.get("top_k", 5))))
    preset = str(payload.get("preset") or "coarse")
    grid = payload.get("sweep_grid") if isinstance(payload.get("sweep_grid"), dict) else _preset_grid(preset)
    candidates = _grid_candidates(grid)
    if len(candidates) > 64:
        return {"error": "sweep grid too large", "candidate_count": len(candidates), "max_candidates": 64}

    rows = _load_lao_backtest_rows()
    if rows is None:
        return {"error": "DB unavailable"}

    baseline = _run_v6_backtest_rows(
        rows,
        region=region,
        days=days,
        min_history=min_history,
        dry_run=True,
        force=False,
        weights=DEFAULT_V6_WEIGHTS,
    )

    results: list[dict[str, Any]] = []
    for idx, weights in enumerate(candidates):
        result = _run_v6_backtest_rows(
            rows,
            region=region,
            days=days,
            min_history=min_history,
            dry_run=True,
            force=False,
            weights=weights,
        )
        acc = result.get("backtest_accuracy", {}) if isinstance(result, dict) else {}
        results.append({
            "rank": 0,
            "index": idx,
            "weights": weights,
            "accuracy": acc,
            "date_range": result.get("date_range") if isinstance(result, dict) else None,
        })

    results.sort(
        key=lambda item: (
            item.get("accuracy", {}).get("hits_1d", 0),
            item.get("accuracy", {}).get("hit_rate_1d", 0.0),
            item.get("accuracy", {}).get("hits_2d", 0),
            item.get("accuracy", {}).get("hit_rate_2d", 0.0),
        ),
        reverse=True,
    )
    for idx, item in enumerate(results, 1):
        item["rank"] = idx

    return {
        "region": region,
        "preset": preset,
        "days": days,
        "min_history": min_history,
        "candidates_evaluated": len(candidates),
        "baseline": {
            "weights": DEFAULT_V6_WEIGHTS,
            "accuracy": baseline.get("backtest_accuracy", {}) if isinstance(baseline, dict) else {},
            "date_range": baseline.get("date_range") if isinstance(baseline, dict) else None,
        },
        "top": results[:top_k],
    }


def accuracy_v6(payload: dict) -> dict:
    """Compute hit-rate of v6 predictions against actual draws.

    Payload keys:
      - last_n: window size (default 30)
    """
    last_n = int(payload.get("last_n", 30))
    rows = _lao_db_query(
        """
        SELECT v.target_date, v.picks_1d, v.picks_2d, v.picks_3d,
               d.lao_last2, d.lao_last3
        FROM v6_prediction_log v
        JOIN draws d ON d.draw_date = v.target_date
        WHERE d.status = 'drawn' AND d.lao_last2 IS NOT NULL
        ORDER BY v.target_date DESC LIMIT %s
        """,
        (last_n,),
    )
    if rows is None:
        return {"error": "DB unavailable or table not found"}
    if not rows:
        return {"hit_rate_1d": 0.0, "hit_rate_2d": 0.0, "hit_rate_3d": 0.0,
                "hits_1d": 0, "total": 0, "streak_1d": 0, "window": last_n,
                "note": "no v6 predictions with draw results yet"}

    hits_1d = hits_2d = hits_3d = 0
    total = len(rows)
    streak_1d = 0
    counting_streak = True
    last_hit_date: str | None = None

    for row in rows:
        last2 = str(row.get("lao_last2") or "").strip()
        last3 = str(row.get("lao_last3") or "").strip()
        p1d = row.get("picks_1d") or []
        p2d = row.get("picks_2d") or []
        p3d = row.get("picks_3d") or []

        hit1 = any(d in last2 for d in p1d if d)
        hit2 = any(n == last2 for n in p2d if n)
        hit3 = any(n == last3 for n in p3d if n)

        if hit1:
            hits_1d += 1
            if last_hit_date is None:
                last_hit_date = str(row.get("target_date") or "")
        if hit2:
            hits_2d += 1
        if hit3:
            hits_3d += 1
        if counting_streak:
            if hit1:
                streak_1d += 1
            else:
                counting_streak = False

    return {
        "window": last_n,
        "total": total,
        "hits_1d": hits_1d,
        "hits_2d": hits_2d,
        "hits_3d": hits_3d,
        "hit_rate_1d": round(hits_1d / total, 4) if total else 0.0,
        "hit_rate_2d": round(hits_2d / total, 4) if total else 0.0,
        "hit_rate_3d": round(hits_3d / total, 4) if total else 0.0,
        "streak_1d": streak_1d,
        "last_hit_date": last_hit_date,
    }


def compare_engines(payload):
    region = payload.get("region", "lao")
    last_n = int(payload.get("last_n", 30))
    v5 = latest_prediction({"region": region})
    v6 = predict_v6({"region": region, "save": False})

    v5_acc = accuracy_stats({"region": region, "last_n": last_n})
    v6_acc = accuracy_v6({"last_n": last_n})

    v6_total = v6_acc.get("total", 0)
    promote = False
    if v6_total >= 5:
        promote = (
            v6_acc.get("hit_rate_1d", 0) > v5_acc.get("by_bet_type", {}).get("1d", {}).get("rate", 0)
            and v6_acc.get("streak_1d", 0) >= 3
        )

    return {
        "region": region,
        "v5_3": v5,
        "v6": v6,
        "accuracy": {
            "v5_3": v5_acc,
            "v6": v6_acc,
        },
        "auto_promote": {
            "should_promote": promote,
            "v6_streak_1d": v6_acc.get("streak_1d", 0),
            "v6_hit_rate_1d": v6_acc.get("hit_rate_1d", 0),
            "v5_hit_rate_1d": v5_acc.get("by_bet_type", {}).get("1d", {}).get("rate", 0),
            "note": "promotes when v6 has >= 5 data points and streak >= 3 and hit_rate_1d > v5",
        },
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


def _normalize_prediction_statuses(value: Any = None) -> list[str]:
    statuses: list[str] = []
    if isinstance(value, str):
        raw_values = [value]
    elif isinstance(value, list):
        raw_values = value
    else:
        raw_values = ["locked", "published"]
    for raw in raw_values:
        status = str(raw or "").strip()
        if status and all(ch.isalnum() or ch in {"_", "-"} for ch in status):
            statuses.append(status)
    return statuses[:8] or ["locked"]


def _v5_data_status(last_n: int, statuses: list[str]) -> dict[str, Any]:
    window_days = max(30, min(365, int(last_n)))
    status_rows = _lao_db_query(
        """
        SELECT p.status,
               COUNT(*)::int AS total,
               COUNT(*) FILTER (WHERE d.lao_last2 IS NOT NULL)::int AS joined
        FROM predictions p
        LEFT JOIN draws d ON d.draw_date = p.target_draw_date AND d.status = 'drawn'
        WHERE p.target_draw_date >= (CURRENT_DATE - (%s || ' days')::interval)
        GROUP BY p.status
        ORDER BY total DESC
        """,
        (window_days,),
    ) or []
    item_rows = _lao_db_query(
        """
        SELECT COUNT(*)::int AS item_count
        FROM prediction_items pi
        JOIN predictions p ON p.id = pi.prediction_id
        WHERE p.status = ANY(%s::text[])
          AND p.target_draw_date >= (CURRENT_DATE - (%s || ' days')::interval)
          AND pi.is_rejected = false
        """,
        (statuses, window_days),
    ) or []
    null_draw_rows = _lao_db_query(
        """
        SELECT COUNT(*)::int AS null_draw_count
        FROM draws
        WHERE status = 'drawn'
          AND lao_last2 IS NULL
          AND draw_date >= (CURRENT_DATE - (%s || ' days')::interval)
        """,
        (window_days,),
    ) or []
    breakdown = {
        str(row.get("status") or "unknown"): {
            "total": int(row.get("total") or 0),
            "joined": int(row.get("joined") or 0),
        }
        for row in status_rows
    }
    joined_active = sum(value["joined"] for key, value in breakdown.items() if key in statuses)
    total_active = sum(value["total"] for key, value in breakdown.items() if key in statuses)
    return {
        "window_days": window_days,
        "active_statuses": statuses,
        "status_breakdown": breakdown,
        "joined_active": joined_active,
        "total_active": total_active,
        "prediction_items_active": int((item_rows[0] if item_rows else {}).get("item_count") or 0),
        "drawn_null_last2": int((null_draw_rows[0] if null_draw_rows else {}).get("null_draw_count") or 0),
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
    statuses = _normalize_prediction_statuses(payload.get("statuses"))

    if region != "lao":
        return {"error": f"region {region} ไม่รองรับ accuracy_stats"}

    data_status = _v5_data_status(last_n, statuses)
    rows = _lao_db_query(
        """
        SELECT p.id, p.target_draw_date, p.status, d.lao_last2, d.lao_last3
        FROM predictions p
        JOIN draws d ON d.draw_date = p.target_draw_date
        WHERE p.status = ANY(%s::text[]) AND d.status = 'drawn'
              AND d.lao_last2 IS NOT NULL
        ORDER BY p.target_draw_date DESC
        LIMIT %s
        """,
        (statuses, last_n),
    )
    if rows is None:
        return {"error": "DB unavailable"}
    if not rows:
        return {"hit_rate": 0.0, "hits": 0, "total": 0, "by_bet_type": {},
                "streak": 0, "last_hit_date": None, "window": last_n,
                "statuses": statuses, "v5_data_status": data_status}

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
        "statuses": statuses,
        "v5_data_status": data_status,
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


def get_active_engine(payload: dict) -> dict:
    """Return which engine is currently active (v5_3 or v6) based on accuracy stats.

    Returns v6 if accuracy_v6 has enough data AND hit_rate_1d > v5_3 AND streak >= 3.
    Otherwise returns v5_3.
    """
    region = payload.get("region", "lao")
    last_n = int(payload.get("last_n", 30))
    statuses = _normalize_prediction_statuses(payload.get("statuses"))
    min_draws = int(payload.get("min_v6_draws", 5))
    min_streak = int(payload.get("min_v6_streak_1d", 3))
    v6_acc = accuracy_v6({"last_n": last_n})
    v5_acc = accuracy_stats({"region": region, "last_n": last_n, "statuses": statuses})

    v6_total = int(v6_acc.get("total", 0) or 0)
    v6_rate = float(v6_acc.get("hit_rate_1d", 0.0) or 0.0)
    v5_rate = float(v5_acc.get("by_bet_type", {}).get("1d", {}).get("rate", 0.0) or 0.0)
    streak = int(v6_acc.get("streak_1d", 0) or 0)

    gates = {
        "data": {
            "ok": v6_total >= min_draws,
            "actual": v6_total,
            "required": min_draws,
        },
        "rate": {
            "ok": v6_rate > v5_rate,
            "v6_hit_rate_1d": v6_rate,
            "v5_hit_rate_1d": v5_rate,
        },
        "streak": {
            "ok": streak >= min_streak,
            "actual": streak,
            "required": min_streak,
        },
    }

    if not gates["data"]["ok"]:
        return {
            "engine": "v5_3",
            "reason": f"data gate failed: v6 has {v6_total} evaluated draws, requires >={min_draws}",
            "gates": gates,
            "accuracy": {"v5_3": v5_acc, "v6": v6_acc},
            "v5_data_status": v5_acc.get("v5_data_status"),
        }

    if not gates["rate"]["ok"]:
        return {
            "engine": "v5_3",
            "reason": f"rate gate failed: v6 1D hit_rate={v6_rate:.1%} must be > v5={v5_rate:.1%}",
            "gates": gates,
            "accuracy": {"v5_3": v5_acc, "v6": v6_acc},
            "v5_data_status": v5_acc.get("v5_data_status"),
        }

    if not gates["streak"]["ok"]:
        return {
            "engine": "v5_3",
            "reason": f"streak gate failed: v6 1D streak={streak}, requires >={min_streak}",
            "gates": gates,
            "accuracy": {"v5_3": v5_acc, "v6": v6_acc},
            "v5_data_status": v5_acc.get("v5_data_status"),
        }

    return {
        "engine": "v6",
        "reason": f"all gates passed: v6 hit_rate_1d={v6_rate:.1%} > v5={v5_rate:.1%}, streak={streak}",
        "gates": gates,
        "accuracy": {"v5_3": v5_acc, "v6": v6_acc},
        "v5_data_status": v5_acc.get("v5_data_status"),
    }


ACTIONS: dict[str, callable] = {
    "predict": predict,
    "predict_v6": predict_v6,
    "backtest_v6": backtest_v6,
    "sweep_v6_weights": sweep_v6_weights,
    "accuracy_v6": accuracy_v6,
    "get_active_engine": get_active_engine,
    "compare_engines": compare_engines,
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
