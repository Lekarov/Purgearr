import hashlib
import logging
import os
import re
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("purgearr.fileops")

METADATA_EXTENSIONS = {
    ".nfo", ".jpg", ".jpeg", ".png", ".webp", ".tbn", ".bmp", ".gif",
    ".srt", ".sub", ".idx", ".ass", ".ssa", ".sup",
    ".sfv", ".md5", ".sha256", ".txt",
}
VIDEO_EXTENSIONS = {".mkv", ".mp4", ".avi", ".mov", ".wmv", ".m4v", ".ts", ".m2ts", ".iso"}


def _file_hash(path: str, chunk: int = 65536) -> str:
    """SHA-256 des premiers 64 Ko d'un fichier."""
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            h.update(f.read(chunk))
        return h.hexdigest()
    except Exception:
        return ""


def hash_file(path: str) -> str:
    """Empreinte SHA-256 (64 Ko) — à appeler AVANT toute suppression."""
    return _file_hash(path)


def _inode_key(path: str) -> Optional[Tuple[int, int]]:
    try:
        s = os.stat(path)
        return (s.st_dev, s.st_ino)
    except Exception:
        return None


def _calc_size(path: str) -> Tuple[int, int]:
    if os.path.isfile(path):
        try:
            return os.path.getsize(path), 1
        except Exception:
            return 0, 1
    total, count = 0, 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
                count += 1
            except Exception:
                pass
    return total, count



def format_size(bytes_: int) -> str:
    if bytes_ >= 1_073_741_824:
        return f"{bytes_ / 1_073_741_824:.2f} Go"
    if bytes_ >= 1_048_576:
        return f"{bytes_ / 1_048_576:.1f} Mo"
    return f"{bytes_ / 1024:.1f} Ko"


# ── Scan par hash ─────────────────────────────────────────────────────────────

def collect_signatures(path: str) -> List[Dict]:
    """
    Construit la liste des signatures (inode, taille, hash) de tous les fichiers
    vidéo sous path. Pour un fichier unique : une seule signature. Pour un dossier
    (ex: série entière) : une signature par épisode.
    À appeler AVANT toute suppression Radarr/Sonarr — path doit encore exister.
    """
    sigs: List[Dict] = []
    if not path:
        return sigs
    if os.path.isfile(path):
        try:
            size = os.path.getsize(path)
        except OSError:
            size = None
        sigs.append({"inode": _inode_key(path), "size": size, "hash": _file_hash(path)})
    elif os.path.isdir(path):
        for root, _dirs, files in os.walk(path):
            for fname in sorted(files):
                if Path(fname).suffix.lower() not in VIDEO_EXTENSIONS:
                    continue
                fpath = os.path.join(root, fname)
                try:
                    size = os.path.getsize(fpath)
                except OSError:
                    size = None
                sigs.append({"inode": _inode_key(fpath), "size": size, "hash": _file_hash(fpath)})
    return sigs


def scan_copies_smart(
    title: str,
    known_path: str,
    extra_paths: List[str],
    known_signatures: Optional[List[Dict]] = None,
    allow_name_fallback: bool = False,
    torrents: Optional[List[Dict]] = None,
) -> Dict:
    """
    Trouve toutes les copies du contenu ciblé (voir core.locator) : hardlinks
    (inode), copies physiques (taille + empreinte), liens symboliques cross-seed,
    dans tout le dossier de téléchargements — regroupées en unités sûres (un
    dossier n'est retenu que si TOUTES ses vidéos sont ce contenu).
    torrents : liste Transmission ; si fournie, les torrents correspondants sont
    renvoyés dans "torrents" (identité de fichier, jamais par nom).
    allow_name_fallback=True ajoute des candidats par nom, NON vérifiés, à cocher
    à la main — jamais utilisés pour une suppression automatique.
    """
    from core.locator import locate

    known_real = os.path.realpath(known_path) if known_path and os.path.exists(known_path) else ""
    source_size_bytes = 0
    if known_real:
        source_size_bytes, _ = _calc_size(known_path)

    loc = locate(known_path, known_signatures=known_signatures, torrents=torrents)
    found = list(loc["copies"])

    if allow_name_fallback:
        found_real = {os.path.realpath(e["path"]) for e in found}
        torrent_roots = {os.path.realpath(t["host_root"]) for t in loc["torrents"] if t.get("host_root")}
        for candidate in find_candidate_dirs_by_name(title, extra_paths):
            real_c = os.path.realpath(candidate["path"])
            if real_c in found_real or real_c in torrent_roots:
                continue
            if known_real and (real_c == known_real or real_c.startswith(known_real + os.sep)
                               or known_real.startswith(real_c + os.sep)):
                continue
            if any(real_c.startswith(f + os.sep) or f.startswith(real_c + os.sep) for f in found_real):
                continue
            found.append(candidate)
            found_real.add(real_c)

    sigs = loc["signatures"]
    verified = [e for e in found if e["match_method"] != "name"]
    total = sum(e["size_bytes"] for e in found)
    # Hardlinks / liens symboliques : mêmes blocs disque que la source → 0 octet libéré
    freed_from_copies = sum(e["size_bytes"] for e in verified if not e["is_hardlink"])
    total_freed = source_size_bytes + freed_from_copies
    if not sigs:
        strategy = "nom (aucune empreinte disponible)" if found else "indisponible"
    else:
        strategy = "inode+hash" if any(s.get("inode") for s in sigs) else "hash"
    return {
        "title":              title,
        "known_path":         known_path,
        "source_hash":        sigs[0]["hash"] if sigs else "",
        "source_size_bytes":  source_size_bytes,
        "source_size_human":  format_size(source_size_bytes),
        "strategy":           strategy,
        "copies":             found,
        "total_copies":       len(found),
        "total_size_bytes":   total,
        "total_size_human":   format_size(total),
        "total_freed_bytes":  total_freed,
        "total_freed_human":  format_size(total_freed),
        "has_inode_match":    any(e["is_hardlink"] for e in verified),
        "skipped":            not found,
        "torrents":           loc["torrents"],
        "signatures":         sigs,
    }


# ── Recherche par nom (aperçu manuel uniquement — jamais pour suppression auto) ─

_RELEASE_NOISE = re.compile(
    r"\b(?:19|20)\d{2}\b|\bs\d{1,2}(?:e\d{1,3})?\b|\bseason\s?\d+\b|\bsaison\s?\d+\b"
    r"|\b(1080p?|2160p?|720p?|480p?|4k|uhd|hdr10?|bluray|blu-?ray|bdrip|webrip|web-?dl|web|hdtv|dvdrip"
    r"|x264|x265|hevc|aac|dts|ddp?5\.1|truehd|atmos|remux|complete|repack|proper"
    r"|french|vf2?|vff|vfq|vostfr|multi|truefrench)\b",
    re.IGNORECASE,
)


def normalize_release_name(name: str) -> str:
    """Normalise un nom de dossier/torrent selon les conventions trackers — points,
    tirets et underscores interchangeables avec les espaces — pour comparer
    'American.Dad', 'american-dad', 'American_Dad', 'AMERICAN DAD' etc."""
    n = name.lower()
    n = re.sub(r"[._\-]+", " ", n)
    n = _RELEASE_NOISE.sub(" ", n)
    n = re.sub(r"[^\w\s]", " ", n)
    return re.sub(r"\s+", " ", n).strip()


def _name_is_same_title(needle: str, dirname: str) -> bool:
    """Le nom normalisé doit COMMENCER par le titre, et ce qui suit ne doit pas
    être un numéro de suite : « Cars » ne doit pas attraper « Cars 2 » ni
    « Cars 3 », « Scream » ne doit pas attraper « Scream 4 »."""
    norm = normalize_release_name(dirname)
    if not norm.startswith(needle):
        return False
    rest = norm[len(needle):]
    if rest and not rest.startswith(" "):
        return False   # « carsten » ≠ « cars »
    nxt = rest.split()[:1]
    if nxt and (nxt[0].isdigit() or nxt[0] in {"ii", "iii", "iv", "v", "vi"}):
        return False
    return True


def find_candidate_dirs_by_name(title: str, search_paths: List[str], max_depth: int = 2) -> List[Dict]:
    """Recherche par NOM (pas par contenu) des dossiers pouvant correspondre à `title`
    dans search_paths, jusqu'à max_depth sous-niveaux — gère les deux structures
    courantes : dossier série contenant les saisons, OU dossiers de saison directement
    à la racine (ex: 'American Dad S01', 'American.Dad.S02...').
    Résultats NON vérifiés par contenu (pas de hash/inode) — à n'utiliser que pour un
    aperçu supervisé par un humain, jamais pour une suppression automatique."""
    needle = normalize_release_name(title)
    needle_words = {w for w in needle.split() if len(w) >= 3}
    if not needle_words:
        return []

    found: Dict[str, Dict] = {}
    for base in search_paths:
        base = base.strip()
        if not base or not os.path.isdir(base):
            continue
        base_depth = base.rstrip(os.sep).count(os.sep)
        try:
            for root, dirs, _files in os.walk(base, followlinks=False):
                depth = root.count(os.sep) - base_depth
                if depth >= max_depth:
                    dirs.clear()
                    continue
                matched_here = []
                for d in dirs:
                    dwords = set(normalize_release_name(d).split())
                    if not dwords:
                        continue
                    # Tous les mots significatifs du titre doivent être présents dans
                    # le nom du dossier — insensible à l'ordre (gère les variantes de
                    # séparateurs/inversions utilisées par certains trackers).
                    if needle_words <= dwords and _name_is_same_title(needle, d):
                        full = os.path.join(root, d)
                        if full not in found:
                            size_bytes, file_count = _calc_size(full)
                            found[full] = {
                                "path":         full,
                                "is_dir":       True,
                                "size_bytes":   size_bytes,
                                "size_human":   format_size(size_bytes),
                                "file_count":   file_count,
                                "match_method": "name",
                                "is_hardlink":  False,
                            }
                        matched_here.append(d)
                # Ne pas redescendre dans un dossier déjà retenu (ex: dossier série
                # matché) : ses sous-dossiers (saisons/épisodes) matchent aussi le nom
                # et seraient sinon comptés une deuxième fois en plus du parent.
                for d in matched_here:
                    dirs.remove(d)
        except PermissionError as e:
            logger.warning("[Scan nom] Accès refusé à %s : %s", base, e)
    return list(found.values())


# ── Suppression ───────────────────────────────────────────────────────────────

def delete_copy(entry: Dict) -> Dict:
    path = entry["path"]
    try:
        if os.path.islink(path):
            os.unlink(path)
        elif entry["is_dir"]:
            shutil.rmtree(path)
        else:
            os.remove(path)
            _delete_companions(path)
        logger.info("[Fileops] Supprimé : %s", path)
        return {**entry, "success": True, "error": None}
    except FileNotFoundError:
        logger.info("[Fileops] Déjà supprimé (ignoré) : %s", path)
        return {**entry, "success": True, "error": None}
    except Exception as e:
        logger.error("[Fileops] Erreur suppression %s : %s", path, e)
        return {**entry, "success": False, "error": str(e)}


def _is_category(p) -> bool:
    """Dossiers de catégorie (downloads/complete/film, downloads/série/Fallout,
    downloads/.cross-seed-links/C411…) : jamais supprimés, même vides —
    Transmission/Radarr/Sonarr y écrivent."""
    try:
        from core.locator import downloads_root
        dl = os.path.normpath(downloads_root() or "")
    except Exception:
        return False
    p = os.path.normpath(str(p))
    if not dl or not (p == dl or p.startswith(dl + os.sep)):
        return False
    parts = os.path.relpath(p, dl).split(os.sep)
    if parts == ["."] or len(parts) <= 1:
        return True
    if len(parts) == 2:
        # film/<Release> est un dossier de film, pas une catégorie
        from config import get_config
        movies = os.path.normpath(get_config().get("library_root_movies", "") or "")
        return os.path.join(dl, parts[0]) != movies
    return False


def _prune_empty_parents(path: str, roots: List[str]):
    """
    Remonte l'arborescence depuis le parent de path et supprime les dossiers devenus
    vides, jusqu'à — mais sans jamais supprimer — une des racines configurées
    (extra_paths / library_root_*). Évite de laisser des dossiers wrapper vides
    (ex: séries imbriquées NOM/NOM/épisodes) après suppression d'une release.
    """
    roots_norm = {os.path.normpath(r) for r in roots if r and r.strip()}
    parent = os.path.dirname(os.path.normpath(path))
    while parent and os.path.isdir(parent) and os.path.normpath(parent) not in roots_norm \
            and not _is_category(parent):
        try:
            if os.listdir(parent):
                break
            os.rmdir(parent)
            logger.info("[Fileops] Dossier vide supprimé : %s", parent)
        except OSError:
            break
        next_parent = os.path.dirname(parent)
        if next_parent == parent:
            break
        parent = next_parent


def _delete_companions(file_path: str):
    p = Path(file_path)
    parent, stem = p.parent, p.stem
    for sibling in list(parent.iterdir()):
        if sibling == p:
            continue
        # Égal au stem, ou stem + suffixe de langue/tag (ex: Movie.fr.srt) — mais pas
        # un stem qui prolonge un numéro (Show.S01E01 ne doit pas matcher Show.S01E010).
        if (sibling.stem == stem or sibling.stem.startswith(stem + ".")) \
                and sibling.suffix.lower() in METADATA_EXTENSIONS:
            try:
                sibling.unlink()
            except Exception:
                pass
    try:
        remaining = list(parent.iterdir())
        if not _is_category(parent) and \
                all(f.is_file() and f.suffix.lower() in METADATA_EXTENSIONS for f in remaining):
            for f in remaining:
                try:
                    Path(f).unlink()
                except Exception:
                    pass
            parent.rmdir()
    except Exception:
        pass


def run_cleanup_from_scan(scan_result: Dict, roots: Optional[List[str]] = None) -> Dict:
    copies = scan_result.get("copies", [])
    if not copies:
        return {"skipped": True, "copies_found": 0}

    results = [delete_copy(c) for c in copies]
    if roots:
        for r in results:
            if r["success"]:
                _prune_empty_parents(r["path"], roots)
    ok          = [r for r in results if r["success"]]
    # Idem : un hardlink supprimé ne libère aucun octet supplémentaire (même inode
    # que la source), donc il ne compte pas dans l'espace réellement libéré.
    total_bytes = sum(r["size_bytes"] for r in ok if not r.get("is_hardlink"))
    total_files = sum(r["file_count"] for r in ok)

    return {
        "skipped":        False,
        "copies_found":   len(copies),
        "copies_deleted": len(ok),
        "copies_failed":  len(results) - len(ok),
        "total_files":    total_files,
        "size_bytes":     total_bytes,
        "size_human":     format_size(total_bytes),
        "details": [
            {
                "path":         r["path"],
                "success":      r["success"],
                "size":         format_size(r["size_bytes"]),
                "files":        r["file_count"],
                "match_method": r.get("match_method", "?"),
                "is_hardlink":  r.get("is_hardlink", False),
                "error":        r.get("error"),
            }
            for r in results
        ],
    }


def run_cleanup(title: str, file_path: str, extra_paths: List[str], known_signatures: Optional[List[Dict]] = None,
                 allow_name_fallback: bool = False, precomputed_scan: Optional[Dict] = None) -> Dict:
    """
    Appelé depuis pipeline.py après suppression Radarr/Sonarr.
    known_signatures doit être précalculé AVANT la suppression (via collect_signatures)
    car le fichier/dossier source n'existe généralement plus au moment de cet appel.
    allow_name_fallback : réservé aux suppressions manuelles (triggered_by="manual").
    """
    if precomputed_scan is not None:
        result = run_cleanup_from_scan(precomputed_scan, roots=extra_paths)
        _invalidate()
        return result
    if not extra_paths:
        return {"skipped": True, "copies_found": 0}
    scan = scan_copies_smart(title, file_path, extra_paths, known_signatures=known_signatures,
                              allow_name_fallback=allow_name_fallback)
    result = run_cleanup_from_scan(scan, roots=extra_paths)
    _invalidate()
    return result


def _invalidate():
    try:
        from core.locator import invalidate_index
        invalidate_index()
    except Exception:
        pass


def delete_selected_paths(paths: List[str], roots: Optional[List[str]] = None) -> Dict:
    """Supprime une liste de chemins explicitement choisis (ex: candidats "nom" cochés
    à la main par l'utilisateur dans la modal de confirmation). Aucun scan/matching —
    les chemins sont pris tels quels, seule leur existence est vérifiée."""
    entries = []
    for p in paths:
        if not p or not os.path.exists(p):
            continue
        size_bytes, file_count = _calc_size(p)
        entries.append({
            "path": p, "is_dir": os.path.isdir(p),
            "size_bytes": size_bytes, "file_count": file_count,
            "match_method": "name", "is_hardlink": False,
        })
    if not entries:
        return {"skipped": True, "copies_found": 0}
    return run_cleanup_from_scan({"copies": entries}, roots=roots)
