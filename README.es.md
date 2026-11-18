<div align="center">

# Purgearr

[![en](https://img.shields.io/badge/lang-en-red.svg)](https://github.com/Lekarov/Purgearr/blob/master/README.md)
[![fr](https://img.shields.io/badge/lang-fr-blue.svg)](https://github.com/Lekarov/Purgearr/blob/master/README.fr.md)
[![es](https://img.shields.io/badge/lang-es-yellow.svg)](https://github.com/Lekarov/Purgearr/blob/master/README.es.md)
[![pt](https://img.shields.io/badge/lang-pt-green.svg)](https://github.com/Lekarov/Purgearr/blob/master/README.pt.md)
[![de](https://img.shields.io/badge/lang-de-lightgrey.svg)](https://github.com/Lekarov/Purgearr/blob/master/README.de.md)
[![it](https://img.shields.io/badge/lang-it-008C45.svg)](https://github.com/Lekarov/Purgearr/blob/master/README.it.md)

**Elimina el desorden. Conserva lo esencial. Una interfaz para toda tu biblioteca multimedia.**

![Estado](https://img.shields.io/badge/estado-beta-orange?style=flat-square)
![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white) ![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)
![Licencia](https://img.shields.io/badge/licencia-MIT-6b7491?style=flat-square)
![Jellyfin](https://img.shields.io/badge/Jellyfin-00A4DC?style=flat-square&logo=jellyfin&logoColor=white) ![Radarr](https://img.shields.io/badge/Radarr-FFC230?style=flat-square) ![Sonarr](https://img.shields.io/badge/Sonarr-35C5F4?style=flat-square) ![Transmission](https://img.shields.io/badge/Transmission-CC0000?style=flat-square)
![Idiomas](https://img.shields.io/badge/idiomas-6-orange?style=flat-square)

</div>

---

## Capturas de pantalla

<div align="center">

| Vistos | Sugerencias — Nunca vistos |
|:---:|:---:|
| ![Watched](https://i.ibb.co/0y7d7PzZ/Capture-d-cran-2026-07-24-163340.png) | ![Never watched](https://i.ibb.co/h1Y1vT7w/Capture-d-cran-2026-07-24-163441.png) |

| Torrents muertos (ratio 0) | Historial de eliminaciones |
|:---:|:---:|
| ![Dead seed](https://i.ibb.co/DfB94tz7/Capture-d-cran-2026-07-24-163523.png) | ![History](https://i.ibb.co/t98YjsP/Capture-d-cran-2026-07-24-163616.png) |

| Registro de eventos | Modal de confirmación |
|:---:|:---:|
| ![Event log](https://i.ibb.co/7NWmHB7m/Capture-d-cran-2026-07-24-163649.png) | ![Confirm deletion](https://i.ibb.co/WCCbMbD/Capture-d-cran-2026-07-24-163748.png) |

</div>

---

## Qué hace

Purgearr es una interfaz web autoalojada para configuraciones de **Jellyfin + Radarr + Sonarr + Transmission**. Ofrece una vista completa de tu biblioteca multimedia, detecta contenido que nunca se ha visto, señala torrents muertos que ocupan espacio en disco y permite eliminar limpiamente — el archivo, la entrada de Radarr/Sonarr y el torrent en una sola acción.

Nunca lo viste. Nunca lo verás. Eliminado.

---

## Funcionalidades

- **Dashboard** — estadísticas globales, cola de eliminación, historial reciente
- **Vistos** — lista completa de contenido visto con progreso por usuario y estado "listo para eliminar"
- **Sugerencias** — nunca vistos / parcialmente vistos / torrents muertos (ratio 0) con estadísticas de seeding en tiempo real
- **Catálogo** — vista completa de la biblioteca Jellyfin, Películas y Series separadas, paginada (60/pág.), con búsqueda, orden y filtros de estado
- **Lista blanca** — protege cualquier título permanentemente; los favoritos de Jellyfin se protegen automáticamente
- **Historial** — todas las eliminaciones pasadas con escáner de copias residuales
- **Registro** — diario filtrable de cada operación, por categoría y nivel
- **Configuración** — configuración completa desde la interfaz web, sin editar archivos
- **Multi-usuario** — define espectadores requeridos; la eliminación solo se sugiere cuando todos han visto
- **Multi-tracker** — detecta todos los torrents que seedean el mismo archivo en varios trackers, deduplicado para el cálculo de tamaño
- **Detección de hardlinks** — escaneo inode + SHA-256 antes de eliminar para detectar copias
- **Modal de confirmación** — muestra exactamente lo que se eliminará antes de cada acción
- **Idioma** — 6 idiomas

---

## Páginas

| URL | Descripción |
|---|---|
| `/` | Dashboard — estadísticas, cola, historial reciente |
| `/watched` | Lista de contenido visto |
| `/suggestions` | Nunca vistos / torrents muertos / parcialmente vistos |
| `/catalogue` | Catálogo completo — búsqueda, orden, filtros |
| `/protected` | Gestión de lista blanca |
| `/history` | Eliminaciones pasadas + escáner de restos |
| `/transmission` | Torrents huérfanos + lista completa |
| `/logs` | Registro de eventos |
| `/settings` | Configuración |

---

## Stack tecnológico

| Componente | Tecnología |
|---|---|
| Backend | FastAPI + Uvicorn |
| Base de datos | SQLite via SQLAlchemy |
| Planificador | APScheduler |
| Plantillas | Jinja2 |
| Frontend | HTML / CSS / JS vanilla |
| i18n | Módulo personalizado — 6 idiomas |

---

## Requisitos

- Python 3.10+
- Jellyfin, Radarr, Sonarr y Transmission accesibles en tu red local

---

## Instalación

**1. Clonar el repositorio**

```bash
git clone https://github.com/Lekarov/Purgearr.git
cd Purgearr
```

**2. Entorno virtual + dependencias**

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**3. Inicio**

```bash
python main.py
```

La interfaz está disponible en `http://[IP]:7979`. Configura todos los servicios desde la página **Configuración** en el primer inicio.

**4. La carpeta `data/` — nunca eliminar**

```
data/
├── config.json        ← configuración (URLs, claves API, reglas)
├── protected.json     ← lista blanca de contenido protegido
├── purgearr.db        ← historial, cola, eventos de visualización
└── cache/             ← caché temporal (regenerado automáticamente)
```

> Esta carpeta está excluida de git — tus datos se preservan en las actualizaciones.

---

## Servicio systemd (Raspberry Pi)

```ini
[Unit]
Description=Purgearr Media Manager
After=network.target

[Service]
Type=simple
WorkingDirectory=/ruta/a/Purgearr
ExecStart=/ruta/a/Purgearr/venv/bin/python main.py
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

## Webhook de Jellyfin (opcional)

El webhook recibe eventos `PlaybackStop` de Jellyfin en tiempo real. Instala el plugin **Webhook** desde el catálogo de Jellyfin:

- **URL**: `http://[IP]:7979/webhook/jellyfin`
- **Evento**: `Playback Stop`

> El modo Auto (eliminación automática al detener la reproducción) está en estabilización — usa solo la eliminación manual desde la interfaz.

---

## Control desde Telegram (DoktorTV Bot)

Purgearr se puede controlar desde Telegram con **[DoktorTV Bot](https://github.com/Lekarov/DoktorTV-Bot)**: sugerencias de borrado una a una (películas vistas, series vistas o empezadas, nunca vistas, las más pesadas), ficha con póster, **vista previa exacta** de lo que se borrará (biblioteca, torrents por tracker, hardlinks, enlaces cross-seed, copias) y confirmación.

- El bot usa las rutas `/api/bot/*` (Purgearr **1.2.0+**). En el `.env` del bot: `PURGEARR_URL=http://[IP]:7979`
- Prueba: `curl http://[IP]:7979/api/bot/ping`

---

## Actualización

```bash
git pull
sudo systemctl restart purgearr
```

---

## Privacidad

Purgearr funciona **completamente en tu propia máquina** — ningún dato abandona tu red.

- Sin analíticas, sin telemetría, sin servicios externos
- Todas las llamadas API van directamente a tus instancias locales de Jellyfin, Radarr, Sonarr y Transmission
- La configuración se almacena localmente en `data/config.json`

**El código fuente es completamente auditable** — cada línea está en este repositorio.

---

## Licencia

MIT — usa y adapta libremente.

---

<div align="center">
  Made by <a href="https://github.com/Lekarov">Pestovich</a>
</div>
