<div align="center">

# Purgearr

[![en](https://img.shields.io/badge/lang-en-red.svg)](https://github.com/Lekarov/Purgearr/blob/master/README.md)
[![fr](https://img.shields.io/badge/lang-fr-blue.svg)](https://github.com/Lekarov/Purgearr/blob/master/README.fr.md)
[![es](https://img.shields.io/badge/lang-es-yellow.svg)](https://github.com/Lekarov/Purgearr/blob/master/README.es.md)
[![pt](https://img.shields.io/badge/lang-pt-green.svg)](https://github.com/Lekarov/Purgearr/blob/master/README.pt.md)
[![de](https://img.shields.io/badge/lang-de-lightgrey.svg)](https://github.com/Lekarov/Purgearr/blob/master/README.de.md)
[![it](https://img.shields.io/badge/lang-it-008C45.svg)](https://github.com/Lekarov/Purgearr/blob/master/README.it.md)

**Elimina il disordine. Tieni l'essenziale. Un'interfaccia per tutta la tua libreria multimediale.**

![Stato](https://img.shields.io/badge/stato-beta-orange?style=flat-square)
![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white) ![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)
![Licenza](https://img.shields.io/badge/licenza-MIT-6b7491?style=flat-square)
![Jellyfin](https://img.shields.io/badge/Jellyfin-00A4DC?style=flat-square&logo=jellyfin&logoColor=white) ![Radarr](https://img.shields.io/badge/Radarr-FFC230?style=flat-square) ![Sonarr](https://img.shields.io/badge/Sonarr-35C5F4?style=flat-square) ![Transmission](https://img.shields.io/badge/Transmission-CC0000?style=flat-square)
![Lingue](https://img.shields.io/badge/lingue-6-orange?style=flat-square)

</div>

---

## Screenshot

<div align="center">

| Visti | Suggerimenti — Mai visti |
|:---:|:---:|
| ![Watched](https://i.ibb.co/0y7d7PzZ/Capture-d-cran-2026-07-24-163340.png) | ![Never watched](https://i.ibb.co/h1Y1vT7w/Capture-d-cran-2026-07-24-163441.png) |

| Torrent morti (rapporto 0) | Cronologia eliminazioni |
|:---:|:---:|
| ![Dead seed](https://i.ibb.co/DfB94tz7/Capture-d-cran-2026-07-24-163523.png) | ![History](https://i.ibb.co/t98YjsP/Capture-d-cran-2026-07-24-163616.png) |

| Registro eventi | Finestra di conferma |
|:---:|:---:|
| ![Event log](https://i.ibb.co/7NWmHB7m/Capture-d-cran-2026-07-24-163649.png) | ![Confirm deletion](https://i.ibb.co/WCCbMbD/Capture-d-cran-2026-07-24-163748.png) |

</div>

---

## Cosa fa

Purgearr è un'interfaccia web self-hosted per configurazioni **Jellyfin + Radarr + Sonarr + Transmission**. Offre una visione completa della tua libreria multimediale, individua i contenuti mai visti, segnala i torrent morti che sprecano spazio su disco e consente di eliminare in modo pulito — il file, la voce Radarr/Sonarr e il torrent in un'unica azione.

Non l'hai mai visto. Non lo vedrai mai. Eliminato.

---

## Funzionalità

- **Dashboard** — statistiche globali della libreria, coda di eliminazione, cronologia recente
- **Visti** — elenco completo dei contenuti visti con avanzamento per utente e stato "pronto per l'eliminazione"
- **Suggerimenti** — mai visti / parzialmente visti / torrent morti (rapporto 0) con statistiche di seeding in tempo reale
- **Catalogo** — vista completa della libreria Jellyfin, Film e Serie separati, paginata (60/pag.), con ricerca, ordinamento e filtri di stato
- **Lista bianca** — protegge qualsiasi titolo in modo permanente; i preferiti Jellyfin sono automaticamente protetti
- **Cronologia** — tutte le eliminazioni passate con scanner per copie residue
- **Registro** — diario filtrabile di ogni operazione, per categoria e livello
- **Impostazioni** — configurazione completa dall'interfaccia web, senza modificare file
- **Multi-utente** — definisce gli spettatori richiesti; l'eliminazione viene suggerita solo quando tutti hanno visto
- **Multi-tracker** — rileva tutti i torrent che fanno seeding dello stesso file su più tracker, deduplicato per il calcolo delle dimensioni
- **Rilevamento hardlink** — scansione inode + SHA-256 prima dell'eliminazione per rilevare copie
- **Finestra di conferma** — mostra esattamente cosa verrà eliminato prima di ogni azione
- **Lingua** — 6 lingue

---

## Pagine

| URL | Descrizione |
|---|---|
| `/` | Dashboard — statistiche, coda, cronologia recente |
| `/watched` | Elenco dei contenuti visti |
| `/suggestions` | Mai visti / torrent morti / parzialmente visti |
| `/catalogue` | Catalogo completo — ricerca, ordinamento, filtri |
| `/protected` | Gestione della lista bianca |
| `/history` | Eliminazioni passate + scanner dei resti |
| `/transmission` | Torrent orfani + elenco completo |
| `/logs` | Registro eventi |
| `/settings` | Configurazione |

---

## Stack tecnologico

| Componente | Tecnologia |
|---|---|
| Backend | FastAPI + Uvicorn |
| Database | SQLite via SQLAlchemy |
| Scheduler | APScheduler |
| Template | Jinja2 |
| Frontend | HTML / CSS / JS vanilla |
| i18n | Modulo personalizzato — 6 lingue |

---

## Requisiti

- Python 3.10+
- Jellyfin, Radarr, Sonarr e Transmission accessibili nella tua rete locale

---

## Installazione

**1. Clonare il repository**

```bash
git clone https://github.com/Lekarov/Purgearr.git
cd Purgearr
```

**2. Ambiente virtuale + dipendenze**

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**3. Avvio**

```bash
python main.py
```

L'interfaccia è disponibile su `http://[IP]:7979`. Configura tutti i servizi dalla pagina **Impostazioni** al primo avvio.

**4. La cartella `data/` — non eliminare mai**

```
data/
├── config.json        ← configurazione (URL, chiavi API, regole)
├── protected.json     ← lista bianca dei contenuti protetti
├── purgearr.db        ← cronologia, coda, eventi di visualizzazione
└── cache/             ← cache temporanea (rigenerata automaticamente)
```

> Questa cartella è esclusa da git — i tuoi dati vengono preservati durante gli aggiornamenti.

---

## Servizio systemd (Raspberry Pi)

```ini
[Unit]
Description=Purgearr Media Manager
After=network.target

[Service]
Type=simple
WorkingDirectory=/percorso/a/Purgearr
ExecStart=/percorso/a/Purgearr/venv/bin/python main.py
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

## Webhook Jellyfin (opzionale)

Il webhook riceve eventi `PlaybackStop` da Jellyfin in tempo reale. Installa il plugin **Webhook** dal catalogo Jellyfin:

- **URL**: `http://[IP]:7979/webhook/jellyfin`
- **Evento**: `Playback Stop`

> La modalità Auto (eliminazione automatica all'arresto della riproduzione) è in fase di stabilizzazione — usa solo l'eliminazione manuale dall'interfaccia.

---

## Controllo da Telegram (DoktorTV Bot)

Purgearr si può controllare da Telegram con **[DoktorTV Bot](https://github.com/Lekarov/DoktorTV-Bot)**: suggerimenti di eliminazione uno alla volta (film visti, serie viste o iniziate, mai visti, i più pesanti), scheda con locandina, **anteprima esatta** di ciò che verrà eliminato (libreria, torrent per tracker, hardlink, link cross-seed, copie) e conferma.

- Il bot usa le rotte `/api/bot/*` (Purgearr **1.2.0+**). Nel `.env` del bot: `PURGEARR_URL=http://[IP]:7979`
- Test: `curl http://[IP]:7979/api/bot/ping`

---

## Aggiornamento

```bash
git pull
sudo systemctl restart purgearr
```

---

## Privacy

Purgearr funziona **interamente sulla tua macchina** — nessun dato lascia mai la tua rete.

- Nessuna analisi, nessuna telemetria, nessun servizio esterno
- Tutte le chiamate API vanno direttamente alle tue istanze locali di Jellyfin, Radarr, Sonarr e Transmission
- La configurazione è memorizzata localmente in `data/config.json`

**Il codice sorgente è completamente verificabile** — ogni riga è in questo repository.

---

## Licenza

MIT — usa e adatta liberamente.

---

<div align="center">
  Made by <a href="https://github.com/Lekarov">Pestovich</a>
</div>
