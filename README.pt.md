<div align="center">

# Purgearr

[![en](https://img.shields.io/badge/lang-en-red.svg)](https://github.com/Lekarov/Purgearr/blob/master/README.md)
[![fr](https://img.shields.io/badge/lang-fr-blue.svg)](https://github.com/Lekarov/Purgearr/blob/master/README.fr.md)
[![es](https://img.shields.io/badge/lang-es-yellow.svg)](https://github.com/Lekarov/Purgearr/blob/master/README.es.md)
[![pt](https://img.shields.io/badge/lang-pt-green.svg)](https://github.com/Lekarov/Purgearr/blob/master/README.pt.md)
[![de](https://img.shields.io/badge/lang-de-lightgrey.svg)](https://github.com/Lekarov/Purgearr/blob/master/README.de.md)
[![it](https://img.shields.io/badge/lang-it-008C45.svg)](https://github.com/Lekarov/Purgearr/blob/master/README.it.md)

**Elimina a desordem. Guarda o essencial. Uma interface para toda a tua biblioteca multimédia.**

![Estado](https://img.shields.io/badge/estado-beta-orange?style=flat-square)
![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white) ![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)
![Licença](https://img.shields.io/badge/licença-MIT-6b7491?style=flat-square)
![Jellyfin](https://img.shields.io/badge/Jellyfin-00A4DC?style=flat-square&logo=jellyfin&logoColor=white) ![Radarr](https://img.shields.io/badge/Radarr-FFC230?style=flat-square) ![Sonarr](https://img.shields.io/badge/Sonarr-35C5F4?style=flat-square) ![Transmission](https://img.shields.io/badge/Transmission-CC0000?style=flat-square)
![Idiomas](https://img.shields.io/badge/idiomas-6-orange?style=flat-square)

</div>

---

## Capturas de ecrã

<div align="center">

| Vistos | Sugestões — Nunca vistos |
|:---:|:---:|
| ![Watched](https://i.ibb.co/0y7d7PzZ/Capture-d-cran-2026-07-24-163340.png) | ![Never watched](https://i.ibb.co/h1Y1vT7w/Capture-d-cran-2026-07-24-163441.png) |

| Torrents mortos (rácio 0) | Histórico de eliminações |
|:---:|:---:|
| ![Dead seed](https://i.ibb.co/DfB94tz7/Capture-d-cran-2026-07-24-163523.png) | ![History](https://i.ibb.co/t98YjsP/Capture-d-cran-2026-07-24-163616.png) |

| Registo de eventos | Modal de confirmação |
|:---:|:---:|
| ![Event log](https://i.ibb.co/7NWmHB7m/Capture-d-cran-2026-07-24-163649.png) | ![Confirm deletion](https://i.ibb.co/WCCbMbD/Capture-d-cran-2026-07-24-163748.png) |

</div>

---

## O que faz

Purgearr é uma interface web auto-alojada para configurações de **Jellyfin + Radarr + Sonarr + Transmission**. Oferece uma visão completa da tua biblioteca multimédia, deteta conteúdo que nunca foi visto, sinaliza torrents mortos a desperdiçar espaço em disco e permite eliminar de forma limpa — o ficheiro, a entrada Radarr/Sonarr e o torrent numa única ação.

Nunca o viste. Nunca o verás. Eliminado.

---

## Funcionalidades

- **Dashboard** — estatísticas globais da biblioteca, fila de eliminação, histórico recente
- **Vistos** — lista completa de conteúdo visto com progresso por utilizador e estado "pronto a eliminar"
- **Sugestões** — nunca vistos / parcialmente vistos / torrents mortos (rácio 0) com estatísticas de seeding em tempo real
- **Catálogo** — vista completa da biblioteca Jellyfin, Filmes e Séries separados, paginada (60/pág.), com pesquisa, ordenação e filtros de estado
- **Lista branca** — protege qualquer título permanentemente; os favoritos do Jellyfin são automaticamente protegidos
- **Histórico** — todas as eliminações passadas com scanner de cópias residuais
- **Registo** — diário filtrável de cada operação, por categoria e nível
- **Definições** — configuração completa a partir da interface web, sem editar ficheiros
- **Multi-utilizador** — define utilizadores obrigatórios; a eliminação só é sugerida quando todos viram
- **Multi-tracker** — deteta todos os torrents a fazer seed do mesmo ficheiro em vários trackers, deduplicado para o cálculo de tamanho
- **Deteção de hardlinks** — análise inode + SHA-256 antes de eliminar para detetar cópias
- **Modal de confirmação** — mostra exatamente o que será eliminado antes de cada ação
- **Idioma** — 6 idiomas

---

## Páginas

| URL | Descrição |
|---|---|
| `/` | Dashboard — estatísticas, fila, histórico recente |
| `/watched` | Lista de conteúdo visto |
| `/suggestions` | Nunca vistos / torrents mortos / parcialmente vistos |
| `/catalogue` | Catálogo completo — pesquisa, ordenação, filtros |
| `/protected` | Gestão da lista branca |
| `/history` | Eliminações passadas + scanner de restos |
| `/transmission` | Torrents órfãos + lista completa |
| `/logs` | Registo de eventos |
| `/settings` | Configuração |

---

## Stack tecnológico

| Componente | Tecnologia |
|---|---|
| Backend | FastAPI + Uvicorn |
| Base de dados | SQLite via SQLAlchemy |
| Agendador | APScheduler |
| Templates | Jinja2 |
| Frontend | HTML / CSS / JS vanilla |
| i18n | Módulo personalizado — 6 idiomas |

---

## Requisitos

- Python 3.10+
- Jellyfin, Radarr, Sonarr e Transmission acessíveis na tua rede local

---

## Instalação

**1. Clonar o repositório**

```bash
git clone https://github.com/Lekarov/Purgearr.git
cd Purgearr
```

**2. Ambiente virtual + dependências**

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**3. Iniciar**

```bash
python main.py
```

A interface está disponível em `http://[IP]:7979`. Configura todos os serviços na página **Definições** no primeiro início.

**4. A pasta `data/` — nunca eliminar**

```
data/
├── config.json        ← configuração (URLs, chaves API, regras)
├── protected.json     ← lista branca de conteúdo protegido
├── purgearr.db        ← histórico, fila, eventos de visualização
└── cache/             ← cache temporário (regenerado automaticamente)
```

> Esta pasta está excluída do git — os teus dados são preservados nas atualizações.

---

## Serviço systemd (Raspberry Pi)

```ini
[Unit]
Description=Purgearr Media Manager
After=network.target

[Service]
Type=simple
WorkingDirectory=/caminho/para/Purgearr
ExecStart=/caminho/para/Purgearr/venv/bin/python main.py
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

## Webhook do Jellyfin (opcional)

O webhook recebe eventos `PlaybackStop` do Jellyfin em tempo real. Instala o plugin **Webhook** a partir do catálogo do Jellyfin:

- **URL**: `http://[IP]:7979/webhook/jellyfin`
- **Evento**: `Playback Stop`

> O modo Auto (eliminação automática ao parar a reprodução) está em estabilização — usa apenas a eliminação manual a partir da interface.

---

## Controlo pelo Telegram (DoktorTV Bot)

O Purgearr pode ser controlado pelo Telegram com o **[DoktorTV Bot](https://github.com/Lekarov/DoktorTV-Bot)**: sugestões de remoção uma a uma (filmes vistos, séries vistas ou começadas, nunca vistos, os mais pesados), ficha com póster, **pré-visualização exata** do que será removido (biblioteca, torrents por tracker, hardlinks, links cross-seed, cópias) e confirmação.

- O bot usa as rotas `/api/bot/*` (Purgearr **1.2.0+**). No `.env` do bot: `PURGEARR_URL=http://[IP]:7979`
- Teste: `curl http://[IP]:7979/api/bot/ping`

---

## Atualização

```bash
git pull
sudo systemctl restart purgearr
```

---

## Privacidade

O Purgearr funciona **inteiramente na tua própria máquina** — nenhum dado abandona a tua rede.

- Sem análises, sem telemetria, sem serviços externos
- Todas as chamadas API vão diretamente para as tuas instâncias locais de Jellyfin, Radarr, Sonarr e Transmission
- A configuração é armazenada localmente em `data/config.json`

**O código fonte é totalmente auditável** — cada linha está neste repositório.

---

## Licença

MIT — usa e adapta livremente.

---

<div align="center">
  Made by <a href="https://github.com/Lekarov">Pestovich</a>
</div>
