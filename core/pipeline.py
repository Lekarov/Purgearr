import json
import logging
import os
import shutil
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import desc
from sqlalchemy.orm import Session

from config import get_rules, get_scan_paths
from core import eventlog
from core.fileops import _calc_size, collect_signatures, delete_selected_paths, format_size, run_cleanup
from database import DeletionHistory
from services.factory import get_jellyfin, get_radarr, get_sonarr, get_transmission


# Rétrocompatibilité : ces fonctions sont maintenant dans core.queue
from core.queue import process_queue, handle_watch_event  # noqa: F401

logger = logging.getLogger("purgearr.pipeline")


# ── Helpers ───────────────────────────────────────────────────────────────────

def merge_history_details(old: Optional[Dict], new: Optional[Dict]) -> Dict:
    """Fusionne les détails de deux tentatives de suppression sur le même item.
    Les tailles utilisent le max (jamais la somme) pour ne pas recompter le même
    fichier/les mêmes copies vues à plusieurs tentatives ; torrents sont unionnés
    par nom."""
    old = old or {}
    new = new or {}
    merged = {**old, **new}
    for k in ("file_size_bytes", "copies_size_bytes", "total_freed_bytes", "copies_deleted"):
        merged[k] = max(old.get(k) or 0, new.get(k) or 0)
    old_torrents = {t.get("name"): t for t in (old.get("torrents") or [])}
    for t in (new.get("torrents") or []):
        old_torrents.setdefault(t.get("name"), t)
    merged["torrents"] = list(old_torrents.values())
    merged["file_path"] = new.get("file_path") or old.get("file_path")
    merged["file_size_human"] = format_size(merged["file_size_bytes"])
    merged["copies_size_human"] = format_size(merged["copies_size_bytes"])
    merged["total_freed_human"] = format_size(merged["total_freed_bytes"])
    return merged


def _merge_cleanup_results(a: Optional[Dict], b: Optional[Dict]) -> Dict:
    """Combine le résultat du nettoyage automatique (hash/inode) avec celui des
    chemins "nom" cochés manuellement par l'utilisateur (delete_selected_paths)."""
    a = a or {}
    b = b or {}
    if a.get("skipped", True) and b.get("skipped", True):
        return {"skipped": True, "copies_found": 0}
    size_bytes = (a.get("size_bytes") or 0) + (b.get("size_bytes") or 0)
    return {
        "skipped":        False,
        "copies_found":   (a.get("copies_found") or 0) + (b.get("copies_found") or 0),
        "copies_deleted": (a.get("copies_deleted") or 0) + (b.get("copies_deleted") or 0),
        "copies_failed":  (a.get("copies_failed") or 0) + (b.get("copies_failed") or 0),
        "total_files":    (a.get("total_files") or 0) + (b.get("total_files") or 0),
        "size_bytes":     size_bytes,
        "size_human":     format_size(size_bytes),
        "details":        (a.get("details") or []) + (b.get("details") or []),
    }


def _save_history(db: Session, item: Dict, services: List[str], triggered_by: str,
                  error: Optional[str] = None, details: Optional[Dict] = None):
    """Upsert : une nouvelle tentative sur un item déjà présent dans l'historique
    met à jour la ligne existante (fusion) plutôt que d'en créer une nouvelle —
    évite les doublons visuels sur /history quand une suppression est retentée
    plusieurs fois (ex: échec Sonarr puis retry en suppression directe)."""
    jf_id = item.get("jellyfin_id")
    existing = (
        db.query(DeletionHistory)
        .filter(DeletionHistory.jellyfin_item_id == jf_id)
        .order_by(desc(DeletionHistory.deleted_at))
        .first()
        if jf_id else None
    )
    if existing:
        try:
            old_services = set(json.loads(existing.deleted_from or "[]"))
        except Exception:
            old_services = set()
        try:
            old_details = json.loads(existing.details_json or "{}")
        except Exception:
            old_details = {}
        existing.deleted_at = datetime.utcnow()
        existing.deleted_from = json.dumps(sorted(old_services | set(services)))
        existing.triggered_by = triggered_by
        existing.error = error
        existing.details_json = json.dumps(merge_history_details(old_details, details))
        db.commit()
        return
    db.add(DeletionHistory(
        jellyfin_item_id=jf_id,
        item_type=item.get("type"),
        item_title=item.get("title"),
        series_title=item.get("series_title"),
        deleted_at=datetime.utcnow(),
        deleted_from=json.dumps(services),
        triggered_by=triggered_by,
        error=error,
        details_json=json.dumps(details) if details else None,
    ))
    db.commit()


def dedupe_deletion_history(db: Session) -> int:
    """Nettoyage rétroactif : fusionne les lignes d'historique en double créées
    avant la mise en place de l'upsert dans _save_history (plusieurs tentatives
    de suppression sur le même item = plusieurs lignes). Retourne le nombre de
    lignes fusionnées/supprimées."""
    from collections import defaultdict
    groups: Dict[str, List[DeletionHistory]] = defaultdict(list)
    for row in db.query(DeletionHistory).filter(
        DeletionHistory.jellyfin_item_id.isnot(None),
        DeletionHistory.jellyfin_item_id != "",
    ).all():
        groups[row.jellyfin_item_id].append(row)

    removed = 0
    for rows in groups.values():
        if len(rows) < 2:
            continue
        rows.sort(key=lambda r: r.deleted_at or datetime.min)
        keep = rows[-1]
        try:
            details = json.loads(keep.details_json or "{}")
        except Exception:
            details = {}
        try:
            services = set(json.loads(keep.deleted_from or "[]"))
        except Exception:
            services = set()
        for older in rows[:-1]:
            try:
                o_details = json.loads(older.details_json or "{}")
            except Exception:
                o_details = {}
            try:
                o_services = set(json.loads(older.deleted_from or "[]"))
            except Exception:
                o_services = set()
            details = merge_history_details(o_details, details)
            services |= o_services
            db.delete(older)
            removed += 1
        keep.deleted_from = json.dumps(sorted(services))
        keep.details_json = json.dumps(details)
    if removed:
        db.commit()
    return removed


def _stop_all_torrents(file_path: str, title: str) -> List[Dict]:
    """Cherche et stoppe TOUS les torrents correspondants. Retourne [{name, tracker_name, tracker_url}]."""
    from services.transmission import get_tracker_info
    results: List[Dict] = []
    try:
        tr = get_transmission()
        torrents = tr.find_all_by_path_or_name(file_path, title)
        if not torrents:
            return results
        for torrent in torrents:
            tr.stop_and_remove(torrent["id"], delete_data=False)
            logger.info(f"[Transmission] Torrent supprimé : {torrent['name']}")
            tname, turl = get_tracker_info(torrent)
            results.append({"name": torrent["name"], "tracker_name": tname, "tracker_url": turl})
    except Exception as e:
        logger.warning(f"[Transmission] Erreur pour '{title}': {e}")
        eventlog.warning("service", f"Transmission KO pour '{title}' : {e}")
    return results


def _delete_path_direct(path: str) -> bool:
    """Supprime un fichier/dossier directement sur le disque (fallback quand Sonarr/Radarr
    ne connaît pas l'item — ex: série seedée manuellement, jamais importée dans Sonarr)."""
    if not path or not os.path.exists(path):
        return False
    if os.path.isdir(path):
        shutil.rmtree(path)
    else:
        os.remove(path)
    return True


# ── Suppression film ──────────────────────────────────────────────────────────

def delete_movie(db: Session, item: Dict, triggered_by: str, source_hash: str = "",
                  extra_delete_paths: Optional[List[str]] = None) -> Dict:
    """
    Pipeline complet de suppression d'un film.
    item = { jellyfin_id, title, tmdb_id, imdb_id, file_path }
    source_hash : empreinte pré-calculée (scan manuel) ou calculée ici avant suppression Radarr
    extra_delete_paths : chemins "nom" cochés manuellement dans la modal (non vérifiés
    par contenu) — supprimés en plus du nettoyage automatique hash/inode.
    """
    result = {"success": False, "services": [], "errors": [], "blocked_by_favorite": False, "cleanup": None}
    rules = get_rules()
    title = item.get("title", "?")
    file_path = item.get("file_path", "")

    logger.info(f"[Pipeline] Suppression film : {title}")

    # 0. Vérifier les favoris Jellyfin — item favori = intouchable
    try:
        if get_jellyfin().is_favorite_any_user(item.get("jellyfin_id", "")):
            logger.info(f"[Pipeline] Film en favori, suppression bloquée : {title}")
            result["errors"].append("Item en favori Jellyfin — suppression bloquée")
            result["blocked_by_favorite"] = True
            eventlog.warning("protection", f"Film en favori — suppression bloquée : {title}",
                             triggered_by=triggered_by, jellyfin_id=item.get("jellyfin_id"))
            return result
    except Exception as e:
        logger.warning(f"[Pipeline] Impossible de vérifier les favoris: {e}")
        eventlog.warning("service", f"Jellyfin favoris indisponibles : {e}", title=title)

    # 0.5 Empreintes AVANT suppression — pour retrouver toutes les copies (fichier
    # unique ou dossier entier) une fois Radarr aura supprimé la source
    known_signatures = collect_signatures(file_path) if file_path else []
    if not source_hash and known_signatures:
        source_hash = known_signatures[0]["hash"]
        logger.debug(f"[Pipeline] Hash source calculé avant suppression : {source_hash[:12]}…")

    # Taille du fichier source (avant que Radarr ne le supprime)
    file_size = _calc_size(file_path)[0] if file_path and os.path.exists(file_path) else 0

    # 1. Transmission — stop TOUS les torrents seedant ce fichier (multi-tracker)
    torrents_info = _stop_all_torrents(file_path, title)
    torrent_names = [t["name"] for t in torrents_info]
    if torrents_info:
        result["services"].append("transmission")
        logger.info(f"[Transmission] {len(torrents_info)} torrent(s) supprimé(s) pour : {title}")

    # 1.5 Sauvegarder dans l'index cleanup AVANT que Radarr supprime les fichiers
    try:
        from core.cleanup_store import add_entry
        add_entry(
            item_title=title, item_type="Movie", source_hash=source_hash,
            source_hashes=[s["hash"] for s in known_signatures if s.get("hash")],
            file_path=file_path, jellyfin_item_id=item.get("jellyfin_id", ""),
            file_size_bytes=file_size, torrent_name=", ".join(torrent_names) if torrent_names else None,
            scan_paths=get_scan_paths("Movie"),
        )
    except Exception as e:
        logger.warning(f"[Cleanup] Erreur sauvegarde index : {e}")

    # 2. Radarr — supprime le film, les fichiers, et bloque le re-téléchargement
    try:
        radarr = get_radarr()
        movie = None
        if item.get("tmdb_id"):
            try:
                movie = radarr.find_by_tmdb_id(int(item["tmdb_id"]))
            except (TypeError, ValueError):
                movie = None
        if not movie and item.get("imdb_id"):
            movie = radarr.find_by_imdb_id(item["imdb_id"])
        if not movie:
            movie = radarr.find_by_title(title)
        if movie:
            radarr.delete(
                movie["id"],
                delete_files=rules.get("delete_files", True),
                add_exclusion=rules.get("add_to_exclusion", True),
            )
            result["services"].append("radarr")
            result["success"] = True
            logger.info(f"[Radarr] Film supprimé : {title} (id={movie['id']})")
        else:
            logger.warning(f"[Radarr] Film introuvable : {title}")
            result["errors"].append("Radarr: film introuvable")
    except Exception as e:
        result["errors"].append(f"Radarr: {e}")
        logger.error(f"[Radarr] Erreur pour '{title}': {e}")

    # 2.5 Nettoyage des copies (signatures pré-calculées = pas de fallback titre hasardeux)
    try:
        result["cleanup"] = run_cleanup(title, file_path, get_scan_paths("Movie"), known_signatures=known_signatures)
        if extra_delete_paths:
            selected = delete_selected_paths(extra_delete_paths, roots=get_scan_paths("Movie"))
            result["cleanup"] = _merge_cleanup_results(result["cleanup"], selected)
    except Exception as e:
        logger.warning(f"[Fileops] Erreur nettoyage copies : {e}")

    # 3. Jellyfin — suppression immédiate de l'item + refresh bibliothèque
    # (le refresh seul est asynchrone côté Jellyfin : l'item peut rester visible
    # dans le catalogue tant que le scan n'a pas tourné — delete_item est immédiat)
    try:
        jf = get_jellyfin()
        if result["success"] and item.get("jellyfin_id"):
            try:
                jf.delete_item(item["jellyfin_id"])
            except Exception as e:
                logger.warning(f"[Jellyfin] delete_item KO pour '{title}': {e}")
        jf.refresh_library()
        result["services"].append("jellyfin")
    except Exception as e:
        result["errors"].append(f"Jellyfin refresh: {e}")

    # Détails pour l'historique
    from core.fileops import format_size
    cleanup_result = result.get("cleanup") or {}
    copies_size = cleanup_result.get("size_bytes", 0)
    details = {
        "file_path": file_path,
        "file_size_bytes": file_size,
        "file_size_human": format_size(file_size),
        "torrents": torrents_info,
        "copies_deleted": cleanup_result.get("copies_deleted", 0),
        "copies_size_bytes": copies_size,
        "copies_size_human": format_size(copies_size),
        "total_freed_bytes": file_size + copies_size,
        "total_freed_human": format_size(file_size + copies_size),
    }
    _save_history(db, item, result["services"], triggered_by,
                  "; ".join(result["errors"]) or None, details=details)

    # Log événementiel
    if result["success"]:
        eventlog.info("deletion", f"Film supprimé : {title}",
                      triggered_by=triggered_by,
                      services=result["services"],
                      copies_deleted=cleanup_result.get("copies_deleted", 0))
    elif result["errors"]:
        eventlog.error("deletion", f"Échec suppression film : {title}",
                       triggered_by=triggered_by, errors=result["errors"])

    return result


# ── Suppression épisode ───────────────────────────────────────────────────────

def delete_episode(db: Session, item: Dict, triggered_by: str, source_hash: str = "",
                    extra_delete_paths: Optional[List[str]] = None) -> Dict:
    """
    Pipeline de suppression d'un épisode (ou d'une série entière selon config).
    item = { jellyfin_id, title, series_title, tvdb_id, file_path, season, episode }
    extra_delete_paths : chemins "nom" cochés manuellement dans la modal (non vérifiés
    par contenu) — supprimés en plus du nettoyage automatique hash/inode.
    """
    result = {"success": False, "services": [], "errors": [], "blocked_by_favorite": False, "cleanup": None}
    rules = get_rules()
    delete_mode = item.get("_force_delete_mode") or rules.get("series", {}).get("delete_mode", "episode")
    series_title = item.get("series_title", "?")
    title = item.get("title", "?")
    file_path = item.get("file_path", "")

    logger.info(f"[Pipeline] Suppression épisode : {series_title} — {title}")

    # 0. Vérifier les favoris Jellyfin
    try:
        if get_jellyfin().is_favorite_any_user(item.get("jellyfin_id", "")):
            logger.info(f"[Pipeline] Épisode en favori, suppression bloquée : {title}")
            result["errors"].append("Item en favori Jellyfin — suppression bloquée")
            result["blocked_by_favorite"] = True
            eventlog.warning("protection", f"Épisode en favori — suppression bloquée : {series_title} — {title}",
                             triggered_by=triggered_by, jellyfin_id=item.get("jellyfin_id"))
            return result
    except Exception as e:
        logger.warning(f"[Pipeline] Impossible de vérifier les favoris: {e}")
        eventlog.warning("service", f"Jellyfin favoris indisponibles : {e}", title=title)

    # 0.5 Empreintes AVANT suppression — pour retrouver toutes les copies (épisode
    # unique ou dossier série entière) une fois Sonarr aura supprimé la source
    known_signatures = collect_signatures(file_path) if file_path else []
    if not source_hash and known_signatures:
        source_hash = known_signatures[0]["hash"]

    # Taille du fichier source (avant que Sonarr ne le supprime)
    file_size = _calc_size(file_path)[0] if file_path and os.path.exists(file_path) else 0

    # 1. Transmission — stop TOUS les torrents seedant cet épisode (multi-tracker)
    torrents_info = _stop_all_torrents(file_path, series_title)
    torrent_names = [t["name"] for t in torrents_info]
    if torrents_info:
        result["services"].append("transmission")
        logger.info(f"[Transmission] {len(torrents_info)} torrent(s) supprimé(s) pour : {series_title}")

    # 1.5 Sauvegarder dans l'index cleanup AVANT que Sonarr supprime les fichiers
    try:
        from core.cleanup_store import add_entry
        add_entry(
            item_title=title, item_type="Episode", source_hash=source_hash,
            source_hashes=[s["hash"] for s in known_signatures if s.get("hash")],
            file_path=file_path, series_title=series_title,
            jellyfin_item_id=item.get("jellyfin_id", ""),
            file_size_bytes=file_size, torrent_name=", ".join(torrent_names) if torrent_names else None,
            scan_paths=get_scan_paths("Episode"),
        )
    except Exception as e:
        logger.warning(f"[Cleanup] Erreur sauvegarde index : {e}")

    # 2. Sonarr
    try:
        sonarr = get_sonarr()
        series = None
        if item.get("tvdb_id"):
            try:
                series = sonarr.find_by_tvdb_id(int(item["tvdb_id"]))
            except (TypeError, ValueError):
                series = None
        if not series:
            series = sonarr.find_by_title(series_title)

        if not series:
            # Série absente de Sonarr (ex: seedée manuellement, jamais importée) —
            # pas une erreur en soi : on supprime directement le fichier/dossier
            # source (déjà résolu depuis Jellyfin) plutôt que d'échouer.
            logger.info(f"[Sonarr] Série introuvable, suppression directe : {series_title}")
            try:
                if rules.get("delete_files", True) and _delete_path_direct(file_path):
                    result["services"].append("filesystem")
                    result["success"] = True
                    logger.info(f"[Fileops] Suppression directe (hors Sonarr) : {file_path}")
                else:
                    result["errors"].append("Sonarr: série introuvable et fichier source introuvable")
            except Exception as e:
                result["errors"].append(f"Suppression directe: {e}")
                logger.error(f"[Fileops] Erreur suppression directe '{file_path}': {e}")
        elif delete_mode == "series":
            sonarr.delete_series(
                series["id"],
                delete_files=rules.get("delete_files", True),
                add_exclusion=rules.get("add_to_exclusion", True),
            )
            result["services"].append("sonarr")
            result["success"] = True
            logger.info(f"[Sonarr] Série entière supprimée : {series_title}")
        else:
            # Suppression épisode par épisode via le fichier
            file_path = item.get("file_path", "")
            ep_files = sonarr.get_episode_files(series["id"])
            deleted = False
            for ef in ep_files:
                if file_path and ef.get("path", "") == file_path:
                    sonarr.delete_episode_file(ef["id"])
                    deleted = True
                    break
            # Fallback : correspondance par saison/épisode si le path ne matche pas
            if not deleted and item.get("season") and item.get("episode"):
                episodes = sonarr.get_episodes(series["id"])
                for ep in episodes:
                    if ep.get("seasonNumber") == item["season"] and ep.get("episodeNumber") == item["episode"]:
                        if ep.get("episodeFileId"):
                            sonarr.delete_episode_file(ep["episodeFileId"])
                            deleted = True
                        break
            if deleted:
                result["services"].append("sonarr")
                result["success"] = True
                logger.info(f"[Sonarr] Épisode supprimé : {series_title} S{item.get('season', '?')}E{item.get('episode', '?')}")
            else:
                result["errors"].append("Sonarr: fichier épisode introuvable")
                logger.warning(f"[Sonarr] Fichier épisode introuvable pour : {title}")

    except Exception as e:
        result["errors"].append(f"Sonarr: {e}")
        logger.error(f"[Sonarr] Erreur pour '{series_title}': {e}")

    # 2.5 Nettoyage des copies (signatures pré-calculées)
    try:
        cleanup_title = series_title if delete_mode == "series" else title
        result["cleanup"] = run_cleanup(cleanup_title, file_path, get_scan_paths("Episode"), known_signatures=known_signatures)
        if extra_delete_paths:
            selected = delete_selected_paths(extra_delete_paths, roots=get_scan_paths("Episode"))
            result["cleanup"] = _merge_cleanup_results(result["cleanup"], selected)
    except Exception as e:
        logger.warning(f"[Fileops] Erreur nettoyage copies : {e}")

    # 3. Jellyfin — suppression immédiate de l'item + refresh bibliothèque
    # (le refresh seul est asynchrone côté Jellyfin : l'item peut rester visible
    # dans le catalogue tant que le scan n'a pas tourné — delete_item est immédiat)
    try:
        jf = get_jellyfin()
        if result["success"] and item.get("jellyfin_id"):
            try:
                jf.delete_item(item["jellyfin_id"])
            except Exception as e:
                logger.warning(f"[Jellyfin] delete_item KO pour '{series_title} — {title}': {e}")
        jf.refresh_library()
        result["services"].append("jellyfin")
    except Exception as e:
        result["errors"].append(f"Jellyfin refresh: {e}")

    # Détails pour l'historique
    from core.fileops import format_size
    cleanup_result = result.get("cleanup") or {}
    copies_size = cleanup_result.get("size_bytes", 0)
    details = {
        "file_path": file_path,
        "file_size_bytes": file_size,
        "file_size_human": format_size(file_size),
        "torrents": torrents_info,
        "copies_deleted": cleanup_result.get("copies_deleted", 0),
        "copies_size_bytes": copies_size,
        "copies_size_human": format_size(copies_size),
        "total_freed_bytes": file_size + copies_size,
        "total_freed_human": format_size(file_size + copies_size),
    }
    _save_history(db, item, result["services"], triggered_by,
                  "; ".join(result["errors"]) or None, details=details)

    # Log événementiel
    label = f"{series_title} — {title}"
    if result["success"]:
        eventlog.info("deletion", f"Épisode supprimé : {label}",
                      triggered_by=triggered_by,
                      services=result["services"],
                      delete_mode=delete_mode,
                      copies_deleted=cleanup_result.get("copies_deleted", 0))
    elif result["errors"]:
        eventlog.error("deletion", f"Échec suppression épisode : {label}",
                       triggered_by=triggered_by, errors=result["errors"])

    return result
