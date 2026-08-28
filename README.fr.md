<div align="center">

# Purgearr

[![en](https://img.shields.io/badge/lang-en-red.svg)](https://github.com/Lekarov/Purgearr/blob/master/README.md)
[![fr](https://img.shields.io/badge/lang-fr-blue.svg)](https://github.com/Lekarov/Purgearr/blob/master/README.fr.md)
[![es](https://img.shields.io/badge/lang-es-yellow.svg)](https://github.com/Lekarov/Purgearr/blob/master/README.es.md)
[![pt](https://img.shields.io/badge/lang-pt-green.svg)](https://github.com/Lekarov/Purgearr/blob/master/README.pt.md)
[![de](https://img.shields.io/badge/lang-de-lightgrey.svg)](https://github.com/Lekarov/Purgearr/blob/master/README.de.md)
[![it](https://img.shields.io/badge/lang-it-008C45.svg)](https://github.com/Lekarov/Purgearr/blob/master/README.it.md)

**Libère de l'espace. Garde l'essentiel. Une interface pour toute ta bibliothèque.**

![Status](https://img.shields.io/badge/status-bêta-orange?style=flat-square)
![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white) ![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)
![Licence](https://img.shields.io/badge/licence-MIT-6b7491?style=flat-square)
![Jellyfin](https://img.shields.io/badge/Jellyfin-00A4DC?style=flat-square&logo=jellyfin&logoColor=white) ![Radarr](https://img.shields.io/badge/Radarr-FFC230?style=flat-square) ![Sonarr](https://img.shields.io/badge/Sonarr-35C5F4?style=flat-square) ![Transmission](https://img.shields.io/badge/Transmission-CC0000?style=flat-square)
![Langues](https://img.shields.io/badge/langues-6-orange?style=flat-square)

</div>

---

## Aperçu

<div align="center">

| Regardés | Suggestions — Jamais regardés |
|:---:|:---:|
| ![Watched](https://i.ibb.co/0y7d7PzZ/Capture-d-cran-2026-07-24-163340.png) | ![Never watched](https://i.ibb.co/h1Y1vT7w/Capture-d-cran-2026-07-24-163441.png) |

| Torrents morts (ratio 0) | Historique des suppressions |
|:---:|:---:|
| ![Dead seed](https://i.ibb.co/DfB94tz7/Capture-d-cran-2026-07-24-163523.png) | ![History](https://i.ibb.co/t98YjsP/Capture-d-cran-2026-07-24-163616.png) |

| Journal événementiel | Modal de confirmation |
|:---:|:---:|
| ![Event log](https://i.ibb.co/7NWmHB7m/Capture-d-cran-2026-07-24-163649.png) | ![Confirm deletion](https://i.ibb.co/WCCbMbD/Capture-d-cran-2026-07-24-163748.png) |

</div>

---

## Ce que ça fait

Purgearr est une interface web auto-hébergée pour les setups **Jellyfin + Radarr + Sonarr + Transmission**. Il donne une vue complète de ta bibliothèque, identifie les contenus jamais regardés, signale les torrents morts qui occupent de l'espace, et permet de supprimer proprement — le fichier, l'entrée Radarr/Sonarr, et le torrent en une seule action.

Jamais regardé. Jamais regarderas. Supprimé.

---

## Fonctionnalités

- **Dashboard** — stats globales de la bibliothèque, queue de suppression, historique récent
- **Regardés** — liste complète des contenus vus avec progression par utilisateur et statut "prêt à supprimer"
- **Suggestions** — jamais regardés / vus partiellement / torrents morts (ratio 0) avec stats seeding Transmission en temps réel
- **Catalogue** — vue complète de la bibliothèque Jellyfin, Films et Séries séparés, paginée (60/page), avec recherche, tri et filtres de statut
- **Whitelist** — protège n'importe quel titre définitivement ; les favoris Jellyfin sont automatiquement protégés
- **Historique** — toutes les suppressions passées avec scanner de copies résiduelles
- **Journal** — journal filtrable de chaque opération, par catégorie et niveau
- **Paramètres** — configuration complète depuis l'interface web, sans édition de fichier
- **Multi-utilisateurs** — définir des spectateurs requis ; la suppression n'est suggérée que quand tous ont regardé
- **Multi-tracker** — détecte tous les torrents qui seedent le même fichier sur plusieurs trackers, dédupliqué pour le calcul de taille
- **Détection hardlinks** — scan inode + SHA-256 avant suppression pour détecter les copies, correctement exclues du total d'espace libéré (elles partagent les mêmes blocs disque que la source)
- **Matching par nom supervisé** — quand le hash/inode seul ne suffit pas (ex: une saison éparpillée sous des noms de release différents), une recherche par nom optionnelle fait remonter des candidats supplémentaires ; tu choisis toi-même lesquels supprimer via des cases à cocher, jamais supprimés automatiquement
- **Modal de confirmation** — affiche exactement ce qui sera supprimé avant chaque action
- **Langue** — 6 langues

---

## Pages

| URL | Description |
|---|---|
| `/` | Dashboard — stats, queue, historique récent |
| `/watched` | Liste des contenus regardés |
| `/suggestions` | Jamais vus / torrents morts / vus partiellement |
| `/catalogue` | Catalogue complet — recherche, tri, filtres |
| `/protected` | Gestion de la whitelist |
| `/history` | Suppressions passées + scanner de restes |
| `/transmission` | Torrents orphelins + liste complète |
| `/logs` | Journal événementiel |
| `/settings` | Configuration |

---

## Stack technique

| Composant | Technologie |
|---|---|
| Backend | FastAPI + Uvicorn |
| Base de données | SQLite via SQLAlchemy |
| Scheduler | APScheduler |
| Templates | Jinja2 |
| Frontend | HTML / CSS / JS vanilla |
| i18n | Module custom — 6 langues |

---

## Prérequis

- Python 3.10+
- Jellyfin, Radarr, Sonarr et Transmission accessibles sur ton réseau local

---

## Installation

**1. Cloner le dépôt**

```bash
git clone https://github.com/Lekarov/Purgearr.git
cd Purgearr
```

**2. Environnement virtuel + dépendances**

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**3. Démarrage**

```bash
python main.py
```

L'interface est accessible sur `http://[IP]:7979`. Configure tous les services depuis la page **Paramètres** au premier lancement.

**4. Le dossier `data/` — ne jamais supprimer**

```
data/
├── config.json        ← configuration (URLs, clés API, règles)
├── protected.json     ← whitelist des contenus protégés
├── purgearr.db        ← historique, queue, événements watch
└── cache/             ← cache temporaire (régénéré automatiquement)
```

> Ce dossier est exclu de git — tes données sont préservées lors des mises à jour.

---

## Service systemd (Raspberry Pi)

```ini
[Unit]
Description=Purgearr Media Manager
After=network.target

[Service]
Type=simple
WorkingDirectory=/chemin/vers/Purgearr
ExecStart=/chemin/vers/Purgearr/venv/bin/python main.py
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

## Webhook Jellyfin (optionnel)

Le webhook reçoit les événements `PlaybackStop` de Jellyfin en temps réel. Installe le plugin **Webhook** depuis le catalogue Jellyfin :

- **URL** : `http://[IP]:7979/webhook/jellyfin`
- **Événement** : `Playback Stop`

> Le mode Auto (suppression automatique au stop de lecture) est en cours de stabilisation — utilise uniquement la suppression manuelle depuis l'interface.

---

## Mise à jour

```bash
git pull
sudo systemctl restart purgearr
```

---

## Confidentialité

Purgearr fonctionne **entièrement sur ta propre machine** — aucune donnée ne quitte jamais ton réseau.

- Pas d'analytics, pas de télémétrie, pas de service externe
- Tous les appels API vont directement vers tes instances locales de Jellyfin, Radarr, Sonarr et Transmission
- La configuration est stockée localement dans `data/config.json`

**Le code source est entièrement auditable** — chaque ligne est dans ce dépôt.

---

## Licence

MIT — utilise et adapte librement.

---

<div align="center">
  Made by <a href="https://github.com/Lekarov">Pestovich</a>
</div>
