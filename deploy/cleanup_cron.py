#!/usr/bin/env python3
"""Clean up duplicate cron jobs — nami-core scheduler now handles:
  - VIP lottery send (was: 0 18 * * *)
  - Draw alert (was: 5 */4 * * *)
  - Health alerts (was: */5 * * * *)
  
Keep: scrapers, backups, affiliate (not yet in nami-core)
Remove duplicates (each appears twice in crontab)
"""
import subprocess

result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
lines = result.stdout.strip().split("\n")

# Deduplicate and filter
seen = set()
cleaned = []
for line in lines:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        continue
    if stripped in seen:
        continue  # skip duplicate
    seen.add(stripped)
    
    # Remove jobs now handled by nami-core scheduler
    if "vip_lottery_sender.py" in stripped:
        print(f"  REMOVING (now in nami-core scheduler): {stripped[:80]}")
        continue
    if "draw_alert.py" in stripped:
        print(f"  REMOVING (now in nami-core scheduler): {stripped[:80]}")
        continue
    if "health_alerts.py" in stripped:
        print(f"  REMOVING (now in nami-core scheduler): {stripped[:80]}")
        continue
    if "health_check.sh" in stripped:
        print(f"  REMOVING (now in nami-core scheduler): {stripped[:80]}")
        continue
    
    cleaned.append(stripped)
    print(f"  KEEPING: {stripped[:80]}")

# Write back
new_cron = "\n".join(cleaned) + "\n"
subprocess.run(["crontab", "-"], input=new_cron, text=True)
print(f"\nCleaned: {len(lines)} → {len(cleaned)} entries")
