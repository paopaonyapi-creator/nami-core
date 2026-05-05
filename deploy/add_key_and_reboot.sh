#!/bin/bash
# Add MSI SSH key to authorized_keys on real disk
sed -i '/ad pao@/d' /mnt/disk/root/.ssh/authorized_keys
echo 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAICE7rd9+Fu43QXpw6BsGbrxRK+WWKSZIRKYeU69aVwGX ad pao@MSI' >> /mnt/disk/root/.ssh/authorized_keys
echo "Key added. Verifying:"
grep -- 'ad pao@MSI' /mnt/disk/root/.ssh/authorized_keys
echo "Now rebooting to normal system..."
reboot
