from typing import Dict, List, Optional
from .base import BaseAPIClient


class RadarrClient(BaseAPIClient):

    def get_all_movies(self) -> List[Dict]:
        return self.get("/api/v3/movie")

    def get_movie(self, movie_id: int) -> Dict:
        return self.get(f"/api/v3/movie/{movie_id}")

    def get_movie_files(self, movie_id: int) -> List[Dict]:
        return self.get("/api/v3/moviefile", params={"movieId": movie_id})

    def find_by_title(self, title: str) -> Optional[Dict]:
        title_lower = title.lower()
        for movie in self.get_all_movies():
            if movie.get("title", "").lower() == title_lower:
                return movie
        return None

    def find_by_tmdb_id(self, tmdb_id: int) -> Optional[Dict]:
        for movie in self.get_all_movies():
            if movie.get("tmdbId") == tmdb_id:
                return movie
        return None

    def find_by_imdb_id(self, imdb_id: str) -> Optional[Dict]:
        for movie in self.get_all_movies():
            if movie.get("imdbId") == imdb_id:
                return movie
        return None

    def find_by_path(self, host_path: str) -> Optional[Dict]:
        """Film dont le fichier (ou le dossier) correspond exactement au chemin
        hôte — Radarr voit /media/film, Purgearr voit le chemin réel du NAS."""
        from core.locator import to_container
        wanted = {p.rstrip("/") for p in to_container(host_path, ["/media/film", "/downloads"])}
        for movie in self.get_all_movies():
            mf = (movie.get("movieFile") or {}).get("path", "")
            if mf and mf.rstrip("/") in wanted:
                return movie
            mp = (movie.get("path") or "").rstrip("/")
            if mp and mp in wanted:
                return movie
        return None

    def unmonitor(self, movie_id: int) -> Dict:
        movie = self.get_movie(movie_id)
        movie["monitored"] = False
        return self.put(f"/api/v3/movie/{movie_id}", movie)

    def delete(self, movie_id: int, delete_files: bool = True, add_exclusion: bool = True) -> bool:
        """Supprime le film de Radarr, ses fichiers, et l'ajoute à la liste d'exclusion."""
        return super().delete(
            f"/api/v3/movie/{movie_id}",
            params={"deleteFiles": delete_files, "addImportExclusion": add_exclusion},
        )

    def ping(self) -> bool:
        try:
            self.get("/api/v3/system/status")
            return True
        except Exception:
            return False
