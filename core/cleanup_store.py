import json
import logging
import os
import tempfile
import threading
import uuid
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("purgearr.cleanup_store")

DATA_DIR  = Path(__file__).parent.parent / "data"
INDEX_PATH = DATA_DIR / "cleanup_index.json"

# Sérialise les cycles lecture-modification-écriture de cleanup_index.json
# pour éviter qu'une écriture concurrente en écrase une autre.
INDEX_LOCK = threading.Lock()


def load_index() -> list:
    try:
        with open(INDEX_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return []
    except json.JSONDecodeError as e:
        logger.error(f"cleanup_index.json invalide ({e}) — index remis à zéro")
        return []


def save_index(entries: list):
    """Écrit dans un fichier temporaire puis rename atomique — évite la corruption si crash."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=INDEX_PATH.name + ".", suffix=".tmp", dir=str(DATA_DIR))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, INDEX_PATH)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def add_entry(
    item_title: str,
    item_type: str,
    source_hash: str,
    file_path: str = "",
    series_title: str = None,
    jellyfin_item_id: str = "",
    file_size_bytes: int = 0,
    torrent_name: str = None,
    scan_paths: list = None,
    source_hashes: list = None,
):
    """source_hashes : empreinte de CHAQUE fichier vidéo (un dossier saison/série en a
    plusieurs) — nécessaire pour que le rescan des traces retrouve toutes les copies,
    pas seulement celle du premier épisode. source_hash reste rempli (rétrocompat/legacy)."""
    if not source_hash:
        return
    with INDEX_LOCK:
        entries = load_index()
        entries.append({
            "id":                 str(uuid.uuid4())[:8],
            "item_title":         item_title,
            "series_title":       series_title,
            "item_type":          item_type,
            "jellyfin_item_id":   jellyfin_item_id,
            "source_hash":        source_hash,
            "source_hashes":      source_hashes or [source_hash],
            "file_path":          file_path,
            "file_size_bytes":    file_size_bytes,
            "torrent_name":       torrent_name,
            "scan_paths":         scan_paths or [],
            "deleted_at":         datetime.utcnow().isoformat(),
            "remains_checked_at": None,
            "remains_found":      None,
        })
        save_index(entries)
