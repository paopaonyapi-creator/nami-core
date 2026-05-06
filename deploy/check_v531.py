import subprocess, os, json

pw = open("/etc/nami-harness/postgres_password").read().strip()
env = {**os.environ, "PGPASSWORD": pw}

sql = """
SELECT p.target_draw_date::date, p.status, rv.name, 
       count(pi.id) as items
FROM predictions p 
JOIN rule_versions rv ON p.rule_version_id = rv.id 
LEFT JOIN prediction_items pi ON p.id = pi.prediction_id 
WHERE rv.is_active = true 
GROUP BY 1,2,3 
ORDER BY p.created_at DESC LIMIT 3;
"""

r = subprocess.run(["psql", "-h", "127.0.0.1", "-U", "postgres", "-d", "laopatana_stat_lab",
                     "-A", "-F", "|", "-P", "footer=off", "-c", sql],
                    capture_output=True, text=True, env=env, timeout=15)
print(r.stdout)

# Also show latest prediction items
sql2 = """
SELECT pi.bet_type, pi.number, pi.category, round(pi.score::numeric, 4) as score
FROM prediction_items pi 
JOIN predictions p ON pi.prediction_id = p.id
JOIN rule_versions rv ON p.rule_version_id = rv.id
WHERE rv.is_active = true
ORDER BY pi.score DESC LIMIT 15;
"""

r2 = subprocess.run(["psql", "-h", "127.0.0.1", "-U", "postgres", "-d", "laopatana_stat_lab",
                      "-A", "-F", "|", "-P", "footer=off", "-c", sql2],
                     capture_output=True, text=True, env=env, timeout=15)
print(r2.stdout)
