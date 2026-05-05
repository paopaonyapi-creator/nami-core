#!/bin/bash
# Fix authorized_keys on real disk and reboot to normal
set -e
mkdir -p /mnt/disk
mount /dev/sda1 /mnt/disk
cat /mnt/disk/root/.ssh/authorized_keys 2>/dev/null || echo "No existing file"
# Overwrite with clean version from stdin
cat > /mnt/disk/root/.ssh/authorized_keys
chmod 600 /mnt/disk/root/.ssh/authorized_keys
chown root:root /mnt/disk/root/.ssh/authorized_keys
echo "=== Verifying ==="
cat /mnt/disk/root/.ssh/authorized_keys
echo "=== Keys written, unmounting ==="
umount /mnt/disk
echo "=== Rebooting to normal system ==="
reboot
