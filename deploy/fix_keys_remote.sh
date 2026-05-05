#!/bin/bash
# One-shot fix: mount disk, write clean authorized_keys via python3, verify, reboot
mkdir -p /mnt/disk
mount /dev/sda1 /mnt/disk
python3 -c '
import os
AUTH_KEYS_PATH = "/mnt/disk/root/.ssh/authorized_keys"
KEYS = [
    "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAII1pLWep7hd7bBgy4XuSNcIC/xPMYJel4mvXXZnBAkl6 hermes-agent",
    "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAVR1KH50erR5CWZmg6BUOKy5ve+It+ul4Pqupp8nFYe pao-main-pc",
    "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGKkdlKcof1zz7LzA6t/XXEdu5gfxnYtjPR9ZEHTHFhG nami-user-key",
    "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAICE7rd9+Fu43QXpw6BsGbrxRK+WWKSZIRKYeU69aVwGX ad pao@MSI",
]
os.makedirs(os.path.dirname(AUTH_KEYS_PATH), exist_ok=True)
with open(AUTH_KEYS_PATH, "w", encoding="utf-8", newline="\n") as f:
    for key in KEYS:
        f.write(key + "\n")
os.chmod(AUTH_KEYS_PATH, 0o600)
os.chown(AUTH_KEYS_PATH, 0, 0)
with open(AUTH_KEYS_PATH, "r", encoding="utf-8") as f:
    content = f.read()
print("=== KEYS WRITTEN ===")
print(content)
print("=== VERIFIED ===")
'
umount /mnt/disk
echo "=== REBOOTING ==="
reboot
