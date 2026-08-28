<div align="center">

# Purgearr

[![en](https://img.shields.io/badge/lang-en-red.svg)](https://github.com/Lekarov/Purgearr/blob/master/README.md)
[![fr](https://img.shields.io/badge/lang-fr-blue.svg)](https://github.com/Lekarov/Purgearr/blob/master/README.fr.md)
[![es](https://img.shields.io/badge/lang-es-yellow.svg)](https://github.com/Lekarov/Purgearr/blob/master/README.es.md)
[![pt](https://img.shields.io/badge/lang-pt-green.svg)](https://github.com/Lekarov/Purgearr/blob/master/README.pt.md)
[![de](https://img.shields.io/badge/lang-de-lightgrey.svg)](https://github.com/Lekarov/Purgearr/blob/master/README.de.md)
[![it](https://img.shields.io/badge/lang-it-008C45.svg)](https://github.com/Lekarov/Purgearr/blob/master/README.it.md)

**Kill the clutter. Keep the classics. One interface for your entire media library.**

![Status](https://img.shields.io/badge/status-beta-orange?style=flat-square)
![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white) ![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-6b7491?style=flat-square)
![Jellyfin](https://img.shields.io/badge/Jellyfin-00A4DC?style=flat-square&logo=jellyfin&logoColor=white) ![Radarr](https://img.shields.io/badge/Radarr-FFC230?style=flat-square) ![Sonarr](https://img.shields.io/badge/Sonarr-35C5F4?style=flat-square) ![Transmission](https://img.shields.io/badge/Transmission-CC0000?style=flat-square)
![Languages](https://img.shields.io/badge/languages-6-orange?style=flat-square)

</div>

---

## Screenshots

<div align="center">

| Watched | Suggestions — Never watched |
|:---:|:---:|
| ![Watched](https://i.ibb.co/0y7d7PzZ/Capture-d-cran-2026-07-24-163340.png) | ![Never watched](https://i.ibb.co/h1Y1vT7w/Capture-d-cran-2026-07-24-163441.png) |

| Dead torrents (ratio 0) | Deletion history |
|:---:|:---:|
| ![Dead seed](https://i.ibb.co/DfB94tz7/Capture-d-cran-2026-07-24-163523.png) | ![History](https://i.ibb.co/t98YjsP/Capture-d-cran-2026-07-24-163616.png) |

| Event log | Confirmation modal |
|:---:|:---:|
| ![Event log](https://i.ibb.co/7NWmHB7m/Capture-d-cran-2026-07-24-163649.png) | ![Confirm deletion](https://i.ibb.co/WCCbMbD/Capture-d-cran-2026-07-24-163748.png) |

</div>

---

## What it does

Purgearr is a self-hosted web interface for **Jellyfin + Radarr + Sonarr + Transmission** setups. It gives you a complete view of your media library, surfaces content that's never been watched, flags dead torrents wasting disk space, and lets you delete cleanly — removing the file, the Radarr/Sonarr entry, and the torrent in a single action.

Never watched it. Never will. Gone.

---

## Features

- **Dashboard** — global library stats, deletion queue, recent history
- **Watched** — full list of viewed content with per-user progress and "ready to delete" status
- **Suggestions** — never watched / partially watched / dead torrents (ratio 0) with live Transmission seeding stats
- **Catalogue** — complete Jellyfin library view, Films & Series separated, paginated (60/page), with search, sort, and status filters
- **Whitelist** — protect any title permanently; Jellyfin favorites are automatically protected
- **History** — all past deletions with a leftover copy scanner
- **Event log** — filterable journal of every operation, with category and level filters
- **Settings** — full configuration from the web UI, no file editing required
- **Multi-user** — define required watchers; deletion is only suggested when all have watched
- **Multi-tracker** — detects all torrents seeding the same file across multiple trackers, deduplicated for size calculation
- **Hardlink detection** — inode + SHA-256 scan before deletion to catch duplicate copies, correctly excluded from the freed-space total (they share the same disk blocks as the source)
- **Reviewed name matching** — when hash/inode alone isn't enough (e.g. a whole season spread across differently-named tracker releases), an optional name-based search surfaces extra candidates; you pick exactly which ones to delete via checkboxes, never deleted automatically
- **Confirmation modal** — shows exactly what will be removed before any deletion
- **Language** — 6 languages

---

## Pages

| URL | Description |
|---|---|
| `/` | Dashboard — stats, queue, recent history |
| `/watched` | Viewed content list |
| `/suggestions` | Never watched / dead torrents / partially watched |
| `/catalogue` | Full catalogue — search, sort, filter |
| `/protected` | Whitelist management |
| `/history` | Past deletions + leftover copy scanner |
| `/transmission` | Orphaned torrents + full torrent list |
| `/logs` | Event journal |
| `/settings` | Configuration |

---

## Tech stack

| Component | Technology |
|---|---|
| Backend | FastAPI + Uvicorn |
| Database | SQLite via SQLAlchemy |
| Scheduler | APScheduler |
| Templates | Jinja2 |
| Frontend | Vanilla HTML / CSS / JS |
| i18n | Custom module — 6 languages |

---

## Requirements

- Python 3.10+
- Jellyfin, Radarr, Sonarr and Transmission accessible on your local network

---

## Install

**1. Clone the repository**

```bash
git clone https://github.com/Lekarov/Purgearr.git
cd Purgearr
```

**2. Virtual environment + dependencies**

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**3. Start**

```bash
python main.py
```

The interface is available at `http://[IP]:7979`. Configure all services from the **Settings** page on first launch.

**4. The `data/` folder — never delete**

```
data/
├── config.json        ← configuration (URLs, API keys, rules)
├── protected.json     ← protected content whitelist
├── purgearr.db        ← history, queue, watch events
└── cache/             ← temporary cache (auto-regenerated)
```

> This folder is excluded from git — your data is preserved across updates.

---

## Run as a service (Raspberry Pi)

```ini
[Unit]
Description=Purgearr Media Manager
After=network.target

[Service]
Type=simple
WorkingDirectory=/path/to/Purgearr
ExecStart=/path/to/Purgearr/venv/bin/python main.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable purgearr
sudo systemctl start purgearr
```

---

## Jellyfin Webhook (optional)

The webhook receives `PlaybackStop` events from Jellyfin in real time. Install the **Webhook** plugin from the Jellyfin catalog:

- **URL**: `http://[IP]:7979/webhook/jellyfin`
- **Event**: `Playback Stop`

> Auto mode (automatic deletion on playback stop) is currently in stabilization — use manual deletion from the interface only.

---

## Updating

```bash
git pull
sudo systemctl restart purgearr
```

---

## Privacy

Purgearr runs **entirely on your own machine** — no data ever leaves your network.

- No analytics, no telemetry, no external services
- All API calls go directly to your local Jellyfin, Radarr, Sonarr, and Transmission instances
- Configuration is stored locally in `data/config.json`

**The source code is fully auditable** — every line is in this repository.

---

## License

MIT — use and adapt freely.

---

<div align="center">
  Made by <a href="https://github.com/Lekarov">Pestovich</a>
</div>
