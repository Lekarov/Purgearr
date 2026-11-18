from typing import Dict, List, Optional
from .base import BaseAPIClient


class SonarrClient(BaseAPIClient):

    def get_all_series(self) -> List[Dict]:
        return self.get("/api/v3/series")

    def get_series(self, series_id: int) -> Dict:
        return self.get(f"/api/v3/series/{series_id}")

    def get_episodes(self, series_id: int) -> List[Dict]:
        return self.get("/api/v3/episode", params={"seriesId": series_id})

    def get_episode(self, episode_id: int) -> Dict:
        return self.get(f"/api/v3/episode/{episode_id}")

    def get_episode_files(self, series_id: int) -> List[Dict]:
        return self.get("/api/v3/episodefile", params={"seriesId": series_id})

    def find_by_title(self, title: str) -> Optional[Dict]:
        title_lower = title.lower()
        for series in self.get_all_series():
            if series.get("title", "").lower() == title_lower:
                return series
        return None

    def find_by_tvdb_id(self, tvdb_id: int) -> Optional[Dict]:
        for series in self.get_all_series():
            if series.get("tvdbId") == tvdb_id:
                return series
        return None

    def find_by_path(self, host_path: str) -> Optional[Dict]:
        """Série dont le dossier contient (ou est) le chemin hôte."""
        from core.locator import to_container
        wanted = {p.rstrip("/") for p in to_container(host_path, ["/media/série", "/downloads"])}
        for series in self.get_all_series():
            sp = (series.get("path") or "").rstrip("/")
            if sp and any(w == sp or w.startswith(sp + "/") for w in wanted):
                return series
        return None

    def unmonitor_series(self, series_id: int) -> Dict:
        series = self.get_series(series_id)
        series["monitored"] = False
        return self.put(f"/api/v3/series/{series_id}", series)

    def unmonitor_episode(self, episode_id: int) -> Dict:
        episode = self.get_episode(episode_id)
        episode["monitored"] = False
        return self.put(f"/api/v3/episode/{episode_id}", episode)

    def delete_episode_file(self, episode_file_id: int) -> bool:
        return super().delete(f"/api/v3/episodefile/{episode_file_id}")

    def delete_series(self, series_id: int, delete_files: bool = True, add_exclusion: bool = True) -> bool:
        """Supprime la série complète, ses fichiers, et l'ajoute à la liste d'exclusion."""
        return super().delete(
            f"/api/v3/series/{series_id}",
            params={"deleteFiles": delete_files, "addImportListExclusion": add_exclusion},
        )

    def all_episodes_watched(self, series_id: int, watched_episode_ids: List[int]) -> bool:
        """Vérifie si tous les épisodes d'une série ont été regardés."""
        episodes = self.get_episodes(series_id)
        aired = [ep for ep in episodes if ep.get("hasFile")]
        if not aired:
            return False
        return all(ep["id"] in watched_episode_ids for ep in aired)

    def ping(self) -> bool:
        try:
            self.get("/api/v3/system/status")
            return True
        except Exception:
            return False
