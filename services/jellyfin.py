from typing import Any, Dict, List, Optional
import requests


class JellyfinClient:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        # Jellyfin 10.11+/12 refuse ?api_key= et X-Emby-Token (401) :
        # seul l'en-tête Authorization MediaBrowser est accepté.
        self.session.headers["Authorization"] = f'MediaBrowser Token="{api_key}"'

    def _url(self, endpoint: str) -> str:
        return f"{self.base_url}{endpoint}"

    def _get(self, endpoint: str, params: Optional[Dict] = None) -> Any:
        r = self.session.get(self._url(endpoint), params=params, timeout=30)
        r.raise_for_status()
        return r.json()

    def _post(self, endpoint: str, data: Optional[Dict] = None) -> Any:
        r = self.session.post(self._url(endpoint), json=data, timeout=30)
        r.raise_for_status()
        return r.json() if r.content else {}

    def _delete(self, endpoint: str) -> bool:
        r = self.session.delete(self._url(endpoint), timeout=30)
        r.raise_for_status()
        return True

    # ── Utilisateurs ──────────────────────────────────────────────────────────

    def get_users(self) -> List[Dict]:
        return self._get("/Users")

    def get_user(self, user_id: str) -> Dict:
        return self._get(f"/Users/{user_id}")

    # ── Items ─────────────────────────────────────────────────────────────────

    def get_item(self, item_id: str, user_id: Optional[str] = None) -> Dict:
        if user_id:
            return self._get(f"/Users/{user_id}/Items/{item_id}")
        return self._get(f"/Items/{item_id}")

    def get_all_movies(self, user_id: str) -> List[Dict]:
        result = self._get(f"/Users/{user_id}/Items", params={
            "IncludeItemTypes": "Movie",
            "Recursive": True,
            "Fields": "Path,ProviderIds,UserData",
        })
        return result.get("Items", [])

    def get_all_series(self, user_id: str) -> List[Dict]:
        result = self._get(f"/Users/{user_id}/Items", params={
            "IncludeItemTypes": "Series",
            "Recursive": True,
            "Fields": "Path,ProviderIds,UserData",
        })
        return result.get("Items", [])

    def get_episodes(self, series_id: str, user_id: str) -> List[Dict]:
        result = self._get(f"/Shows/{series_id}/Episodes", params={
            "UserId": user_id,
            "Fields": "Path,ProviderIds,UserData",
        })
        return result.get("Items", [])

    # ── Données de visionnage ─────────────────────────────────────────────────

    def get_user_data(self, user_id: str, item_id: str) -> Dict:
        item = self._get(f"/Users/{user_id}/Items/{item_id}")
        return item.get("UserData", {})

    def get_play_percentage(self, user_id: str, item_id: str) -> float:
        """Retourne le pourcentage visionné (0-100)."""
        user_data = self.get_user_data(user_id, item_id)
        return user_data.get("PlayedPercentage") or 0.0

    def is_played(self, user_id: str, item_id: str) -> bool:
        user_data = self.get_user_data(user_id, item_id)
        return user_data.get("Played", False)

    def get_watched_items(self, user_id: str, media_type: Optional[str] = None) -> List[Dict]:
        """
        Retourne tous les items regardés d'un utilisateur.
        media_type : "Movie", "Episode", ou None pour tout.
        """
        params: Dict = {
            "IsPlayed": True,
            "Recursive": True,
            "Fields": "Path,ProviderIds,UserData",
        }
        if media_type:
            params["IncludeItemTypes"] = media_type
        result = self._get(f"/Users/{user_id}/Items", params=params)
        return result.get("Items", [])

    def get_recently_played(self, user_id: str, limit: int = 20) -> List[Dict]:
        result = self._get(f"/Users/{user_id}/Items", params={
            "Limit": limit,
            "Fields": "Path,ProviderIds,UserData",
            "Filters": "IsPlayed",
            "SortBy": "DatePlayed",
            "SortOrder": "Descending",
            "Recursive": True,
            "IncludeItemTypes": "Movie,Episode",
        })
        return result.get("Items", [])

    def get_watch_status_all_users(self, item_id: str) -> Dict[str, Dict]:
        """
        Retourne le statut de visionnage pour chaque user.
        { user_id: { "name": str, "played": bool, "percentage": float } }
        """
        result: Dict[str, Dict] = {}
        for user in self.get_users():
            uid = user["Id"]
            user_data = self.get_user_data(uid, item_id)
            result[uid] = {
                "name": user["Name"],
                "played": user_data.get("Played", False),
                "percentage": user_data.get("PlayedPercentage") or 0.0,
            }
        return result

    # ── Bibliothèque ──────────────────────────────────────────────────────────

    def refresh_library(self) -> bool:
        self._post("/Library/Refresh")
        return True

    def delete_item(self, item_id: str) -> bool:
        return self._delete(f"/Items/{item_id}")

    # ── Suggestions de nettoyage ─────────────────────────────────────────────

    def get_all_items_metadata(self, user_id: str, media_type: str, limit: int = 500) -> List[Dict]:
        """Tous les items (vus ou non) avec métadonnées, triés par date d'ajout."""
        result = self._get(f"/Users/{user_id}/Items", params={
            "IncludeItemTypes": media_type,
            "Recursive": True,
            "Fields": "Path,ProviderIds,UserData,DateCreated,OriginalTitle,ChildCount,RecursiveItemCount",
            "SortBy": "DateCreated",
            "SortOrder": "Ascending",
            "Limit": limit,
        })
        return result.get("Items", [])

    def get_all_episodes_with_series(self, user_id: str, limit: int = 10000) -> List[Dict]:
        """Tous les épisodes avec chemin et métadonnées de série (pour détection orphelins)."""
        result = self._get(f"/Users/{user_id}/Items", params={
            "IncludeItemTypes": "Episode",
            "Recursive": True,
            "Fields": "Path,SeriesId,SeriesName,ParentIndexNumber,UserData",
            "Limit": limit,
        })
        return result.get("Items", [])

    def get_played_item_ids(self, user_id: str, media_type: str) -> set:
        """
        Retourne les IDs des items regardés par un utilisateur.
        Pour les épisodes, inclut aussi les SeriesId (pour savoir quelles séries ont été vues).
        """
        result = self._get(f"/Users/{user_id}/Items", params={
            "IsPlayed": True,
            "Recursive": True,
            "Fields": "SeriesId",
            "IncludeItemTypes": media_type,
        })
        ids: set = set()
        for item in result.get("Items", []):
            ids.add(item["Id"])
            if media_type == "Episode" and item.get("SeriesId"):
                ids.add(item["SeriesId"])
        return ids

    # ── Favoris ───────────────────────────────────────────────────────────────

    def is_favorite(self, user_id: str, item_id: str) -> bool:
        user_data = self.get_user_data(user_id, item_id)
        return user_data.get("IsFavorite", False)

    def remove_favorite(self, user_id: str, item_id: str) -> bool:
        return self._delete(f"/Users/{user_id}/FavoriteItems/{item_id}")

    def get_favorite_items(self, user_id: str) -> List[Dict]:
        """Films/séries mis en favori par cet utilisateur."""
        result = self._get(f"/Users/{user_id}/Items", params={
            "Filters": "IsFavorite",
            "IncludeItemTypes": "Movie,Series",
            "Recursive": True,
        })
        return result.get("Items", [])

    def is_favorite_any_user(self, item_id: str) -> bool:
        """Retourne True si au moins un utilisateur a mis l'item en favori."""
        for user in self.get_users():
            try:
                if self.is_favorite(user["Id"], item_id):
                    return True
            except Exception:
                continue
        return False

    def get_watched_with_details(self, user_id: str, media_type: Optional[str] = None, limit: int = 100) -> List[Dict]:
        """
        Retourne les items regardés avec toutes les infos nécessaires.
        Inclut : ProviderIds, Path, UserData (IsFavorite, PlayedPercentage, LastPlayedDate).
        """
        params: Dict = {
            "IsPlayed": True,
            "Recursive": True,
            "Fields": "Path,ProviderIds,UserData,SeriesName,ParentIndexNumber,IndexNumber,SeriesId",
            "SortBy": "DatePlayed",
            "SortOrder": "Descending",
            "Limit": limit,
        }
        if media_type:
            params["IncludeItemTypes"] = media_type
        else:
            params["IncludeItemTypes"] = "Movie,Episode"
        result = self._get(f"/Users/{user_id}/Items", params=params)
        return result.get("Items", [])

    def search_items(self, user_id: str, query: str, limit: int = 20) -> List[Dict]:
        """Recherche films et séries par titre (correspondance partielle)."""
        result = self._get(f"/Users/{user_id}/Items", params={
            "SearchTerm": query,
            "IncludeItemTypes": "Movie,Series",
            "Recursive": True,
            "Fields": "UserData",
            "Limit": limit,
        })
        return result.get("Items", [])

    # ── Santé ─────────────────────────────────────────────────────────────────

    def ping(self) -> bool:
        try:
            self._get("/System/Info/Public")
            return True
        except Exception:
            return False
