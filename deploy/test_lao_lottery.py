from nami_workers.lottery_worker import lottery_worker

print("=== VIP Action ===")
r = lottery_worker({"action": "vip"})
print(r)

print("\n=== Lao Predict ===")
r2 = lottery_worker({"action": "predict", "region": "lao"})
print(r2)

print("\n=== Lao Fetch Results ===")
r3 = lottery_worker({"action": "fetch_results", "region": "lao"})
print(r3)
