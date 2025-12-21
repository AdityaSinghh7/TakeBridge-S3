#!/bin/bash
# 1. Format and Mount the Local NVMe SSD
# We use -F to force formatting since it's a blank scratch disk every time
mkfs.ext4 -F /dev/nvme0n1
mkdir -p /mnt/nvme
mount /dev/nvme0n1 /mnt/nvme

# 2. Set Permissions for your user
chown -R adityasingh:adityasingh /mnt/nvme

# 3. Restore the Master Brain (C.img)
# Create the directory where the docker-compose volume expects the data
mkdir -p /mnt/nvme/win-final/data

# FAST COPY: Move the pre-initialized disk from Boot Disk backup to NVMe.
# --sparse=always ensures we don't waste time copying empty space, making it faster.
cp --sparse=always /home/adityasingh/win-master-backup/C.img /mnt/nvme/win-final/data/

# 4. Start the Agent Stack
# We run this from the HOME directory (Boot Disk) because that's where docker-compose.yml lives.
# The compose file is configured to point to /mnt/nvme/win-final/data for storage.
cd /home/adityasingh/win-final
docker compose up -d
