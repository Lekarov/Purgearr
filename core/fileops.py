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
) -> Dict:
    """
    Trouve les copies dans extra_paths par inode (hardlinks) puis hash SHA-256.
    known_signatures : signatures pré-calculées avant suppression Radarr/Sonarr
    (une par fichier vidéo — un dossier série entière en a donc plusieurs).
    Si non fournies et que known_path existe encore (scan de prévisualisation
    avant suppression), elles sont calculées ici.
    Par défaut, aucun matching par titre — uniquement contenu identique (hash/inode).
    allow_name_fallback=True ajoute une recherche par nom (variantes de séparateurs
    tracker) en complément — réservé au scan manuel supervisé (jamais aux
    suppressions automatiques webhook/queue, un mauvais match nom pourrait viser
    le mauvais dossier).
    """
    known_real   = os.path.realpath(known_path) if known_path and os.path.exists(known_path) else ""
    known_is_dir = bool(known_path) and os.path.isdir(known_path)

    if known_signatures is None:
        known_signatures = collect_signatures(known_path)

    # Taille du fichier/dossier source (pour affichage dans la modal)
    source_size_bytes = 0
    if known_path and (os.path.isfile(known_path) or os.path.isdir(known_path)):
        source_size_bytes, _ = _calc_size(known_path)

    if not known_signatures:
        name_matches = find_candidate_dirs_by_name(title, extra_paths) if allow_name_fallback else []
        total = sum(e["size_bytes"] for e in name_matches)
        return {
            "title": title, "known_path": known_path, "source_hash": "",
            "source_size_bytes": source_size_bytes,
            "source_size_human": format_size(source_size_bytes),
            "strategy": "nom (aucun hash disponible)" if name_matches else "indisponible",
            "copies": name_matches, "total_copies": len(name_matches),
            "total_size_bytes": total, "total_size_human": format_size(total),
            "total_freed_bytes": source_size_bytes + total,
            "total_freed_human": format_size(source_size_bytes + total),
            "has_inode_match": False, "skipped": not name_matches,
        }

    known_inodes = {s["inode"] for s in known_signatures if s.get("inode")}
    by_size: Dict[int, List[Dict]] = {}
    # signatures sans taille connue (ex: hash historique seul depuis cleanup_index.json)
    # — impossible de les préfiltrer par taille, on les compare à tout fichier candidat
    hash_only: List[Dict] = []
    for s in known_signatures:
        if s.get("size") is not None:
            by_size.setdefault(s["size"], []).append(s)
        elif s.get("hash"):
            hash_only.append(s)

    strategy = "inode+hash" if known_inodes else "hash"
    found: List[Dict] = []
    reported: set = set()  # global à tous les base paths pour éviter les doublons

    for base in extra_paths:
        base = base.strip()
        if not base or not os.path.isdir(base):
            logger.warning("[Scan] Chemin ignoré (introuvable) : %s", base)
            continue

        base_depth = base.rstrip(os.sep).count(os.sep)

        try:
            for root, dirs, files in os.walk(base, followlinks=False):
                depth = root.count(os.sep) - base_depth
                if depth >= 5:
                    dirs.clear()
                    continue

                for fname in files:
                    if Path(fname).suffix.lower() not in VIDEO_EXTENSIONS:
                        continue
                    fpath = os.path.join(root, fname)

                    # Ignorer les fichiers appartenant au dossier/fichier source
                    try:
                        real_fpath = os.path.realpath(fpath)
                        if known_real:
                            if known_is_dir and real_fpath.startswith(known_real + os.sep):
                                continue
                            elif not known_is_dir and real_fpath == known_real:
                                continue
                    except Exception:
                        pass

                    match_method: Optional[str] = None
                    finode = _inode_key(fpath)
                    if finode and finode in known_inodes:
                        match_method = "inode"
                    else:
                        # Préfiltre par taille quand connue (rapide, évite d'ouvrir le fichier) ;
                        # les signatures sans taille (hash_only) sont testées systématiquement
                        try:
                            fsize = os.path.getsize(fpath)
                        except OSError:
                            continue
                        candidates = by_size.get(fsize, []) + hash_only
                        if candidates:
                            fhash = _file_hash(fpath)
                            if any(fhash == c["hash"] for c in candidates if c.get("hash")):
                                match_method = "hash"

                    if not match_method:
                        continue

                    # Dossier parent du fichier trouvé = dossier release
                    # SAUF si ce parent est un dossier catégorie (film/, série/…)
                    # contenant plusieurs films — dans ce cas on ne prend que le fichier.
                    parent = os.path.dirname(fpath)
                    if os.path.normpath(parent) == os.path.normpath(base):
                        release = fpath   # fichier directement dans base
                    else:
                        try:
                            video_siblings = sum(
                                1 for f in os.scandir(parent)
                                if f.is_file() and Path(f.name).suffix.lower() in VIDEO_EXTENSIONS
                            )
                        except Exception:
                            video_siblings = 1
                        if video_siblings <= 4:
                            release = parent  # vrai dossier release (1 film)
                        else:
                            release = fpath   # dossier catégorie → fichier seul

                    if release in reported:
                        continue
                    reported.add(release)

                    # Ignorer si c'est la source elle-même
                    try:
                        real_release = os.path.realpath(release)
                        if known_real:
                            if known_is_dir and real_release == known_real:
                                continue
                            elif not known_is_dir and real_release == os.path.dirname(known_real):
                                continue
                    except Exception:
                        pass

                    size_bytes, file_count = _calc_size(release)
                    found.append({
                        "path":         release,
                        "is_dir":       os.path.isdir(release),
                        "size_bytes":   size_bytes,
                        "size_human":   format_size(size_bytes),
                        "file_count":   file_count,
                        "match_method": match_method,
                        "is_hardlink":  match_method == "inode",
                    })
                    logger.info("[Scan] Copie trouvée (%s) : %s", match_method, release)

        except PermissionError as e:
            logger.warning("[Scan] Accès refusé à %s : %s", base, e)

    if allow_name_fallback:
        found_real = {os.path.realpath(e["path"]) for e in found}
        for candidate in find_candidate_dirs_by_name(title, extra_paths):
            real_c = os.path.realpath(candidate["path"])
            if real_c in found_real or (known_real and (real_c == known_real or real_c.startswith(known_real + os.sep))):
                continue
            found.append(candidate)
            found_real.add(real_c)

    total = sum(e["size_bytes"] for e in found)
    # Les hardlinks partagent les mêmes blocs disque que la source : les compter
    # dans l'espace libéré double leur poids (source + copie = même donnée physique).
    freed_from_copies = sum(e["size_bytes"] for e in found if not e["is_hardlink"])
    total_freed = source_size_bytes + freed_from_copies
    return {
        "title":              title,
        "known_path":         known_path,
        "source_hash":        known_signatures[0]["hash"] if known_signatures else "",
        "source_size_bytes":  source_size_bytes,
        "source_size_human":  format_size(source_size_bytes),
        "strategy":           strategy,
        "copies":             found,
        "total_copies":       len(found),
        "total_size_bytes":   total,
        "total_size_human":   format_size(total),
        "total_freed_bytes":  total_freed,
        "total_freed_human":  format_size(total_freed),
        "has_inode_match":    any(e["is_hardlink"] for e in found),
        "skipped":            False,
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
                    if needle_words <= dwords:
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
        if entry["is_dir"]:
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


def _prune_empty_parents(path: str, roots: List[str]):
    """
    Remonte l'arborescence depuis le parent de path et supprime les dossiers devenus
    vides, jusqu'à — mais sans jamais supprimer — une des racines configurées
    (extra_paths / library_root_*). Évite de laisser des dossiers wrapper vides
    (ex: séries imbriquées NOM/NOM/épisodes) après suppression d'une release.
    """
    roots_norm = {os.path.normpath(r) for r in roots if r and r.strip()}
    parent = os.path.dirname(os.path.normpath(path))
    while parent and os.path.isdir(parent) and os.path.normpath(parent) not in roots_norm:
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
        if all(f.is_file() and f.suffix.lower() in METADATA_EXTENSIONS for f in remaining):
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
                 allow_name_fallback: bool = False) -> Dict:
    """
    Appelé depuis pipeline.py après suppression Radarr/Sonarr.
    known_signatures doit être précalculé AVANT la suppression (via collect_signatures)
    car le fichier/dossier source n'existe généralement plus au moment de cet appel.
    allow_name_fallback : réservé aux suppressions manuelles (triggered_by="manual").
    """
    if not extra_paths:
        return {"skipped": True, "copies_found": 0}
    scan = scan_copies_smart(title, file_path, extra_paths, known_signatures=known_signatures,
                              allow_name_fallback=allow_name_fallback)
    return run_cleanup_from_scan(scan, roots=extra_paths)


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
