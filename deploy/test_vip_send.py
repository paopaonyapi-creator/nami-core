from nami_workers.lottery_worker import lottery_worker

print("=== VIP Send Test ===")
r = lottery_worker({"action": "vip", "send": True})
print(r)
