import subprocess, os

pw = open("/etc/nami-harness/postgres_password").read().strip()
env = {**os.environ, "PGPASSWORD": pw}

# Recent draws
sql = "SELECT count(*) FROM draws WHERE draw_date >= now() - interval '7 days';"
r = subprocess.run(["psql", "-h", "127.0.0.1", "-U", "postgres", "-d", "laopatana_stat_lab",
                     "-t", "-A", "-c", sql], capture_output=True, text=True, env=env, timeout=15)
print(f"Draws last 7 days: {r.stdout.strip()}")

# Latest prediction
sql2 = """
SELECT p.target_draw_date::date, p.status, rv.name,
       (SELECT count(*) FROM prediction_items WHERE prediction_id = p.id AND is_rejected = false) as active_items
FROM predictions p
JOIN rule_versions rv ON p.rule_version_id = rv.id
ORDER BY p.created_at DESC LIMIT 3;
"""
r2 = subprocess.run(["psql", "-h", "127.0.0.1", "-U", "postgres", "-d", "laopatana_stat_lab",
                      "-A", "-F", "|", "-P", "footer=off", "-c", sql2], capture_output=True, text=True, env=env, timeout=15)
print(r2.stdout)

# Latest draw
sql3 = "SELECT draw_date::date, lao_last4, lao_last2 FROM draws ORDER BY draw_date DESC LIMIT 1;"
r3 = subprocess.run(["psql", "-h", "127.0.0.1", "-U", "postgres", "-d", "laopatana_stat_lab",
                      "-t", "-A", "-c", sql3], capture_output=True, text=True, env=env, timeout=15)
print(f"Latest draw: {r3.stdout.strip()}")
