#!/bin/bash
# Log output for debugging: sudo journalctl -u google-startup-scripts.service
exec > /var/log/startup-script.log 2>&1

echo "--- 1. NVMe Setup ---"
mkfs.ext4 -F /dev/nvme0n1
mkdir -p /mnt/nvme
mount /dev/nvme0n1 /mnt/nvme

echo "--- 2. Copying Master Brain ---"
# Create destination directory
mkdir -p /mnt/nvme/win-final/data

# FAST COPY (Sparse)
# This will take ~2 minutes on the new SSD.
cp --sparse=always /home/adityasingh/win-master-backup/C.img /mnt/nvme/win-final/data/

echo "--- 3. Setting Permissions ---"
# CRITICAL: Run chown AFTER copy is done so adityasingh owns the file
chown -R adityasingh:adityasingh /mnt/nvme

echo "--- 4. Starting Docker ---"
# CRITICAL: Run as 'adityasingh' to find the correct docker socket and configs
su - adityasingh -c "cd /home/adityasingh/win-final && docker compose up -d"

echo "--- Startup Complete ---"
