# 📌 Pinnwand (Pinboard)

A self-hosted digital pinboard with colorful sticky notes — easy to use, no login required, runs locally on your network.
<img src="/pinnwand_full_screenshot.png" alt="Alt-Text" width="70%"/>



## ✨ Features

- 📋 **Multiple Boards:** Create, rename, and reorder boards via drag-and-drop
- 🗂 **Overview Board:** View all notes across all boards at a single glance
- 🎨 **6 Sticky Note Colors:** Yellow, pink, blue, green, orange, and purple
- 🏷 **Custom Tags:** Create per-board tags and filter notes by tag
- ✏️ **Rich Text Formatting:** **Bold**, *Italic*, Underline, Bullet Lists, Numbered Lists, Checklists
- 👤 **Author Field:** Optional creator name for each note
- 📜 **Change History:** Track note revisions with author name, date, and timestamp
- 📦 **Archiving & Deletion:** Archive (hide) notes or permanently delete them
- 🔀 **Custom Reordering:** Drag and drop notes to rearrange them
- 🖼 **Custom Logo:** Upload your own logo
- 💾 **Persistent Storage:** All data stored in a SQLite database (persists across restarts)
- 📱 **Responsive UI:** Fully optimized for mobile, tablet, and desktop screens

---

## 🚀 Quickstart

### Prerequisites

- Linux server with Docker and Docker Compose installed
- *Alternative:* Proxmox VE (see section below)

### 1. Clone the repository


git clone [https://github.com/Abratzo/pinnwand.git](https://github.com/Abratzo/pinnwand.git)
cd pinnwand



### 2. Start the container

```bash
docker compose up -d --build

```

*Note: Initial setup may take 2–3 minutes.*

Once finished, open your browser and navigate to:

```text
http://YOUR-SERVER-IP:8080

```

That's it! ✅

---

## 🖥 Installation on Proxmox

If you use Proxmox VE, you can quickly spin up a ready-to-use Docker LXC container using the Community Script:

**In Proxmox Web UI: Select your Node → Shell**, then run:

```bash
bash -c "$(curl -fsSL [https://raw.githubusercontent.com/community-scripts/ProxmoxVE/main/ct/docker.sh](https://raw.githubusercontent.com/community-scripts/ProxmoxVE/main/ct/docker.sh))"

```

After creation, open the console of the newly created LXC container and follow the **Quickstart** steps above.

---

## 🔄 Updates

To update your Pinnwand instance to the latest version:

```bash
cd pinnwand
git pull
docker compose up -d --build

```

### Via Portainer (Optional GUI Management)

If you use Portainer:

1. Install Portainer (if not already installed):
```bash
docker run -d \
  -p 9000:9000 \
  --name portainer \
  --restart unless-stopped \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v portainer_data:/data \
  portainer/portainer-ce

```


2. Open `http://YOUR-SERVER-IP:9000` → Go to **Stacks** → **pinnwand** → Click **Pull and redeploy**.

---

## 💾 Automatic Backups

Set up an automated daily script to back up your SQLite database:

```bash
cat > ~/backup-pinnwand.sh << 'SCRIPT'
#!/bin/bash
DATE=$(date +%Y-%m-%d_%H-%M)
mkdir -p ~/pinnwand-backups
cp /var/lib/docker/volumes/pinnwand_pinnwand-data/_data/pinnwand.db \
   ~/pinnwand-backups/pinnwand_$DATE.db
# Keep only the last 7 backups
ls -t ~/pinnwand-backups/*.db | tail -n +8 | xargs rm -f 2>/dev/null
echo "Backup created: pinnwand_$DATE.db"
SCRIPT
chmod +x ~/backup-pinnwand.sh

# Run automatically every day at 03:00 AM
(crontab -l 2>/dev/null; echo "0 3 * * * /root/backup-pinnwand.sh") | crontab -

```

---

## 🗂 Directory Structure

```text
pinnwand/
├── docker-compose.yml        # Docker Compose configuration
├── backend/
│   ├── Dockerfile            # Backend container instructions
│   ├── main.py               # FastAPI backend (Python)
│   └── requirements.txt      # Python dependencies
└── frontend/
    └── index.html            # Complete single-file Web App

```

---

## 🛠 Useful Commands

```bash
# Check container status
docker ps | grep pinnwand

# View live logs
docker logs -f pinnwand-pinnwand-1

# Restart container
docker compose restart

# Stop container
docker compose down

# Query SQLite database status directly
docker exec pinnwand-pinnwand-1 python3 -c "
import sqlite3
con = sqlite3.connect('/data/pinnwand.db')
print('Boards:', con.execute('SELECT id, name FROM boards').fetchall())
print('Total Notes:', con.execute('SELECT COUNT(*) FROM notes').fetchone()[0])
"

```

---

## 🏗 Tech Stack

| Component | Technology |
| --- | --- |
| **Backend** | Python 3.12 + FastAPI |
| **Database** | SQLite |
| **Frontend** | Vanilla HTML / CSS / JavaScript |
| **Deployment** | Docker / Docker Compose |

---

## ⚙️ Configuration

### Changing the Port

Modify `docker-compose.yml` to bind to your preferred port (e.g., port `80` instead of `8080`):

```yaml
ports:
  - "80:8000"

```

### Custom Database Path

Set a custom path via environment variables in `docker-compose.yml`:

```yaml
environment:
  - DB_PATH=/data/pinnwand.db

```

---

## 📄 License

[MIT License](https://www.google.com/search?q=LICENSE) — free to use, modify, and distribute.
EOF
