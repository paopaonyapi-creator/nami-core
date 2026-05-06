import subprocess, os

pw = open("/etc/nami-harness/postgres_password").read().strip()
env = {**os.environ, "PGPASSWORD": pw}

sql = """
SELECT p.id, p.target_draw_date::date, p.status, rv.name,
       (SELECT count(*) FROM prediction_items WHERE prediction_id = p.id) as items
FROM predictions p
JOIN rule_versions rv ON p.rule_version_id = rv.id
ORDER BY p.created_at DESC LIMIT 5;
"""

r = subprocess.run(["psql", "-h", "127.0.0.1", "-U", "postgres", "-d", "laopatana_stat_lab",
                     "-A", "-F", "|", "-P", "footer=off", "-c", sql],
                    capture_output=True, text=True, env=env, timeout=15)
print(r.stdout)
