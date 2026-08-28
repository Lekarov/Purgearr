import json
import logging
import os
from datetime import datetime
from typing import Dict

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import desc
from sqlalchemy.orm import Session

from config import PROTECTED_LOCK, get_config, get_extra_paths, get_mode, get_protected, get_rules, get_scan_paths, resolve_real_path, save_config, save_protected
from i18n import SUPPORTED_LANGUAGES
from core import eventlog
from core.pipeline import delete_episode, delete_movie, process_queue
from core.sync import sync_watch_data
from scheduler import INTERVAL_OPTIONS, restart_jobs
from database import DeletionHistory, DeletionQueue, WatchEvent, get_db
from services.factory import get_jellyfin, get_radarr, get_sonarr, get_transmission
from api.templates import templates
from api.route_suggestions import router as suggestions_router
from api.route_transmission import router as transmission_router
from api.route_cleanup import router as cleanup_router
from api.route_logs import router as logs_router
from api.route_catalogue import router as catalogue_router

logger = logging.getLogger("purgearr.routes")
router = APIRouter(tags=["dashboard"])
router.include_router(suggestions_router)
router.include_router(transmission_router)
router.include_router(cleanup_router)
router.include_router(logs_router)
router.include_router(catalogue_router)


# ── Dashboard ─────────────────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    stats = {
        "movies_deleted": db.query(DeletionHistory).filter(DeletionHistory.item_type == "Movie").count(),
        "episodes_deleted": db.query(DeletionHistory).filter(DeletionHistory.item_type == "Episode").count(),
        "queue_pending": db.query(DeletionQueue).filter(DeletionQueue.status == "pending").count(),
        "protected": len(get_protected().get("titles", [])) + len(get_protected().get("jellyfin_ids", [])),
    }
    queue = (
        db.query(DeletionQueue)
        .filter(DeletionQueue.status == "pending")
        .order_by(DeletionQueue.scheduled_at)
        .limit(10)
        .all()
    )
    recent = (
        db.query(DeletionHistory)
        .order_by(desc(DeletionHistory.deleted_at))
        .limit(10)
        .all()
    )
    return templates.TemplateResponse(
        request=request, name="dashboard.html",
        context={"stats": stats, "queue": queue, "recent": recent},
    )


# ── Historique ────────────────────────────────────────────────────────────────

@router.get("/history", response_class=HTMLResponse)
def history(request: Request, db: Session = Depends(get_db)):
    items = db.query(DeletionHistory).order_by(desc(DeletionHistory.deleted_at)).all()
    for item in items:
        try:
            item.services_list = json.loads(item.deleted_from or "[]")
        except Exception:
            item.services_list = []
        try:
            item.details_data = json.loads(item.details_json or "{}")
        except Exception:
            item.details_data = {}
    return templates.TemplateResponse(request=request, name="history.html", context={"items": items})


# ── Paramètres ────────────────────────────────────────────────────────────────

@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request):
    cfg = get_config()
    cfg.setdefault("logs", {})
    cfg["logs"].setdefault("enabled", True)
    cfg["logs"].setdefault("retention_days", 30)
    cfg["logs"].setdefault("max_entries", 10000)
    try:
        jf_users = get_jellyfin().get_users()
    except Exception:
        jf_users = []
    return templates.TemplateResponse(request=request, name="settings.html",
        context={"cfg": cfg, "saved": False, "interval_options": INTERVAL_OPTIONS, "jf_users": jf_users,
                 "extra_paths": get_extra_paths()})


@router.post("/settings", response_class=HTMLResponse)
def settings_save(
    request: Request,
    # Connexions
    jellyfin_url: str = Form(""),
    jellyfin_api_key: str = Form(""),
    radarr_url: str = Form(""),
    radarr_api_key: str = Form(""),
    sonarr_url: str = Form(""),
    sonarr_api_key: str = Form(""),
    trans_host: str = Form(""),
    trans_port: int = Form(9091),
    trans_user: str = Form(""),
    trans_pass: str = Form(""),
    # Règles
    watch_pct: int = Form(85),
    delay_hours: int = Form(0),
    multi_user_mode: str = Form("any"),
    watched_users: str = Form(""),
    delete_files: bool = Form(False),
    add_to_exclusion: bool = Form(False),
    disk_threshold: int = Form(0),
    movies_enabled: bool = Form(False),
    movies_pct: int = Form(85),
    movies_delay: int = Form(0),
    series_enabled: bool = Form(False),
    series_mode: str = Form("episode"),
    series_pct: int = Form(85),
    series_delay: int = Form(0),
    queue_interval: int = Form(360),
    scan_interval: int = Form(360),
    primary_user: str = Form(""),
    required_users_csv: str = Form(""),
    extra_paths_raw: str = Form(""),
    library_root_movies: str = Form(""),
    library_root_series: str = Form(""),
    logs_enabled: bool = Form(False),
    logs_retention_days: int = Form(30),
    logs_max_entries: int = Form(10000),
    language: str = Form("fr"),
):
    cfg = get_config()
    users_list       = [u.strip() for u in watched_users.splitlines() if u.strip()]
    required_list    = [u.strip() for u in required_users_csv.split(",") if u.strip()]
    extra_paths_list = [p.strip() for p in extra_paths_raw.splitlines() if p.strip()]
    current_mode     = cfg.get("rules", {}).get("mode", "manual")

    cfg["jellyfin"]          = {"url": jellyfin_url, "api_key": jellyfin_api_key}
    cfg["radarr"]            = {"url": radarr_url,   "api_key": radarr_api_key}
    cfg["sonarr"]            = {"url": sonarr_url,   "api_key": sonarr_api_key}
    cfg["transmission"]      = {
        "host": trans_host, "port": trans_port,
        "username": trans_user or None, "password": trans_pass or None,
    }
    cfg["library_root_movies"] = library_root_movies.strip() or cfg.get("library_root_movies", "")
    cfg["library_root_series"] = library_root_series.strip() or cfg.get("library_root_series", "")
    cfg["rules"] = {
        "mode":                       current_mode,
        "primary_user":               primary_user,
        "required_users":             required_list,
        "watch_percentage_threshold": watch_pct,
        "deletion_delay_hours":       delay_hours,
        "multi_user_mode":            multi_user_mode,
        "watched_users":              users_list,
        "delete_files":               delete_files,
        "add_to_exclusion":           add_to_exclusion,
        "disk_usage_threshold":       disk_threshold,
        "movies": {
            "enabled":                    movies_enabled,
            "watch_percentage_threshold": movies_pct,
            "deletion_delay_hours":       movies_delay,
        },
        "series": {
            "enabled":                    series_enabled,
            "delete_mode":                series_mode,
            "watch_percentage_threshold": series_pct,
            "deletion_delay_hours":       series_delay,
        },
    }
    cfg["scheduler"]    = {"queue_interval_minutes": queue_interval, "scan_interval_minutes": scan_interval}
    cfg["extra_paths"]  = extra_paths_list
    cfg["logs"] = {
        "enabled":        logs_enabled,
        "retention_days": max(1, int(logs_retention_days)),
        "max_entries":    max(100, int(logs_max_entries)),
    }
    cfg["language"] = language if language in SUPPORTED_LANGUAGES else "fr"

    save_config(cfg)
    restart_jobs()
    eventlog.info("config", "Paramètres enregistrés",
                  mode=current_mode, scheduler={"queue": queue_interval, "scan": scan_interval})

    try:
        jf_users = get_jellyfin().get_users()
    except Exception:
        jf_users = []
    return templates.TemplateResponse(request=request, name="settings.html",
        context={"cfg": cfg, "saved": True, "interval_options": INTERVAL_OPTIONS, "jf_users": jf_users,
                 "extra_paths": extra_paths_list})


# ── Liste de protection ───────────────────────────────────────────────────────

@router.get("/protected", response_class=HTMLResponse)
def protected_page(request: Request):
    p   = get_protected()
    cfg = get_config()
    jellyfin_url     = cfg["jellyfin"]["url"].rstrip("/")
    jellyfin_api_key = cfg["jellyfin"]["api_key"]

    protected_items: list = []
    try:
        jf    = get_jellyfin()
        users = jf.get_users()
        admin = users[0]["Id"] if users else None

        # Items avec ID Jellyfin
        for jid in (p.get("jellyfin_ids") or []):
            try:
                it = jf.get_item(jid, user_id=admin)
                name = it.get("Name") or it.get("OriginalTitle") or jid
                protected_items.append({
                    "id":        jid,
                    "title":     name,
                    "type":      it.get("Type", "Movie"),
                    "image_url": f"{jellyfin_url}/Items/{jid}/Images/Primary?fillWidth=220&quality=80&api_key={jellyfin_api_key}",
                    "source":    "id",
                })
            except Exception as e:
                logger.warning("[Protected] get_item(%s) failed: %s", jid, e)
                protected_items.append({
                    "id": jid, "title": f"ID: {jid[:12]}…", "type": "Movie",
                    "image_url": "", "source": "id",
                })

        # Items avec titre uniquement — recherche Jellyfin pour avoir l'image
        for title in (p.get("titles") or []):
            found = None
            if admin:
                try:
                    results = jf.search_items(admin, title, limit=1)
                    if results:
                        found = results[0]
                except Exception:
                    pass
            if found:
                protected_items.append({
                    "id":        None,
                    "title":     title,
                    "type":      found.get("Type", "Movie"),
                    "image_url": f"{jellyfin_url}/Items/{found['Id']}/Images/Primary?fillWidth=220&quality=80&api_key={jellyfin_api_key}",
                    "source":    "title",
                })
            else:
                protected_items.append({
                    "id": None, "title": title, "type": "Movie",
                    "image_url": "", "source": "title",
                })
        # Favoris Jellyfin — protection automatique, indépendante de la whitelist manuelle
        # favorites_info : { item_id: {"title": str, "type": str, "users": [{"id","name"}, ...]} }
        favorites_info: Dict[str, Dict] = {}
        for u in users:
            try:
                for it in jf.get_favorite_items(u["Id"]):
                    entry = favorites_info.setdefault(it["Id"], {
                        "title": it.get("Name") or it["Id"],
                        "type":  it.get("Type", "Movie"),
                        "users": [],
                    })
                    entry["users"].append({"id": u["Id"], "name": u.get("Name", "?")})
            except Exception as e:
                logger.warning("[Protected] favoris KO pour %s : %s", u.get("Name"), e)

        # Rattacher les favoris aux entrées whitelist déjà listées (par ID, sinon par titre)
        for p_item in protected_items:
            if p_item.get("id") and p_item["id"] in favorites_info:
                p_item["favorited_by"] = favorites_info.pop(p_item["id"])["users"]
                continue
            match_id = next(
                (fid for fid, info in favorites_info.items()
                 if info["title"].lower() == p_item["title"].lower()),
                None,
            )
            if match_id:
                p_item["favorited_by"] = favorites_info.pop(match_id)["users"]

        # Ajouter les favoris Jellyfin qui ne sont pas déjà dans la whitelist
        for fid, info in favorites_info.items():
            protected_items.append({
                "id":           fid,
                "title":        info["title"],
                "type":         info["type"],
                "image_url":    f"{jellyfin_url}/Items/{fid}/Images/Primary?fillWidth=220&quality=80&api_key={jellyfin_api_key}",
                "source":       "favorite",
                "favorited_by": info["users"],
            })
    except Exception:
        for jid in (p.get("jellyfin_ids") or []):
            protected_items.append({"id": jid, "title": jid, "type": "Movie", "image_url": "", "source": "id"})
        for title in (p.get("titles") or []):
            protected_items.append({"id": None, "title": title, "type": "Movie", "image_url": "", "source": "title"})

    return templates.TemplateResponse(request=request, name="protected.html",
                                      context={"protected": p, "protected_items": protected_items})


@router.post("/protected/add")
def protected_add(title: str = Form(""), jellyfin_id: str = Form("")):
    with PROTECTED_LOCK:
        p = get_protected()
        p.setdefault("titles", [])
        p.setdefault("jellyfin_ids", [])
        added = []
        if title and title not in p["titles"]:
            p["titles"].append(title)
            added.append(f"titre={title}")
        if jellyfin_id and jellyfin_id not in p["jellyfin_ids"]:
            p["jellyfin_ids"].append(jellyfin_id)
            added.append(f"id={jellyfin_id}")
        save_protected(p)
    if added:
        eventlog.info("protection", f"Whitelist + {' / '.join(added)}")
    return RedirectResponse("/protected", status_code=303)


@router.post("/protected/remove")
def protected_remove(title: str = Form(""), jellyfin_id: str = Form("")):
    with PROTECTED_LOCK:
        p = get_protected()
        removed = []
        if title in p.get("titles", []):
            p["titles"].remove(title)
            removed.append(f"titre={title}")
        if jellyfin_id in p.get("jellyfin_ids", []):
            p["jellyfin_ids"].remove(jellyfin_id)
            removed.append(f"id={jellyfin_id}")
        save_protected(p)
    if removed:
        eventlog.info("protection", f"Whitelist − {' / '.join(removed)}")
    return RedirectResponse("/protected", status_code=303)


@router.post("/protected/remove_favorite")
def protected_remove_favorite(jellyfin_id: str = Form(...), user_ids: str = Form(...)):
    """Retire le favori Jellyfin (un ou plusieurs comptes) pour débloquer la suppression."""
    jf = get_jellyfin()
    removed, errors = [], []
    for uid in [u for u in user_ids.split(",") if u]:
        try:
            jf.remove_favorite(uid, jellyfin_id)
            removed.append(uid)
        except Exception as e:
            errors.append(str(e))
            logger.warning("[Protected] remove_favorite KO (user=%s, item=%s) : %s", uid, jellyfin_id, e)
    if removed:
        eventlog.info("protection", f"Favori Jellyfin retiré ({len(removed)} compte(s))", jellyfin_id=jellyfin_id)
    if errors:
        eventlog.warning("protection", f"Échec retrait favori : {'; '.join(errors)}", jellyfin_id=jellyfin_id)
    return RedirectResponse("/protected", status_code=303)


# ── API JSON ──────────────────────────────────────────────────────────────────

@router.get("/api/status")
def api_status():
    """Ping tous les services et retourne leur état."""
    def ping(fn):
        try:
            return fn().ping()
        except Exception:
            return False

    return {
        "radarr": ping(get_radarr),
        "sonarr": ping(get_sonarr),
        "transmission": ping(get_transmission),
        "jellyfin": ping(get_jellyfin),
    }


@router.get("/api/config/service-links")
def api_service_links():
    """Retourne les URLs des services pour les liens de la sidebar."""
    cfg = get_config()
    trans = cfg.get("transmission", {})
    trans_host = (trans.get("host") or "").strip()
    trans_port = trans.get("port", 9091)
    return {
        "radarr":       cfg.get("radarr", {}).get("url", "").rstrip("/") or None,
        "sonarr":       cfg.get("sonarr", {}).get("url", "").rstrip("/") or None,
        "transmission": f"http://{trans_host}:{trans_port}/" if trans_host else None,
        "jellyfin":     cfg.get("jellyfin", {}).get("url", "").rstrip("/") or None,
    }


@router.post("/api/queue/{item_id}/cancel")
def cancel_queue(item_id: int, db: Session = Depends(get_db)):
    item = db.query(DeletionQueue).filter(DeletionQueue.id == item_id, DeletionQueue.status == "pending").first()
    if not item:
        return JSONResponse({"error": "Item introuvable"}, status_code=404)
    item.status = "cancelled"
    db.commit()
    eventlog.info("queue", f"Queue annulée : {item.item_title}")
    return {"status": "ok", "cancelled": item.item_title}


@router.get("/api/set-mode/{mode}")
def set_mode(mode: str):
    if mode not in ("manual", "auto"):
        return JSONResponse({"error": "mode invalide"}, status_code=400)
    cfg = get_config()
    previous = cfg.get("rules", {}).get("mode", "manual")
    cfg.setdefault("rules", {})["mode"] = mode
    save_config(cfg)
    if previous != mode:
        eventlog.info("config", f"Mode changé : {previous} → {mode}")
    return RedirectResponse("/settings", status_code=303)


@router.post("/api/queue/process-now")
def process_now(db: Session = Depends(get_db)):
    process_queue(db)
    return {"status": "ok"}


@router.post("/api/scan/import")
def scan_import(db: Session = Depends(get_db)):
    """Import des données Jellyfin sans suppression."""
    result = sync_watch_data(db)
    return {"status": "ok", **result}


# ── Page Regardés (mode manuel) ───────────────────────────────────────────────

@router.get("/watched", response_class=HTMLResponse)
def watched_page(
    request: Request,
    media_type: str = "",
    ready_filter: str = "",
    user_id: str = "",
    db: Session = Depends(get_db),
):
    from core.rules import get_item_readiness

    rules = get_rules()
    cfg   = get_config()
    jf    = get_jellyfin()

    jellyfin_url     = cfg["jellyfin"]["url"].rstrip("/")
    jellyfin_api_key = cfg["jellyfin"]["api_key"]
    threshold        = rules.get("watch_percentage_threshold", 85)

    users            = jf.get_users()
    default_uid      = rules.get("primary_user") or (users[0]["Id"] if users else "")
    primary_uid      = user_id if user_id and any(u["Id"] == user_id for u in users) else default_uid
    required_uids    = [u for u in (rules.get("required_users") or []) if u]

    primary_name     = next((u["Name"] for u in users if u["Id"] == primary_uid), "?")
    required_details = {u["Id"]: u["Name"] for u in users if u["Id"] in required_uids}

    # Données de visionnage des utilisateurs requis depuis la DB (mis à jour par sync)
    req_watched: dict = {}
    for uid in required_uids:
        req_watched[uid] = {
            e.jellyfin_item_id
            for e in db.query(WatchEvent).filter(
                WatchEvent.jellyfin_user_id == uid,
                WatchEvent.percentage >= threshold,
            ).all()
        }

    # Items regardés par l'utilisateur principal (données fraîches depuis Jellyfin)
    raw_items = jf.get_watched_with_details(primary_uid, media_type or None, limit=200) if primary_uid else []

    items = []
    for it in raw_items:
        ud       = it.get("UserData", {})
        item_id  = it["Id"]
        series_id = it.get("SeriesId", "")
        image_id  = series_id if (it.get("Type") == "Episode" and series_id) else item_id

        # Statut par utilisateur requis
        req_statuses = [
            {
                "id":      uid,
                "name":    required_details.get(uid, uid[:6]),
                "initial": required_details.get(uid, "?")[0].upper(),
                "watched": item_id in req_watched.get(uid, set()),
            }
            for uid in required_uids
        ]
        all_req_watched = all(s["watched"] for s in req_statuses) if req_statuses else True
        ready = all_req_watched and not ud.get("IsFavorite", False)

        items.append({
            "id":            item_id,
            "title":         it.get("Name", "?"),
            "type":          it.get("Type", "?"),
            "series_title":  it.get("SeriesName", ""),
            "season":        it.get("ParentIndexNumber"),
            "episode":       it.get("IndexNumber"),
            "percentage":    round(ud.get("PlayedPercentage") or 100.0, 0),
            "is_favorite":   ud.get("IsFavorite", False),
            "path":          it.get("Path", ""),
            "image_url":     f"{jellyfin_url}/Items/{image_id}/Images/Primary?fillWidth=220&quality=80&api_key={jellyfin_api_key}",
            "req_statuses":  req_statuses,
            "ready":         ready,
        })

    # Filtres
    if ready_filter == "ready":
        items = [i for i in items if i["ready"]]
    elif ready_filter == "waiting":
        items = [i for i in items if not i["ready"] and not i["is_favorite"]]
    elif ready_filter == "fav":
        items = [i for i in items if i["is_favorite"]]

    ready_count   = sum(1 for i in items if i["ready"])
    waiting_count = sum(1 for i in items if not i["ready"] and not i["is_favorite"])

    return templates.TemplateResponse(
        request=request, name="watched.html",
        context={
            "users":            users,
            "primary_uid":      primary_uid,
            "primary_name":     primary_name,
            "required_uids":    required_uids,
            "items":            items,
            "media_type":       media_type,
            "ready_filter":     ready_filter,
            "ready_count":      ready_count,
            "waiting_count":    waiting_count,
            "mode":             get_mode(),
            "selected_user_id": primary_uid,
        },
    )


@router.get("/api/search/jellyfin")
def search_jellyfin(q: str = "", request: Request = None):
    """Recherche Jellyfin par titre — utilisé pour l'autocomplete de la protection."""
    if len(q) < 2:
        return JSONResponse([])
    try:
        jf  = get_jellyfin()
        cfg = get_config()
        users = jf.get_users()
        if not users:
            return JSONResponse([])
        admin_id        = users[0]["Id"]
        jellyfin_url    = cfg["jellyfin"]["url"].rstrip("/")
        jellyfin_api_key = cfg["jellyfin"]["api_key"]
        protected_cfg   = get_protected()
        protected_ids   = set(protected_cfg.get("jellyfin_ids", []))
        protected_titles = {t.lower() for t in protected_cfg.get("titles", [])}

        items = jf.search_items(admin_id, q, limit=20)
        return JSONResponse([
            {
                "id":           it["Id"],
                "title":        it.get("Name", "?"),
                "type":         it.get("Type", "Movie"),
                "image_url":    f"{jellyfin_url}/Items/{it['Id']}/Images/Primary?fillWidth=160&quality=80&api_key={jellyfin_api_key}",
                "is_protected": it["Id"] in protected_ids or it.get("Name", "").lower() in protected_titles,
            }
            for it in items
        ])
    except Exception as e:
        logger.error("search_jellyfin error: %s", e)
        return JSONResponse([])


@router.post("/api/scan/copies")
def api_scan_copies(
    jellyfin_item_id: str = Form(...),
    item_type: str = Form(...),
    item_title: str = Form(...),
    series_title: str = Form(""),
):
    """Scan non-destructif : trouve toutes les copies dans les chemins additionnels."""
    import os
    from core.fileops import scan_copies_smart, _file_hash
    scan_paths = get_scan_paths(item_type)
    if not scan_paths:
        return JSONResponse({"copies": [], "total_copies": 0, "total_size_human": "0 Ko",
                             "skipped": True, "has_inode_match": False,
                             "_debug": "scan_paths vide — configurez la racine bibliothèque ou les chemins additionnels"})
    file_path = ""
    raw_jf_path = ""
    jf_error  = ""
    it: dict = {}
    try:
        jf    = get_jellyfin()
        admin = (jf.get_users() or [{}])[0].get("Id")
        it    = jf.get_item(jellyfin_item_id, user_id=admin)
        raw_jf_path = it.get("Path", "")
        file_path   = resolve_real_path(raw_jf_path, item_type)
    except Exception as e:
        jf_error = str(e)

    label  = series_title or item_title
    result = scan_copies_smart(label, file_path, scan_paths, allow_name_fallback=True)

    # ── Liens vers les services ────────────────────────────────────────────────
    cfg_s = get_config()
    service_links: dict = {}
    service_link_errors: dict = {}
    provider_ids = it.get("ProviderIds", {})

    # Jellyfin — lien direct vers la fiche (toujours disponible si configuré)
    jf_base = cfg_s.get("jellyfin", {}).get("url", "").rstrip("/")
    if jf_base and jellyfin_item_id:
        service_links["jellyfin"] = f"{jf_base}/web/index.html#!/details?id={jellyfin_item_id}"

    # Radarr — fallback accueil, puis essaye la page exacte du film
    radarr_base = cfg_s.get("radarr", {}).get("url", "").rstrip("/")
    if radarr_base:
        service_links["radarr"] = radarr_base + "/"
        if item_type == "Movie":
            try:
                radarr = get_radarr()
                movie = None
                if provider_ids.get("Tmdb"):
                    try:
                        movie = radarr.find_by_tmdb_id(int(provider_ids["Tmdb"]))
                    except (TypeError, ValueError):
                        movie = None
                if not movie and provider_ids.get("Imdb"):
                    movie = radarr.find_by_imdb_id(provider_ids["Imdb"])
                if not movie:
                    movie = radarr.find_by_title(item_title)
                if movie:
                    tmdb_id = movie.get("tmdbId") or movie.get("id")
                    service_links["radarr"] = f"{radarr_base}/movie/{tmdb_id}"
            except Exception as e:
                service_link_errors["radarr"] = str(e)

    # Sonarr — fallback accueil, puis essaye la page exacte de la série
    sonarr_base = cfg_s.get("sonarr", {}).get("url", "").rstrip("/")
    if sonarr_base:
        service_links["sonarr"] = sonarr_base + "/"
        if item_type in ("Episode", "Series"):
            try:
                sonarr = get_sonarr()
                series_obj = sonarr.find_by_title(series_title or item_title)
                if series_obj:
                    slug = series_obj.get("titleSlug") or str(series_obj.get("id", ""))
                    service_links["sonarr"] = f"{sonarr_base}/series/{slug}"
            except Exception as e:
                service_link_errors["sonarr"] = str(e)

    # Transmission — TOUS les torrents correspondants (multi-tracker)
    debug_trans_comments: list = []
    try:
        from services.transmission import get_tracker_info as _get_tracker_info

        tr = get_transmission()
        torrents = tr.find_all_by_path_or_name(file_path, series_title or item_title)
        if torrents:
            torrents_info = []
            for t in torrents:
                raw_comment = (t.get("comment") or "").strip()
                if raw_comment:
                    debug_entry = raw_comment[:100]
                else:
                    first_announce = next(
                        ((tr_obj.get("announce") or "") for tr_obj in (t.get("trackers") or []) if tr_obj.get("announce")),
                        ""
                    )
                    debug_entry = f"[tracker] {first_announce[:80]}" if first_announce else "(vide)"
                debug_trans_comments.append(debug_entry)
                tname, turl = _get_tracker_info(t)
                torrents_info.append({
                    "name":         t.get("name", ""),
                    "tracker_name": tname,
                    "tracker_url":  turl,
                })
            service_links["transmission_torrents"] = torrents_info
    except Exception as e:
        service_link_errors["transmission"] = str(e)

    result["service_links"] = service_links

    # ── Debug ──────────────────────────────────────────────────────────────────
    resolved = file_path != raw_jf_path and bool(file_path)
    result["_debug"] = {
        "jellyfin_path": raw_jf_path or "(vide)",
        "resolved_path": file_path or "(vide)",
        "resolved":      resolved,
        "file_exists":   os.path.exists(file_path) if file_path else False,
        "hash_computed": bool(result.get("source_hash")),
        "hash_prefix":   result.get("source_hash", "")[:12] or "(aucun)",
        "scan_paths":    scan_paths,
        "jf_error":      jf_error or None,
        "service_links":        {k: (v if isinstance(v, str) else f"[{len(v)} torrents, {sum(1 for t in v if t.get('tracker_url'))} avec lien tracker]") for k, v in service_links.items()},
        "link_errors":          service_link_errors or None,
        "transmission_comments": debug_trans_comments or None,
    }
    return JSONResponse(result)


@router.post("/api/delete/manual")
def manual_delete(
    jellyfin_item_id: str = Form(...),
    item_type: str = Form(...),
    item_title: str = Form(...),
    series_title: str = Form(""),
    source_hash: str = Form(""),
    selected_name_paths: str = Form(""),
    db: Session = Depends(get_db),
):
    # Chemins "nom" (non vérifiés par contenu) cochés à la main dans la modal —
    # JSON encodé côté front, jamais utilisés pour les suppressions automatiques.
    try:
        extra_delete_paths = json.loads(selected_name_paths) if selected_name_paths else []
        if not isinstance(extra_delete_paths, list):
            extra_delete_paths = []
    except Exception:
        extra_delete_paths = []
    jf = get_jellyfin()
    details: dict = {}
    provider_ids: dict = {}
    try:
        admin_uid = (jf.get_users() or [{}])[0].get("Id")
        details = jf.get_item(jellyfin_item_id, user_id=admin_uid) or {}
        provider_ids = details.get("ProviderIds", {}) or {}
    except Exception as e:
        logger.warning(f"[Manual Delete] Détails Jellyfin indisponibles : {e}")

    item = {
        "jellyfin_id": jellyfin_item_id,
        "type": item_type,
        "title": item_title,
        "series_title": series_title or None,
        "tmdb_id": provider_ids.get("Tmdb"),
        "imdb_id": provider_ids.get("Imdb"),
        "tvdb_id": provider_ids.get("Tvdb"),
        "file_path": resolve_real_path(details.get("Path", ""), item_type),
        "season": details.get("ParentIndexNumber"),
        "episode": details.get("IndexNumber"),
    }

    if item_type == "Movie":
        result = delete_movie(db, item, triggered_by="manual", source_hash=source_hash,
                               extra_delete_paths=extra_delete_paths)
    else:
        if item_type == "Series":
            # Suppression série complète (ex: depuis Mon Catalogue)
            item["series_title"] = item_title
            item["_force_delete_mode"] = "series"
        result = delete_episode(db, item, triggered_by="manual", source_hash=source_hash,
                                 extra_delete_paths=extra_delete_paths)

    return JSONResponse({
        "success":            result["success"],
        "services":           result["services"],
        "errors":             result["errors"],
        "blocked_by_favorite": result.get("blocked_by_favorite", False),
        "cleanup":            result.get("cleanup"),
    })


