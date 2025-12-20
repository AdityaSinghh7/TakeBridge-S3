#!/bin/bash
# 1. Format and Mount the Local NVMe SSD
# We use -F to force formatting since it's a blank scratch disk every time
mkfs.ext4 -F /dev/nvme0n1
mkdir -p /mnt/nvme
mount /dev/nvme0n1 /mnt/nvme

# 2. Set Permissions for your user
chown -R adityasingh:adityasingh /mnt/nvme

# 3. Restore the Configuration Environment
# We assume your persistent configs (compose, xml) are saved in your home dir
mkdir -p /mnt/nvme/win-final
cp -r /home/adityasingh/win-final/* /mnt/nvme/win-final/

# 4. Start the Agent Stack
cd /mnt/nvme/win-final
docker compose up -d
