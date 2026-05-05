import sys
f = open("/opt/nami-army/vip_lottery_sender.py")
c = f.read()
f.close()
c = c.replace("-1003887377430", "-1003736959465")
f = open("/opt/nami-army/vip_lottery_sender.py", "w")
f.write(c)
f.close()
print("CHANNEL_ID_FIXED")
