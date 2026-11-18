"""
Localisation exacte de tout ce qui appartient à un média avant suppression.

Principe : on ne devine plus par le NOM. On part du fichier/dossier réel (résolu
depuis Jellyfin) et on retrouve, par IDENTITÉ de contenu :
  - les torrents Transmission dont au moins un fichier est ce contenu
    (chemin identique, même inode = hardlink, ou même taille + même empreinte),
  - les copies sur disque (hardlinks, copies physiques, liens symboliques
    cross-seed) dans tout le dossier de téléchargements.

Organisation du NAS (montages Docker) prise en compte via les correspondances
de chemins conteneur → hôte : Transmission voit /downloads, Radarr/Sonarr/Jellyfin
voient /media/film et /media/série.

Toute la recherche se fait AVANT la moindre suppression (sinon les liens
symboliques deviennent orphelins et les inodes disparaissent).
"""
import logging
import os
import threading
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

from config import get_config

logger = logging.getLogger("purgearr.locator")

VIDEO_EXTENSIONS = {".mkv", ".mp4", ".avi", ".mov", ".wmv", ".m4v", ".ts", ".m2ts", ".iso"}
SAMPLE_MAX_BYTES = 300 * 1024 * 1024
HEAD_BYTES = 65536


# ── Correspondances de chemins conteneur ↔ hôte ───────────────────────────────

def downloads_root() -> str:
    cfg = get_config()
    root = (cfg.get("downloads_root") or "").strip()
    if root:
        return root.rstrip("/")
    movies = (cfg.get("library_root_movies") or "").strip().rstrip("/")
    return os.path.dirname(movies) if movies else ""


def path_mappings() -> List[Tuple[str, str]]:
    """(préfixe conteneur, préfixe hôte), du plus long au plus court."""
    cfg = get_config()
    dl = downloads_root()
    maps: Dict[str, str] = {}
    if dl:
        maps["/downloads"] = dl
        maps["/data"] = dl
    if cfg.get("library_root_movies"):
        maps["/media/film"] = cfg["library_root_movies"].rstrip("/")
    if cfg.get("library_root_series"):
        maps["/media/série"] = cfg["library_root_series"].rstrip("/")
    for k, v in (cfg.get("path_mappings") or {}).items():
        if k and v:
            maps[k.rstrip("/")] = v.rstrip("/")
    return sorted(maps.items(), key=lambda kv: len(kv[0]), reverse=True)


def to_host(path: str) -> str:
    if not path:
        return ""
    if os.path.exists(path):
        return path
    for cont, host in path_mappings():
        if path == cont or path.startswith(cont + "/"):
            return host + path[len(cont):]
    return path


def to_container(host_path: str, prefixes: Iterable[str]) -> Set[str]:
    """Toutes les écritures conteneur possibles d'un chemin hôte."""
    out = {host_path}
    wanted = set(prefixes)
    for cont, host in path_mappings():
        if cont in wanted and (host_path == host or host_path.startswith(host + "/")):
            out.add(cont + host_path[len(host):])
    return out


def host_resolve(path: str) -> str:
    """realpath qui sait suivre les liens cross-seed : leur cible est écrite en
    chemin conteneur (/downloads/…), introuvable tel quel depuis l'hôte."""
    p = path
    for _ in range(10):
        if not os.path.islink(p):
            break
        target = os.readlink(p)
        if not os.path.isabs(target):
            target = os.path.normpath(os.path.join(os.path.dirname(p), target))
        p = to_host(target)
    return os.path.realpath(p)


# ── Empreintes ────────────────────────────────────────────────────────────────

_hash_cache: Dict[Tuple[int, int, int, float], str] = {}


def head_hash(path: str) -> str:
    """SHA-256 des 64 premiers Ko (compatible avec l'historique cleanup_index)."""
    import hashlib
    try:
        st = os.stat(path)
        key = (st.st_dev, st.st_ino, st.st_size, st.st_mtime)
        if key in _hash_cache:
            return _hash_cache[key]
        h = hashlib.sha256()
        with open(path, "rb") as f:
            h.update(f.read(HEAD_BYTES))
        digest = h.hexdigest()
        if len(_hash_cache) > 20000:
            _hash_cache.clear()
        _hash_cache[key] = digest
        return digest
    except OSError:
        return ""


def is_video(name: str) -> bool:
    return Path(name).suffix.lower() in VIDEO_EXTENSIONS


def is_sample(path: str, size: int) -> bool:
    n = os.path.basename(path).lower()
    return size < SAMPLE_MAX_BYTES and ("sample" in n or "trailer" in n)


def _inode(st: os.stat_result) -> Tuple[int, int]:
    return (st.st_dev, st.st_ino)


# ── Index du disque (un parcours complet ≈ 0,3 s pour ~16 000 fichiers) ───────

class DiskIndex:
    def __init__(self, roots: List[str], exclude: List[str]):
        self.roots = roots
        self.by_inode: Dict[Tuple[int, int], List[str]] = {}
        self.by_size: Dict[int, List[str]] = {}
        self.symlinks: List[Tuple[str, str]] = []   # (lien, cible hôte absolue)
        self.built_at = time.time()
        excl = {os.path.normpath(e) for e in exclude if e}
        seen_dirs: Set[str] = set()
        for root in roots:
            if not root or not os.path.isdir(root):
                continue
            stack = [root]
            while stack:
                d = stack.pop()
                nd = os.path.normpath(d)
                if nd in excl or nd in seen_dirs:
                    continue
                seen_dirs.add(nd)
                try:
                    entries = list(os.scandir(d))
                except OSError:
                    continue
                for e in entries:
                    try:
                        if e.is_symlink():
                            target = os.readlink(e.path)
                            if not os.path.isabs(target):
                                target = os.path.normpath(os.path.join(d, target))
                            self.symlinks.append((e.path, to_host(target)))
                        elif e.is_dir(follow_symlinks=False):
                            stack.append(e.path)
                        elif e.is_file(follow_symlinks=False) and is_video(e.name):
                            st = e.stat(follow_symlinks=False)
                            self.by_inode.setdefault(_inode(st), []).append(e.path)
                            self.by_size.setdefault(st.st_size, []).append(e.path)
                    except OSError:
                        continue


_index_lock = threading.Lock()
_index: Optional[DiskIndex] = None
INDEX_TTL = 300


def scan_roots() -> Tuple[List[str], List[str]]:
    cfg = get_config()
    roots: List[str] = []
    dl = downloads_root()
    if dl:
        roots.append(dl)
    for p in [cfg.get("library_root_movies", ""), cfg.get("library_root_series", "")] + list(cfg.get("extra_paths", [])):
        p = (p or "").strip().rstrip("/")
        if p and not any(p == r or p.startswith(r + "/") for r in roots):
            roots.append(p)
    exclude = [os.path.join(dl, "incomplete")] if dl else []
    exclude += [p for p in (cfg.get("scan_exclude") or [])]
    return roots, exclude


def get_index(force: bool = False) -> DiskIndex:
    global _index
    with _index_lock:
        if force or _index is None or time.time() - _index.built_at > INDEX_TTL:
            roots, exclude = scan_roots()
            t0 = time.time()
            _index = DiskIndex(roots, exclude)
            logger.info("[Index] %d vidéos, %d liens indexés en %.2fs",
                        sum(len(v) for v in _index.by_size.values()), len(_index.symlinks), time.time() - t0)
        return _index


def invalidate_index():
    global _index
    with _index_lock:
        _index = None


# ── Signatures du contenu ciblé ───────────────────────────────────────────────

def target_videos(path: str) -> List[str]:
    if not path or not os.path.exists(path):
        return []
    if os.path.isfile(path):
        return [path]
    out = []
    for root, _dirs, files in os.walk(path):
        for f in files:
            fp = os.path.join(root, f)
            if is_video(f) and not os.path.islink(fp):
                out.append(fp)
    return sorted(out)


def signatures_for(path: str) -> List[Dict]:
    sigs = []
    for fp in target_videos(path):
        try:
            st = os.stat(fp)
        except OSError:
            continue
        sigs.append({"path": fp, "inode": _inode(st), "size": st.st_size, "hash": head_hash(fp)})
    return sigs


class Matcher:
    """Décide si un fichier est le même contenu que la cible."""

    def __init__(self, sigs: List[Dict], target_path: str = ""):
        self.target_real = os.path.realpath(target_path) if target_path and os.path.exists(target_path) else ""
        self.target_is_dir = bool(self.target_real) and os.path.isdir(self.target_real)
        self.paths = {os.path.realpath(s["path"]) for s in sigs if s.get("path")}
        self.inodes = {tuple(s["inode"]) for s in sigs if s.get("inode")}
        self.by_size: Dict[int, Set[str]] = {}
        self.hash_only: Set[str] = set()
        for s in sigs:
            if s.get("size") is not None and s.get("hash"):
                self.by_size.setdefault(s["size"], set()).add(s["hash"])
            elif s.get("hash"):
                self.hash_only.add(s["hash"])

    def inside_target(self, real: str) -> bool:
        if not self.target_real:
            return False
        return real == self.target_real or (self.target_is_dir and real.startswith(self.target_real + os.sep))

    def match(self, path: str) -> Optional[str]:
        """'source' | 'inode' | 'hash' | None"""
        try:
            real = host_resolve(path)
        except OSError:
            return None
        if real in self.paths or self.inside_target(real):
            return "source"
        try:
            st = os.stat(real)
        except OSError:
            return None
        if _inode(st) in self.inodes:
            return "inode"
        hashes = self.by_size.get(st.st_size)
        if hashes or self.hash_only:
            h = head_hash(real)
            if h and ((hashes and h in hashes) or h in self.hash_only):
                return "hash"
        return None


# ── Torrents ─────────────────────────────────────────────────────────────────

def torrent_root(t: Dict) -> str:
    return to_host(f"{(t.get('downloadDir') or '').rstrip('/')}/{t.get('name', '')}")


def torrent_files(t: Dict) -> List[str]:
    dl = to_host((t.get("downloadDir") or "").rstrip("/"))
    return [f"{dl}/{(f.get('name') or '').lstrip('/')}" for f in (t.get("files") or []) if f.get("name")]


def match_torrents(matcher: Matcher, torrents: List[Dict]) -> List[Dict]:
    """Torrents dont au moins un fichier vidéo est le contenu ciblé."""
    found = []
    for t in torrents:
        how = None
        for fp in torrent_files(t):
            if not is_video(fp) or not os.path.lexists(fp):
                continue
            # stat seul (rapide) ; empreinte lue uniquement si la taille correspond
            m = matcher.match(fp)
            if m:
                how = m
                break
        if how:
            found.append({**t, "match_method": how, "host_root": torrent_root(t)})
    return found


# ── Regroupement des copies en unités de suppression sûres ───────────────────

def protected_dirs(torrents: List[Dict]) -> Set[str]:
    """Dossiers à ne JAMAIS supprimer en bloc : racines, dossiers de catégorie,
    dossiers de téléchargement Transmission (ex: série/Fallout), etc."""
    cfg = get_config()
    prot = set()
    roots, exclude = scan_roots()
    for p in roots + exclude + [cfg.get("library_root_movies", ""), cfg.get("library_root_series", "")] \
            + list(cfg.get("extra_paths", [])):
        if p:
            prot.add(os.path.normpath(p))
    for t in torrents:
        dl = to_host((t.get("downloadDir") or "").rstrip("/"))
        while dl and dl not in ("/", ""):
            prot.add(os.path.normpath(dl))
            parent = os.path.dirname(dl)
            if parent == dl:
                break
            dl = parent
    dl = downloads_root()
    if dl:
        for name in os.listdir(dl) if os.path.isdir(dl) else []:
            full = os.path.join(dl, name)
            if os.path.isdir(full):
                prot.add(os.path.normpath(full))
                if name == ".cross-seed-links":
                    for sub in os.listdir(full):
                        prot.add(os.path.normpath(os.path.join(full, sub)))
    return prot


def _all_videos_match(folder: str, matched: Set[str]) -> bool:
    for root, _dirs, files in os.walk(folder):
        for f in files:
            fp = os.path.join(root, f)
            if not is_video(f):
                continue
            if os.path.normpath(fp) in matched:
                continue
            try:
                size = os.lstat(fp).st_size
            except OSError:
                continue
            if is_sample(fp, size):
                continue
            return False
    return True


def group_units(matched: Dict[str, str], protected: Set[str], matcher: Matcher) -> List[Dict]:
    """matched : {chemin: méthode}. Remonte au dossier release le plus haut dont
    TOUTES les vidéos font partie de la cible ; sinon fichier seul."""
    norm_matched = {os.path.normpath(p) for p in matched}
    units: Dict[str, Dict] = {}
    for path, method in matched.items():
        unit = path
        parent = os.path.dirname(path)
        while parent and os.path.normpath(parent) not in protected:
            real_parent = os.path.realpath(parent)
            if matcher.inside_target(real_parent) or (matcher.target_real and matcher.target_real.startswith(real_parent + os.sep)):
                break
            if not _all_videos_match(parent, norm_matched):
                break
            unit = parent
            nxt = os.path.dirname(parent)
            if nxt == parent:
                break
            parent = nxt
        key = os.path.normpath(unit)
        u = units.setdefault(key, {"path": unit, "methods": set()})
        u["methods"].add(method)
    # retirer les unités incluses dans une autre
    keys = sorted(units, key=len)
    final = []
    for k in keys:
        if any(k.startswith(f["_key"] + os.sep) for f in final):
            continue
        units[k]["_key"] = k
        final.append(units[k])
    out = []
    for u in final:
        p = u["path"]
        is_link = os.path.islink(p)
        is_dir = os.path.isdir(p) and not is_link
        if is_link:
            size, count = 0, 1
        elif is_dir:
            size, count = _dir_size(p)
        else:
            try:
                size, count = os.path.getsize(p), 1
            except OSError:
                size, count = 0, 1
        methods = u["methods"]
        if "hash" in methods:
            method = "hash"
        elif "inode" in methods:
            method = "inode"
        else:
            method = "symlink"
        out.append({
            "path": p, "is_dir": is_dir, "is_symlink": is_link,
            "size_bytes": size, "size_human": _human(size), "file_count": count,
            "match_method": method,
            # un hardlink ou un lien symbolique ne libère aucun octet
            "is_hardlink": method in ("inode", "symlink"),
        })
    return sorted(out, key=lambda e: e["path"])


def _human(n: int) -> str:
    from core.fileops import format_size
    return format_size(n)


def _dir_size(path: str) -> Tuple[int, int]:
    total, count, seen = 0, 0, set()
    for root, _dirs, files in os.walk(path):
        for f in files:
            fp = os.path.join(root, f)
            try:
                st = os.lstat(fp)
            except OSError:
                continue
            count += 1
            if os.path.islink(fp) or _inode(st) in seen:
                continue
            seen.add(_inode(st))
            total += st.st_size
    return total, count


# ── Point d'entrée ───────────────────────────────────────────────────────────

def locate(target_path: str, known_signatures: Optional[List[Dict]] = None,
           torrents: Optional[List[Dict]] = None, fresh_index: bool = False) -> Dict:
    """
    Retourne {signatures, torrents, copies} pour target_path.
    known_signatures : pour les restes d'un média déjà supprimé (target_path vide).
    torrents : liste Transmission (champs files avec length) ; None = pas de recherche torrents.
    """
    sigs = known_signatures if known_signatures is not None else signatures_for(target_path)
    matcher = Matcher(sigs, target_path)
    if not sigs and not matcher.target_real:
        return {"signatures": [], "torrents": [], "copies": []}

    idx = get_index(force=fresh_index)
    matched: Dict[str, str] = {}

    # 1. Hardlinks (même inode) et copies physiques (même taille + empreinte)
    for ino in matcher.inodes:
        for p in idx.by_inode.get(ino, []):
            matched[p] = "inode"
    sizes = list(matcher.by_size.keys())
    candidates: List[str] = [p for s in sizes for p in idx.by_size.get(s, [])]
    if matcher.hash_only:
        candidates += [p for ps in idx.by_size.values() for p in ps]
    for p in candidates:
        if p in matched:
            continue
        m = matcher.match(p)
        if m in ("inode", "hash"):
            matched[p] = m
    # la cible elle-même n'est pas une « copie »
    matched = {p: m for p, m in matched.items()
               if not matcher.inside_target(host_resolve(p)) and host_resolve(p) not in matcher.paths}

    # 2. Liens symboliques (cross-seed) vers la cible ou vers une copie trouvée
    real_targets = set(matcher.paths) | {host_resolve(p) for p in matched}
    for link, dest in idx.symlinks:
        real_dest = host_resolve(link)
        if real_dest in real_targets or matcher.inside_target(real_dest) or \
                any(real_dest.startswith(t + os.sep) for t in real_targets if os.path.isdir(t)):
            matched[link] = "symlink"

    # 3. Torrents
    matched_torrents = match_torrents(matcher, torrents) if torrents is not None else []

    copies = group_units(matched, protected_dirs(torrents or []), matcher)
    return {"signatures": sigs, "torrents": matched_torrents, "copies": copies}


def source_unit(file_path: str, torrents: Optional[List[Dict]] = None) -> str:
    """Pour une suppression directe (média absent de Radarr/Sonarr) : le dossier
    release si toutes ses vidéos sont ce média, sinon le fichier seul."""
    if not file_path or not os.path.exists(file_path):
        return ""
    if os.path.isdir(file_path):
        return file_path
    prot = protected_dirs(torrents or [])
    parent = os.path.dirname(file_path)
    if os.path.normpath(parent) in prot:
        return file_path
    if _all_videos_match(parent, {os.path.normpath(file_path)}):
        return parent
    return file_path
