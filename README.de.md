<div align="center">

# Purgearr

[![en](https://img.shields.io/badge/lang-en-red.svg)](https://github.com/Lekarov/Purgearr/blob/master/README.md)
[![fr](https://img.shields.io/badge/lang-fr-blue.svg)](https://github.com/Lekarov/Purgearr/blob/master/README.fr.md)
[![es](https://img.shields.io/badge/lang-es-yellow.svg)](https://github.com/Lekarov/Purgearr/blob/master/README.es.md)
[![pt](https://img.shields.io/badge/lang-pt-green.svg)](https://github.com/Lekarov/Purgearr/blob/master/README.pt.md)
[![de](https://img.shields.io/badge/lang-de-lightgrey.svg)](https://github.com/Lekarov/Purgearr/blob/master/README.de.md)
[![it](https://img.shields.io/badge/lang-it-008C45.svg)](https://github.com/Lekarov/Purgearr/blob/master/README.it.md)

**Schaff den Ballast weg. Behalte das Wesentliche. Eine Oberfläche für deine gesamte Medienbibliothek.**

![Status](https://img.shields.io/badge/Status-Beta-orange?style=flat-square)
![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white) ![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)
![Lizenz](https://img.shields.io/badge/Lizenz-MIT-6b7491?style=flat-square)
![Jellyfin](https://img.shields.io/badge/Jellyfin-00A4DC?style=flat-square&logo=jellyfin&logoColor=white) ![Radarr](https://img.shields.io/badge/Radarr-FFC230?style=flat-square) ![Sonarr](https://img.shields.io/badge/Sonarr-35C5F4?style=flat-square) ![Transmission](https://img.shields.io/badge/Transmission-CC0000?style=flat-square)
![Sprachen](https://img.shields.io/badge/Sprachen-6-orange?style=flat-square)

</div>

---

## Screenshots

<div align="center">

| Gesehen | Vorschläge — Nie gesehen |
|:---:|:---:|
| ![Watched](https://i.ibb.co/0y7d7PzZ/Capture-d-cran-2026-07-24-163340.png) | ![Never watched](https://i.ibb.co/h1Y1vT7w/Capture-d-cran-2026-07-24-163441.png) |

| Tote Torrents (Ratio 0) | Löschverlauf |
|:---:|:---:|
| ![Dead seed](https://i.ibb.co/DfB94tz7/Capture-d-cran-2026-07-24-163523.png) | ![History](https://i.ibb.co/t98YjsP/Capture-d-cran-2026-07-24-163616.png) |

| Ereignisprotokoll | Bestätigungsdialog |
|:---:|:---:|
| ![Event log](https://i.ibb.co/7NWmHB7m/Capture-d-cran-2026-07-24-163649.png) | ![Confirm deletion](https://i.ibb.co/WCCbMbD/Capture-d-cran-2026-07-24-163748.png) |

</div>

---

## Was es macht

Purgearr ist eine selbst gehostete Weboberfläche für **Jellyfin + Radarr + Sonarr + Transmission**-Setups. Es bietet einen vollständigen Überblick über deine Medienbibliothek, erkennt nie gesehene Inhalte, markiert tote Torrents, die Speicherplatz verschwenden, und ermöglicht sauberes Löschen — die Datei, den Radarr/Sonarr-Eintrag und den Torrent in einer einzigen Aktion.

Nie gesehen. Wirst du nie sehen. Gelöscht.

---

## Funktionen

- **Dashboard** — globale Bibliotheksstatistiken, Lösch-Warteschlange, letzter Verlauf
- **Gesehen** — vollständige Liste gesehener Inhalte mit Fortschritt pro Benutzer und Status "bereit zum Löschen"
- **Vorschläge** — nie gesehen / teilweise gesehen / tote Torrents (Ratio 0) mit Live-Seeding-Statistiken
- **Katalog** — vollständige Jellyfin-Bibliotheksansicht, Filme & Serien getrennt, paginiert (60/Seite), mit Suche, Sortierung und Statusfiltern
- **Whitelist** — schützt jeden Titel dauerhaft; Jellyfin-Favoriten werden automatisch geschützt
- **Verlauf** — alle vergangenen Löschungen mit Scanner für verbleibende Kopien
- **Protokoll** — filterbares Journal jeder Operation, nach Kategorie und Ebene
- **Einstellungen** — vollständige Konfiguration über die Weboberfläche, keine Dateibearbeitung erforderlich
- **Multi-Benutzer** — erforderliche Zuschauer definieren; Löschung wird nur vorgeschlagen, wenn alle gesehen haben
- **Multi-Tracker** — erkennt alle Torrents, die dieselbe Datei über mehrere Tracker seeden, dedupliziert für Größenberechnung
- **Hardlink-Erkennung** — Inode + SHA-256-Scan vor dem Löschen zur Erkennung von Kopien
- **Bestätigungsdialog** — zeigt genau an, was vor jeder Aktion gelöscht wird
- **Sprache** — 6 Sprachen

---

## Seiten

| URL | Beschreibung |
|---|---|
| `/` | Dashboard — Statistiken, Warteschlange, letzter Verlauf |
| `/watched` | Liste gesehener Inhalte |
| `/suggestions` | Nie gesehen / tote Torrents / teilweise gesehen |
| `/catalogue` | Vollständiger Katalog — Suche, Sortierung, Filter |
| `/protected` | Whitelist-Verwaltung |
| `/history` | Vergangene Löschungen + Scanner für Reste |
| `/transmission` | Verwaiste Torrents + vollständige Liste |
| `/logs` | Ereignisprotokoll |
| `/settings` | Konfiguration |

---

## Technologie-Stack

| Komponente | Technologie |
|---|---|
| Backend | FastAPI + Uvicorn |
| Datenbank | SQLite via SQLAlchemy |
| Scheduler | APScheduler |
| Templates | Jinja2 |
| Frontend | Vanilla HTML / CSS / JS |
| i18n | Benutzerdefiniertes Modul — 6 Sprachen |

---

## Voraussetzungen

- Python 3.10+
- Jellyfin, Radarr, Sonarr und Transmission in deinem lokalen Netzwerk erreichbar

---

## Installation

**1. Repository klonen**

```bash
git clone https://github.com/Lekarov/Purgearr.git
cd Purgearr
```

**2. Virtuelle Umgebung + Abhängigkeiten**

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**3. Starten**

```bash
python main.py
```

Die Oberfläche ist unter `http://[IP]:7979` verfügbar. Konfiguriere alle Dienste beim ersten Start über die **Einstellungen**-Seite.

**4. Der `data/`-Ordner — niemals löschen**

```
data/
├── config.json        ← Konfiguration (URLs, API-Schlüssel, Regeln)
├── protected.json     ← Whitelist geschützter Inhalte
├── purgearr.db        ← Verlauf, Warteschlange, Watch-Events
└── cache/             ← Temporärer Cache (wird automatisch neu erstellt)
```

> Dieser Ordner ist von git ausgeschlossen — deine Daten bleiben bei Updates erhalten.

---

## Systemd-Dienst (Raspberry Pi)

```ini
[Unit]
Description=Purgearr Media Manager
After=network.target

[Service]
Type=simple
WorkingDirectory=/pfad/zu/Purgearr
ExecStart=/pfad/zu/Purgearr/venv/bin/python main.py
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

## Jellyfin-Webhook (optional)

Der Webhook empfängt `PlaybackStop`-Ereignisse von Jellyfin in Echtzeit. Installiere das **Webhook**-Plugin aus dem Jellyfin-Katalog:

- **URL**: `http://[IP]:7979/webhook/jellyfin`
- **Ereignis**: `Playback Stop`

> Der Auto-Modus (automatisches Löschen beim Stopp der Wiedergabe) wird noch stabilisiert — verwende nur das manuelle Löschen über die Oberfläche.

---

## Steuerung über Telegram (DoktorTV Bot)

Purgearr lässt sich mit **[DoktorTV Bot](https://github.com/Lekarov/DoktorTV-Bot)** über Telegram steuern: Löschvorschläge (gesehene Filme, gesehene oder begonnene Serien, nie gesehen, die größten), Detailkarte mit Poster, **genaue Vorschau** dessen, was gelöscht wird (Bibliothek, Torrents pro Tracker, Hardlinks, Cross-Seed-Links, Kopien), Bestätigung.

- Der Bot nutzt die Routen `/api/bot/*` (Purgearr **1.2.0+**). In der `.env` des Bots: `PURGEARR_URL=http://[IP]:7979`
- Test: `curl http://[IP]:7979/api/bot/ping`

---

## Aktualisierung

```bash
git pull
sudo systemctl restart purgearr
```

---

## Datenschutz

Purgearr läuft **vollständig auf deinem eigenen Gerät** — keine Daten verlassen jemals dein Netzwerk.

- Keine Analysen, keine Telemetrie, keine externen Dienste
- Alle API-Aufrufe gehen direkt an deine lokalen Instanzen von Jellyfin, Radarr, Sonarr und Transmission
- Die Konfiguration wird lokal in `data/config.json` gespeichert

**Der Quellcode ist vollständig prüfbar** — jede Zeile befindet sich in diesem Repository.

---

## Lizenz

MIT — frei verwenden und anpassen.

---

<div align="center">
  Made by <a href="https://github.com/Lekarov">Pestovich</a>
</div>
