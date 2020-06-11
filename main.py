"""Create dynamic Spotify playlists using Playlist objects."""
from typing import Iterable, List, Mapping, Dict, Optional

import spotipy
from spotipy import util

import json
import operator
from collections import namedtuple


CREDS_FILE = "creds.json"

TRACK_FIELDS = ("id", "name", "is_local")
PLAYLIST_FIELDS = ("id", "name")

API_LIMIT = 50


def main():
    """Create default playlists."""
    creds = get_credentials()
    spotify = get_spotify(creds)

    saved_songs = get_saved_songs(spotify)
    p_saved_songs = Playlist(spotify, "Liked Songs")
    p_saved_songs += saved_songs

    p_instrumental = Playlist(spotify, "All Instrumental", populate=True)

    p_saved_bands = Playlist(spotify, "Liked Songs - Bands", populate=True)
    remove_nonlocal(p_saved_bands)
    p_saved_bands += p_saved_songs - p_instrumental
    p_saved_bands.name = "Liked Songs - Bands"
    p_saved_bands.publish()

    p_saved_instrumentals = Playlist(
        spotify, "Liked Songs - Instrumentals", populate=True
    )
    remove_nonlocal(p_saved_instrumentals)
    p_saved_instrumentals += p_instrumental & saved_songs
    p_saved_instrumentals.name = "Liked Songs - Instrumentals"
    p_saved_instrumentals.publish()

    p_save_songs_all = Playlist(spotify, "Liked Songs - All", populate=True)
    remove_nonlocal(p_save_songs_all)
    p_save_songs_all += p_saved_instrumentals + p_saved_bands
    p_save_songs_all.name = "Liked Songs - All"
    p_save_songs_all.publish()


Track = namedtuple("Track", TRACK_FIELDS)


class Playlist:
    """Maintain a list of tracks and allow for easy updating of the list."""

    def __init__(
        self,
        spotify: spotipy.Spotify,
        name: str,
        id_: str = None,
        populate: bool = False,
    ):
        self.spotify = spotify
        self.name = name
        self.publish_name = None
        self.tracks: set = set()
        self.id = id_
        if self.id is None:
            self._find_id()
        if self.id is not None and populate:
            self._populate()

    def __add__(self, other):
        """Add tracks from both playlists or tracklist."""
        # Set addition is really union "or"
        return self._membership_op(other, "plus", operator.or_)

    def __sub__(self, other):
        """Remove tracks in right playlist from left playlist."""
        return self._membership_op(other, "minus", operator.sub)

    def __and__(self, other):
        """Intersect tracks of both playlists."""
        return self._membership_op(other, "and", operator.and_)

    def __or__(self, other):
        """Combine tracks of both playlists."""
        return self._membership_op(other, "or", operator.or_)

    def __iadd__(self, other):
        """Add tracks from both playlists or tracklist inplace."""
        # Set addition is really union "or"
        return self._membership_op(other, "plus", operator.or_, True)

    def __isub__(self, other):
        """Remove tracks in right playlist from left playlist inplace."""
        return self._membership_op(other, "minus", operator.sub, True)

    def __iand__(self, other):
        """Intersect tracks of both playlists inplace."""
        return self._membership_op(other, "and", operator.and_, True)

    def __ior__(self, other):
        """Combine tracks of both playlists inplace."""
        return self._membership_op(other, "or", operator.or_, True)

    def _membership_op(self, other, name, operation, inplace=False):
        """Perform a membership operation on the Playlist."""
        new = self
        if isinstance(other, Playlist):
            if inplace:
                new = self.copy(f" {name} {other.name}")
            new.tracks = operation(new.tracks, other.tracks)
        else:  # Could check for inplace here to stop non-augmented operations from accepting types other than Playlist
            if inplace:
                new = self.copy()
            try:
                tracks = set(other)
            except TypeError:
                return NotImplemented
            else:
                new.tracks = operation(new.tracks, tracks)
        return new

    def __bool__(self):
        """Determine truthiness of Playlist."""
        return bool(self.tracks)

    def __len__(self):
        """Get the length of the playlist."""
        return len(self.tracks)

    def __iter__(self):
        """Iterate the playlist tracks."""
        return iter(self.tracks)

    def copy(self, name_addition=None):
        """Copy tracks into new playlist."""
        name = self.name if name_addition is None else f"({self.name}){name_addition}"
        new = Playlist(self.spotify, name, self.id, populate=False)
        new.tracks = self.tracks
        return new

    def _populate(self):
        """Populate the playlist with tracks from the playlist id."""
        self.tracks = set(get_playlist_tracks(self.spotify, self.id))

    def _find_id(self):
        """Update id with id from matching playlist name in Spotify."""
        playlists = get_playlists(self.spotify)
        name_map = {p["name"]: p["id"] for p in playlists}
        if self.name in name_map:
            self.id = name_map[self.name]

    def publish(
        self,
        name: str = None,
        always_new: bool = False,
        public: bool = False,
        desc: str = "",
    ):
        """Publish the playlist to spotify."""

        def get_track_ids(tracks: Iterable[Track]):
            """Get the track ids from Track objects."""
            return set(t.id for t in tracks if not t.is_local)

        def get_track_name(
            track_id: str, search_list: Iterable[Track]
        ) -> Optional[str]:
            """Find a track's name from id in a list of tracks."""
            for track in search_list:
                if track.id == track_id:
                    return track.name
            return None

        name = self.name if name is None else name

        user = self.spotify.me()["id"]

        if always_new or self.id is None:
            playlist = self.spotify.user_playlist_create(user, name, public, desc)
            self.id = playlist["id"]

        tracks_online = get_playlist_tracks(self.spotify, self.id)
        tracks_all = list(self.tracks) + tracks_online

        track_ids_current = get_track_ids(tracks_online)
        track_ids_all = get_track_ids(self.tracks)

        track_ids_new = list(track_ids_all - track_ids_current)
        tracks_ids_old = list(track_ids_current - track_ids_all)

        track_names_old = [get_track_name(id_, tracks_all) for id_ in tracks_ids_old]
        print(f"Removing tracks from {name}: {track_names_old}")

        for i in range(0, len(tracks_ids_old), API_LIMIT):
            self.spotify.user_playlist_remove_all_occurrences_of_tracks(
                user, self.id, tracks_ids_old[i : i + API_LIMIT]
            )

        track_names_new = [get_track_name(id_, tracks_all) for id_ in track_ids_new]
        print(f"Adding tracks to {name}: {track_names_new}")
        for i in range(0, len(track_ids_new), API_LIMIT):
            self.spotify.user_playlist_add_tracks(
                user, self.id, track_ids_new[i : i + API_LIMIT]
            )

        print("Done.\n")


def get_playlist_tracks(spotify: spotipy.Spotify, playlist_id: str) -> List[Track]:
    """Load all songs from the given playlist."""
    result = spotify.playlist_tracks(playlist_id)
    results = result["items"]
    while result["next"]:
        result = spotify.next(result)
        results.extend(result["items"])

    return dicts_to_tracks(select_fields(results, "track"))


def get_saved_songs(spotify: spotipy.Spotify):
    """Load all songs from the users saved songs."""
    songs = get_all(spotify, spotify.current_user_saved_tracks(limit=API_LIMIT))

    return dicts_to_tracks(select_fields(songs, "track"))


def get_playlists(spotify: spotipy.Spotify):
    """Get a list of user playlist names and ids."""
    playlists = get_all(spotify, spotify.current_user_playlists())

    return select_fields(playlists, fields=PLAYLIST_FIELDS)


def get_all(spotify: spotipy.Spotify, results: dict):
    """Grab more results until none remain."""
    items = results["items"]
    while results["next"]:
        results = spotify.next(results)
        items.extend(results["items"])

    return items


def get_credentials():
    """Load the credentials from the json."""
    with open(CREDS_FILE) as f:
        creds = json.load(f)

    return creds


def get_spotify(s_creds):
    """Get the spotify object from which to make requests."""
    # Authorize Spotify
    token = util.prompt_for_user_token(
        s_creds["username"],
        s_creds["scopes"],
        s_creds["client_id"],
        s_creds["client_secret"],
        s_creds["redirect_uri"],
    )

    return spotipy.Spotify(auth=token)


def select_fields(items, root=None, fields=TRACK_FIELDS) -> List[Dict]:
    """Convert api results to dicts."""
    return [
        {k: t[root][k] if root is not None else t[k] for k in fields} for t in items
    ]


def dicts_to_tracks(dicts: List[Mapping]) -> List[Track]:
    """Convert api result dicts to tracks."""
    return [Track(*(d[field] for field in TRACK_FIELDS)) for d in dicts]


def remove_nonlocal(playlist: Playlist):
    """Remove all nonlocal tracks from the playlist in-place."""
    playlist -= [track for track in playlist if not track.is_local]
    return playlist


if __name__ == "__main__":
    main()
