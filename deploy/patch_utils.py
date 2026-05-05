#!/usr/bin/env python3
"""Patch _get_ai_config on VPS to handle string configs."""
import re

path = "/opt/nami-core/src/nami_workers/utils.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

old = """    try:
        with open(config_path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}"""

new = """    try:
        with open(config_path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
        if isinstance(data, str):
            return {"openrouter": {"api_key": data.strip()}}
        return {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}"""

if old in content:
    content = content.replace(old, new)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("PATCHED_OK")
else:
    print("ALREADY_PATCHED_OR_NOT_FOUND")
