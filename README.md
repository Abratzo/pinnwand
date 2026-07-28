# 📌 Pinnwand

Eine selbst-gehostete digitale Pinnwand mit bunten PostIt-Notizen — einfach zu bedienen, keine Anmeldung nötig, läuft lokal im Netzwerk.

![Pinnwand Screenshot](https://via.placeholder.com/800x400?text=Pinnwand+App)

## ✨ Features

- 📋 Mehrere Boards erstellen, benennen und per Drag & Drop sortieren
- 🗂 Übersichts-Board zeigt alle Notizen aller Boards auf einen Blick
- 🎨 Notizen in 6 Farben (gelb, pink, blau, grün, orange, lila)
- 🏷 Frei erstellbare Tags pro Board, Notizen filtern nach Tags
- ✏️ Textformatierung: **Fett**, *Kursiv*, Unterstrichen, Aufzählung, Nummerierung, Checkliste
- 👤 Optionaler Erstellername pro Notiz
- 📜 Änderungsverlauf jeder Notiz mit Name, Datum und Uhrzeit
- 📦 Archivieren (ausblenden) und endgültig löschen
- 🔀 Reihenfolge der Notizen per Drag & Drop ändern
- 🖼 Eigenes Logo hochladbar
- 💾 Alle Daten in SQLite-Datenbank (persistent über Neustarts)
- 📱 Funktioniert auf Tablet, PC und Handy

---

## 🚀 Installation

### Voraussetzungen

- [Proxmox](https://www.proxmox.com/) oder ein anderer Linux-Server
- Docker (wird automatisch installiert, siehe unten)

---

### Schritt 1 — Docker installieren (Proxmox)

Im Proxmox-Webinterface auf den **Node** klicken → **Shell**, dann:

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/community-scripts/ProxmoxVE/main/ct/docker.sh)"
```

Das Skript erstellt automatisch einen LXC-Container mit Docker. Danach in die **Console des neuen Containers** wechseln.

---

### Schritt 2 — Dateien herunterladen

```bash
mkdir -p ~/pinnwand/backend ~/pinnwand/frontend

TOKEN="DEIN_GITHUB_TOKEN"
USER="DEIN_GITHUB_USERNAME"
BASE="https://raw.githubusercontent.com/$USER/pinnwand/main"

curl -sH "Authorization: token $TOKEN" -o ~/pinnwand/docker-compose.yml    "$BASE/docker-compose.yml"
curl -sH "Authorization: token $TOKEN" -o ~/pinnwand/backend/Dockerfile     "$BASE/backend/Dockerfile"
curl -sH "Authorization: token $TOKEN" -o ~/pinnwand/backend/main.py        "$BASE/backend/main.py"
curl -sH "Authorization: token $TOKEN" -o ~/pinnwand/backend/requirements.txt "$BASE/backend/requirements.txt"
curl -sH "Authorization: token $TOKEN" -o ~/pinnwand/frontend/index.html    "$BASE/frontend/index.html"
```

> **GitHub Token erstellen:** GitHub → Einstellungen → Developer settings → Personal access tokens → Tokens (classic) → Generate new token → Haken bei `repo` setzen.

---

### Schritt 3 — Starten

```bash
cd ~/pinnwand
docker compose up -d --build
```

Der erste Start dauert 2–3 Minuten. Danach ist die Pinnwand erreichbar unter:

```
http://CONTAINER-IP:8080
```

Die IP des Containers findest du in Proxmox unter dem Container → Summary.

---

### Optional: Portainer (grafische Verwaltung)

Portainer ermöglicht Updates und Verwaltung direkt im Browser ohne Shell.

```bash
docker run -d \
  -p 9000:9000 \
  --name portainer \
  --restart unless-stopped \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v portainer_data:/data \
  portainer/portainer-ce
```

Portainer öffnen: `http://CONTAINER-IP:9000`

Danach: **Stacks → Add Stack → Repository** und die GitHub-URL sowie den Token eintragen.

---

## 🔄 Updates einspielen

### Via Shell

```bash
cd ~/pinnwand

TOKEN="DEIN_GITHUB_TOKEN"
USER="DEIN_GITHUB_USERNAME"
BASE="https://raw.githubusercontent.com/$USER/pinnwand/main"

curl -sH "Authorization: token $TOKEN" -o backend/main.py      "$BASE/backend/main.py"
curl -sH "Authorization: token $TOKEN" -o frontend/index.html  "$BASE/frontend/index.html"

docker compose up -d --build
```

Als Update-Skript speichern:

```bash
cat > ~/update-pinnwand.sh << 'EOF'
#!/bin/bash
TOKEN="DEIN_GITHUB_TOKEN"
USER="DEIN_GITHUB_USERNAME"
BASE="https://raw.githubusercontent.com/$USER/pinnwand/main"
cd ~/pinnwand
curl -sH "Authorization: token $TOKEN" -o backend/main.py     "$BASE/backend/main.py"
curl -sH "Authorization: token $TOKEN" -o frontend/index.html "$BASE/frontend/index.html"
docker compose up -d --build
echo "✅ Pinnwand aktualisiert!"
EOF
chmod +x ~/update-pinnwand.sh
```

Danach reicht immer: `~/update-pinnwand.sh`

### Via Portainer

Stacks → pinnwand → **Pull and redeploy**

---

## 💾 Automatisches Backup

```bash
cat > ~/backup-pinnwand.sh << 'EOF'
#!/bin/bash
DATUM=$(date +%Y-%m-%d_%H-%M)
mkdir -p ~/pinnwand-backups
cp /var/lib/docker/volumes/pinnwand_pinnwand-data/_data/pinnwand.db \
   ~/pinnwand-backups/pinnwand_$DATUM.db
ls -t ~/pinnwand-backups/*.db | tail -n +8 | xargs rm -f 2>/dev/null
echo "✅ Backup erstellt: pinnwand_$DATUM.db"
EOF
chmod +x ~/backup-pinnwand.sh

# Täglich um 3:00 Uhr automatisch sichern
(crontab -l 2>/dev/null; echo "0 3 * * * /root/backup-pinnwand.sh") | crontab -
```

Backup manuell ausführen: `~/backup-pinnwand.sh`

---

## 🗂 Dateistruktur

```
pinnwand/
├── docker-compose.yml        # Docker-Konfiguration
├── backend/
│   ├── Dockerfile            # Container-Bauanleitung
│   ├── main.py               # FastAPI Backend (Python)
│   └── requirements.txt      # Python-Abhängigkeiten
└── frontend/
    └── index.html            # Komplette Web-App (eine Datei)
```

---

## 🛠 Nützliche Befehle

```bash
# Status prüfen
docker ps | grep pinnwand

# Logs anschauen
docker logs pinnwand-pinnwand-1

# Neu starten
cd ~/pinnwand && docker compose restart

# Stoppen
cd ~/pinnwand && docker compose down

# Datenbank direkt prüfen
docker exec pinnwand-pinnwand-1 python3 -c "
import sqlite3
con = sqlite3.connect('/data/pinnwand.db')
print('Boards:', con.execute('SELECT id, name FROM boards').fetchall())
print('Notizen:', con.execute('SELECT COUNT(*) FROM notes').fetchone()[0])
"
```

---

## 🏗 Technischer Stack

| Komponente | Technologie |
|---|---|
| Backend | Python 3.12 + FastAPI |
| Datenbank | SQLite |
| Frontend | Vanilla HTML/CSS/JavaScript |
| Container | Docker + nginx |
| Deployment | Docker Compose |

---

## ⚙️ Konfiguration

| Variable | Standard | Beschreibung |
|---|---|---|
| `DB_PATH` | `/data/pinnwand.db` | Pfad zur Datenbank |
| Port | `8080` | Erreichbar unter `http://IP:8080` |

Port ändern in `docker-compose.yml`:
```yaml
ports:
  - "80:8000"   # Statt 8080 → Port 80 (Standard HTTP)
```

---

## 📄 Lizenz

MIT License — frei verwendbar, veränderbar und weiterggebbar.
