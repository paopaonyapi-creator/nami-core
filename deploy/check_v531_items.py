import subprocess, os

pw = open("/etc/nami-harness/postgres_password").read().strip()
env = {**os.environ, "PGPASSWORD": pw}

sql = """
SELECT bet_type, category, count(*) as cnt, 
       round(avg(score)::numeric, 4) as avg_score,
       round(avg(strict_score)::numeric, 4) as avg_strict
FROM prediction_items 
WHERE prediction_id = '1034dce3-da87-43e4-86c2-25595bdf22e9'
GROUP BY 1,2 ORDER BY 1,2;
"""

r = subprocess.run(["psql", "-h", "127.0.0.1", "-U", "postgres", "-d", "laopatana_stat_lab",
                     "-A", "-F", "|", "-P", "footer=off", "-c", sql],
                    capture_output=True, text=True, env=env, timeout=15)
print(r.stdout)

# Show non-rejected picks
sql2 = """
SELECT bet_type, number, category, round(score::numeric, 4) as score, round(strict_score::numeric, 4) as strict
FROM prediction_items 
WHERE prediction_id = '1034dce3-da87-43e4-86c2-25595bdf22e9'
  AND is_rejected = false
ORDER BY bet_type, score DESC;
"""

r2 = subprocess.run(["psql", "-h", "127.0.0.1", "-U", "postgres", "-d", "laopatana_stat_lab",
                      "-A", "-F", "|", "-P", "footer=off", "-c", sql2],
                     capture_output=True, text=True, env=env, timeout=15)
print(r2.stdout)
