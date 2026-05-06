"""Pipeline worker — ETL-style data transformations with chainable steps."""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger("nami_workers.pipeline")


def pipeline_worker(payload: dict[str, Any]) -> dict[str, Any]:
    """Pipeline worker: transform, aggregate, export."""
    action = payload.get("action", "transform")

    if action == "transform":
        return _transform(payload)
    elif action == "aggregate":
        return _aggregate(payload)
    elif action == "export":
        return _export(payload)
    else:
        return {"error": f"unknown action: {action}"}


def _transform(payload: dict[str, Any]) -> dict[str, Any]:
    """Apply transformation steps to input data."""
    data = payload.get("data", {})
    steps = payload.get("steps", [])

    if not steps:
        return {"error": "steps required"}

    current = data
    applied = []

    for step in steps:
        op = step.get("op", "")
        field = step.get("field", "")
        value = step.get("value")

        try:
            if op == "rename":
                if field in current:
                    current[value] = current.pop(field)
                    applied.append(f"rename:{field}->{value}")
            elif op == "filter":
                if isinstance(current, dict):
                    current = {k: v for k, v in current.items() if k != field}
                    applied.append(f"filter:{field}")
                elif isinstance(current, list):
                    current = [item for item in current if field not in (item if isinstance(item, dict) else {})]
                    applied.append(f"filter:{field}")
            elif op == "add":
                if isinstance(current, dict):
                    current[field] = value
                    applied.append(f"add:{field}")
            elif op == "select":
                if isinstance(current, dict):
                    keys = value if isinstance(value, list) else [value]
                    current = {k: current[k] for k in keys if k in current}
                    applied.append(f"select:{keys}")
            elif op == "map":
                if isinstance(current, list) and field:
                    current = [{**item, field: item.get(field)} for item in current if isinstance(item, dict)]
                    applied.append(f"map:{field}")
            elif op == "flatten":
                if isinstance(current, dict):
                    flat = {}
                    for k, v in current.items():
                        if isinstance(v, dict):
                            for sk, sv in v.items():
                                flat[f"{k}.{sk}"] = sv
                        else:
                            flat[k] = v
                    current = flat
                    applied.append("flatten")
            else:
                applied.append(f"skip:unknown_op:{op}")
        except Exception as exc:
            applied.append(f"error:{op}:{exc}")

    return {"ok": True, "result": current, "applied": applied}


def _aggregate(payload: dict[str, Any]) -> dict[str, Any]:
    """Aggregate numeric data by operation."""
    data = payload.get("data", [])
    operation = payload.get("operation", "sum")
    field = payload.get("field", "")

    if not data:
        return {"error": "data required (list of numbers or list of dicts with field)"}

    # Extract values
    values = []
    for item in data:
        if isinstance(item, (int, float)):
            values.append(item)
        elif isinstance(item, dict) and field:
            val = item.get(field)
            if isinstance(val, (int, float)):
                values.append(val)

    if not values:
        return {"error": f"no numeric values found for field '{field}'"}

    if operation == "sum":
        result = sum(values)
    elif operation == "avg":
        result = sum(values) / len(values)
    elif operation == "min":
        result = min(values)
    elif operation == "max":
        result = max(values)
    elif operation == "count":
        result = len(values)
    elif operation == "median":
        sorted_vals = sorted(values)
        n = len(sorted_vals)
        result = sorted_vals[n // 2] if n % 2 else (sorted_vals[n // 2 - 1] + sorted_vals[n // 2]) / 2
    else:
        return {"error": f"unknown operation: {operation}"}

    return {"ok": True, "operation": operation, "field": field or "direct", "result": round(result, 4), "count": len(values)}


def _export(payload: dict[str, Any]) -> dict[str, Any]:
    """Export data in specified format."""
    data = payload.get("data", {})
    fmt = payload.get("format", "json")

    if fmt == "json":
        return {"ok": True, "format": "json", "output": json.dumps(data, indent=2, default=str)}
    elif fmt == "csv":
        if not isinstance(data, list):
            return {"error": "data must be a list for CSV export"}
        if not data:
            return {"ok": True, "format": "csv", "output": ""}
        keys = list(data[0].keys()) if isinstance(data[0], dict) else []
        lines = [",".join(keys)]
        for row in data:
            if isinstance(row, dict):
                lines.append(",".join(str(row.get(k, "")) for k in keys))
        return {"ok": True, "format": "csv", "output": "\n".join(lines)}
    elif fmt == "summary":
        if isinstance(data, dict):
            return {"ok": True, "format": "summary", "output": f"{len(data)} keys: " + ", ".join(list(data.keys())[:10])}
        elif isinstance(data, list):
            return {"ok": True, "format": "summary", "output": f"{len(data)} items"}
        return {"ok": True, "format": "summary", "output": str(type(data))}
    else:
        return {"error": f"unsupported format: {fmt}"}
