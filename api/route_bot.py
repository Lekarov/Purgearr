"""API JSON pour le bot Telegram DoktorTV (@DoktorTV_Bot).

Le bot ne supprime rien lui-même : il lit ces routes puis passe par les mêmes
routes que l'interface web (/api/scan/copies puis /api/delete/manual), donc par
le même moteur de recherche exacte (core/locator.py).
"""
import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

import requests
from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response

from config import get_config, get_protected, resolve_real_path
from core.fileops import format_size
from services.factory import get_jellyfin

logger = logging.getLogger("purgearr.bot")
router = APIRouter(prefix="/api/bot", tags=["bot"])

CACHE_TTL = 600
NEVER_WATCHED_MIN_DAYS = 60
_cache: Dict = {"at": 0.0, "items": []}
_lock = threading.Lock()


def _size_of(path: str) -> int:
    if not path or not os.path.exists(path):
        return 0
    if os.path.isfile(path):
        return os.path.getsize(path)
    total, seen = 0, set()
    for root, _d, files in os.walk(path):
        for f in files:
            fp = os.path.join(root, f)
            try:
                st = os.lstat(fp)
            except OSError:
                continue
            if os.path.islink(fp) or (st.st_dev, st.st_ino) in seen:
                continue
            seen.add((st.st_dev, st.st_ino))
            total += st.st_size
    return total


def _days_since(iso: Optional[str]) -> Optional[int]:
    """Dates Jellyfin : « 2025-03-01T12:34:56.1234567Z » (UTC)."""
    if not iso:
        return None
    try:
        d = datetime.strptime(iso[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return max(0, (datetime.now(timezone.utc) - d).days)


def _build() -> List[Dict]:
    jf = get_jellyfin()
    users = jf.get_users()
    if not users:
        return []
    admin = users[0]["Id"]
    prot = get_protected()
    prot_ids = set(prot.get("jellyfin_ids", []))
    prot_titles = {t.lower() for t in prot.get("titles", [])}

    base = jf._get(f"/Users/{admin}/Items", params={
        "IncludeItemTypes": "Movie,Series", "Recursive": True,
        "Fields": "Path,DateCreated,ProductionYear,CommunityRating,Genres,RecursiveItemCount",
    }).get("Items", [])

    # Visionnage par utilisateur (Played pour une série = tous les épisodes vus)
    watched: Dict[str, List[Dict]] = {}
    started: Dict[str, List[str]] = {}
    favorite: set = set()
    episodes = {it["Id"]: it.get("RecursiveItemCount") or 0 for it in base if it.get("Type") == "Series"}
    for u in users:
        items = jf._get(f"/Users/{u['Id']}/Items", params={
            "IncludeItemTypes": "Movie,Series", "Recursive": True, "Fields": "UserData",
            "EnableUserData": True,
        }).get("Items", [])
        for it in items:
            ud = it.get("UserData") or {}
            if ud.get("IsFavorite"):
                favorite.add(it["Id"])
            total = episodes.get(it["Id"], 0)
            if total and ud.get("UnplayedItemCount") is not None:
                # série : vue si ≥ 90 % des épisodes vus (Jellyfin exige 100 %)
                ratio = 1 - ud["UnplayedItemCount"] / total
                if ud.get("Played") or ratio >= 0.9:
                    name = u["Name"] if ratio >= 0.999 or ud.get("Played") else f"{u['Name']} ({ratio:.0%})"
                    watched.setdefault(it["Id"], []).append({"user": name, "last": ud.get("LastPlayedDate")})
                elif ratio > 0:
                    started.setdefault(it["Id"], []).append(f"{u['Name']} ({ratio:.0%})")
            elif ud.get("Played"):
                watched.setdefault(it["Id"], []).append({"user": u["Name"], "last": ud.get("LastPlayedDate")})
            elif ud.get("PlayedPercentage") or ud.get("LastPlayedDate"):
                started.setdefault(it["Id"], []).append(u["Name"])

    out = []
    for it in base:
        ty = it.get("Type")
        path = resolve_real_path(it.get("Path", ""), ty)
        if not path or not os.path.exists(path):
            continue
        w = watched.get(it["Id"], [])
        lasts = [x["last"] for x in w if x.get("last")]
        out.append({
            "id": it["Id"], "type": ty, "title": it.get("Name", "?"),
            "year": it.get("ProductionYear"),
            "rating": it.get("CommunityRating"),
            "size_bytes": _size_of(path), "path": path,
            "added_days": _days_since(it.get("DateCreated")),
            "watched_by": [x["user"] for x in w],
            "started_by": started.get(it["Id"], []),
            "last_played_days": min((_days_since(x) for x in lasts if _days_since(x) is not None), default=None),
            "protected": it["Id"] in favorite or it["Id"] in prot_ids or it.get("Name", "").lower() in prot_titles,
            "favorite": it["Id"] in favorite,
        })
    return out


def catalogue(force: bool = False) -> List[Dict]:
    with _lock:
        if force or time.time() - _cache["at"] > CACHE_TTL or not _cache["items"]:
            t0 = time.time()
            _cache["items"] = _build()
            _cache["at"] = time.time()
            logger.info("[Bot] catalogue %d éléments en %.1fs", len(_cache["items"]), time.time() - t0)
        return _cache["items"]


def forget(item_id: str):
    with _lock:
        _cache["items"] = [i for i in _cache["items"] if i["id"] != item_id]


def _public(i: Dict) -> Dict:
    return {**i, "size_human": format_size(i["size_bytes"])}


@router.get("/candidates")
def candidates(cat: str = "vus", kind: str = "all", refresh: int = 0):
    """cat : vus (vus par quelqu'un), jamais (personne, ajouté il y a > 60 j),
    lourds (tout, du plus gros au plus petit). Les favoris/protégés sont exclus."""
    items = [i for i in catalogue(force=bool(refresh)) if not i["protected"]]
    if kind == "movie":
        items = [i for i in items if i["type"] == "Movie"]
    elif kind == "series":
        items = [i for i in items if i["type"] == "Series"]
    if cat == "vus":
        # séries : rarement vues à 100 % → on inclut les séries entamées (avec le %)
        items = [i for i in items if i["watched_by"] or (i["type"] == "Series" and i["started_by"])]
    elif cat == "jamais":
        items = [i for i in items if not i["watched_by"] and not i["started_by"]
                 and (i["added_days"] or 0) >= NEVER_WATCHED_MIN_DAYS]
    items = sorted(items, key=lambda i: i["size_bytes"], reverse=True)
    total = sum(i["size_bytes"] for i in items)
    return JSONResponse({"count": len(items), "total_human": format_size(total),
                         "items": [_public(i) for i in items]})


@router.get("/search")
def search(q: str = ""):
    q = q.strip().lower()
    if len(q) < 2:
        return JSONResponse({"items": []})
    items = [i for i in catalogue() if q in i["title"].lower()]
    if not items:
        # titre original / autre langue : on demande à Jellyfin
        jf = get_jellyfin()
        admin = jf.get_users()[0]["Id"]
        ids = {it["Id"] for it in jf.search_items(admin, q, limit=20)}
        items = [i for i in catalogue() if i["id"] in ids]
    items = sorted(items, key=lambda i: i["size_bytes"], reverse=True)[:15]
    return JSONResponse({"items": [_public(i) for i in items]})


@router.get("/item/{item_id}")
def item(item_id: str):
    """Fiche complète : métadonnées Jellyfin + ce qu'il y a réellement sur le NAS."""
    jf = get_jellyfin()
    admin = jf.get_users()[0]["Id"]
    d = jf._get(f"/Users/{admin}/Items/{item_id}", params={"Fields": "Path,Overview,Genres,MediaSources,MediaStreams,DateCreated,ChildCount,RecursiveItemCount"})
    ty = d.get("Type")
    path = resolve_real_path(d.get("Path", ""), ty)
    known = next((i for i in catalogue() if i["id"] == item_id), None)
    info = {
        "id": item_id, "type": ty, "title": d.get("Name"), "year": d.get("ProductionYear"),
        "overview": (d.get("Overview") or "").strip(), "genres": d.get("Genres", [])[:3],
        "rating": d.get("CommunityRating"), "runtime_min": round((d.get("RunTimeTicks") or 0) / 600_000_000) or None,
        "path": path, "exists": bool(path) and os.path.exists(path),
        "size_bytes": _size_of(path), "added_days": _days_since(d.get("DateCreated")),
        "seasons": d.get("ChildCount") if ty == "Series" else None,
        "episodes": d.get("RecursiveItemCount") if ty == "Series" else None,
        "watched_by": (known or {}).get("watched_by", []),
        "started_by": (known or {}).get("started_by", []),
        "last_played_days": (known or {}).get("last_played_days"),
        "protected": (known or {}).get("protected", False),
        "favorite": (known or {}).get("favorite", False),
    }
    info["size_human"] = format_size(info["size_bytes"])
    if path and os.path.isdir(path):
        info["files"] = sum(1 for _r, _d, fs in os.walk(path) for f in fs
                            if os.path.splitext(f)[1].lower() in {".mkv", ".mp4", ".avi", ".m4v", ".ts"})
    streams = []
    for ms in (d.get("MediaSources") or [])[:1]:
        streams = ms.get("MediaStreams") or []
        info["container"] = ms.get("Container")
    v = next((s for s in streams if s.get("Type") == "Video"), None)
    if v:
        h = v.get("Height") or 0
        info["video"] = ("2160p" if h > 1100 else "1080p" if h > 700 else "720p" if h > 500 else f"{h}p") + \
                        f" {(v.get('Codec') or '').upper()}" + (" HDR" if (v.get("VideoRange") or "") == "HDR" else "")
    info["audio"] = sorted({(s.get("Language") or "?").upper() for s in streams if s.get("Type") == "Audio"})
    info["subs"] = sorted({(s.get("Language") or "?").upper() for s in streams if s.get("Type") == "Subtitle"})
    return JSONResponse(info)


@router.get("/poster/{item_id}")
def poster(item_id: str):
    """Affiche en octets : Telegram ne peut pas joindre Jellyfin sur le réseau local."""
    cfg = get_config()["jellyfin"]
    try:
        r = requests.get(f"{cfg['url'].rstrip('/')}/Items/{item_id}/Images/Primary",
                         params={"fillWidth": 500, "quality": 85}, timeout=15)
        if r.status_code == 200 and r.content:
            return Response(r.content, media_type=r.headers.get("Content-Type", "image/jpeg"))
    except Exception as e:
        logger.warning("[Bot] affiche %s : %s", item_id, e)
    return Response(status_code=404)


@router.post("/forget/{item_id}")
def forget_item(item_id: str):
    """Retire un élément supprimé du cache des suggestions."""
    forget(item_id)
    return {"ok": True}
