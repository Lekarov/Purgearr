from datetime import datetime

from fastapi import APIRouter, Form
from fastapi.responses import JSONResponse

from config import get_scan_paths
from core.cleanup_store import INDEX_LOCK, load_index, save_index
from core.fileops import format_size, run_cleanup_from_scan, scan_copies_smart

router = APIRouter(tags=["cleanup"])


def _entry_signatures(entry: dict) -> list:
    """Une entrée série/saison a une empreinte par épisode (source_hashes) — repli
    sur l'unique source_hash pour les entrées créées avant son introduction."""
    hashes = entry.get("source_hashes") or ([entry["source_hash"]] if entry.get("source_hash") else [])
    return [{"inode": None, "size": None, "hash": h} for h in hashes]


@router.post("/api/cleanup/rescan")
def api_cleanup_rescan():
    """Scanne tous les items de l'index pour trouver les copies résiduelles."""
    results = []
    now = datetime.utcnow().isoformat()

    with INDEX_LOCK:
        entries = load_index()
        for entry in entries:
            if not entry.get("source_hash"):
                continue
            scan_paths = get_scan_paths(entry.get("item_type", "Movie"))
            scan = scan_copies_smart(
                entry["item_title"], "", scan_paths,
                known_signatures=_entry_signatures(entry),
            )
            entry["remains_checked_at"] = now
            entry["remains_found"] = scan["total_copies"]
            if scan["total_copies"] > 0:
                results.append({
                    "id":           entry["id"],
                    "item_title":   entry["item_title"],
                    "series_title": entry.get("series_title"),
                    "item_type":    entry.get("item_type", "Movie"),
                    "deleted_at":   entry["deleted_at"],
                    "torrent_name": entry.get("torrent_name"),
                    "source_hash":  entry["source_hash"][:12],
                    "copies":       scan["copies"],
                    "total_copies": scan["total_copies"],
                    "total_size":   scan["total_size_human"],
                })

        save_index(entries)
    return JSONResponse({"found": len(results), "items": results})


@router.post("/api/cleanup/delete-remains")
def api_cleanup_delete_remains(entry_id: str = Form(...)):
    """Supprime les restes d'un item spécifique."""
    with INDEX_LOCK:
        entries = load_index()
        entry = next((e for e in entries if e["id"] == entry_id), None)
        if not entry or not entry.get("source_hash"):
            return JSONResponse({"error": "Entrée introuvable"}, status_code=404)

        scan_paths = get_scan_paths(entry.get("item_type", "Movie"))
        scan = scan_copies_smart(
            entry["item_title"], "", scan_paths,
            known_signatures=_entry_signatures(entry),
        )
        cleanup = run_cleanup_from_scan(scan, roots=scan_paths)
        entry["remains_found"] = 0
        entry["remains_checked_at"] = datetime.utcnow().isoformat()
        save_index(entries)
    return JSONResponse(cleanup)


@router.post("/api/cleanup/purge-all")
def api_cleanup_purge_all():
    """Scanne et supprime TOUS les restes en une seule passe."""
    total_deleted = 0
    total_size = 0
    now = datetime.utcnow().isoformat()

    with INDEX_LOCK:
        entries = load_index()
        for entry in entries:
            if not entry.get("source_hash"):
                continue
            scan_paths = get_scan_paths(entry.get("item_type", "Movie"))
            scan = scan_copies_smart(
                entry["item_title"], "", scan_paths,
                known_signatures=_entry_signatures(entry),
            )
            if scan["total_copies"] > 0:
                cleanup = run_cleanup_from_scan(scan, roots=scan_paths)
                total_deleted += cleanup.get("copies_deleted", 0)
                total_size += cleanup.get("size_bytes", 0)
            entry["remains_found"] = 0
            entry["remains_checked_at"] = now

        save_index(entries)
    return JSONResponse({
        "success": True,
        "copies_deleted": total_deleted,
        "size_human": format_size(total_size),
    })
