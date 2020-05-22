"""Create dynamic Spotify playlists using Playlist objects."""

import spotipy
from spotipy import util

import json
import operator
from functools import reduce
from collections import namedtuple


CREDS_FILE = "creds.json"

TRACK_FIELDS = ("id", "name", "is_local")
PLAYLIST_FIELDS = ("id", "name")


def main():
    """Create default playlists."""
    creds = get_credentials()
    spotify = get_spotify(creds)

    saved_songs = get_saved_songs(spotify)
    p_saved_songs = Playlist(spotify, "Liked Songs")
    p_saved_songs += saved_songs

    p_instrumental = Playlist(spotify, "All Instrumental", populate=True)

    p_saved_bands = Playlist(spotify, "Liked Songs - Bands", populate=True)
    p_saved_bands -= [track for track in p_saved_bands if not track.is_local]
    p_saved_bands += p_saved_songs - p_instrumental
    p_saved_bands.name = "Liked Songs - Bands"
    p_saved_bands.publish()

    p_saved_instrumentals = Playlist(spotify, "Liked Songs - Instrumentals", populate=True)
    p_saved_instrumentals -= [track for track in p_saved_instrumentals if not track.is_local]
    p_saved_instrumentals += p_instrumental & saved_songs
    p_saved_instrumentals.name = "Liked Songs - Instrumentals"
    p_saved_instrumentals.publish()
    
    p_save_songs_all = Playlist(spotify, "Liked Songs - All", populate=True)
    p_save_songs_all -= [track for track in p_save_songs_all if not track.is_local]
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
        id: str = None,
        populate: bool = False,
    ):
        self.spotify = spotify
        self.name = name
        self.publish_name = None
        self.tracks: set = set()
        self.id = id
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

    def _membership_op(self, other, name, operation):
        """Perform a membership operation on the Playlist."""
        if type(other) == Playlist:
            new = self.copy(f" {name} {other.name}")
            new.tracks = operation(new.tracks, other.tracks)
        elif type(other) in [list, set]:
            new = self.copy()
            new.tracks = operation(new.tracks, set(other))
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

    def __next__(self):
        """Get next track in iterable."""
        yield from self

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

        def get_track_ids(tracks):
            """Get the track ids from Track objects."""
            non_local = filter(lambda t: not t[t._fields.index("is_local")], tracks)
            return set(map(lambda t: t[t._fields.index("id")], non_local))

        name = self.name if name is None else name

        user = self.spotify.me()["id"]

        if always_new or self.id is None:
            playlist = self.spotify.user_playlist_create(user, name, public, desc)
            self.id = playlist["id"]

        all_tracks = get_track_ids(self.tracks)
        current_tracks = get_track_ids(get_playlist_tracks(self.spotify, self.id))
        new_tracks = list(all_tracks - current_tracks)
        old_tracks = list(current_tracks - all_tracks)

        for i in range(0, len(old_tracks), 50):
            self.spotify.user_playlist_remove_all_occurrences_of_tracks(
                user, self.id, old_tracks[i : i + 50]
            )
        for i in range(0, len(new_tracks), 50):
            self.spotify.user_playlist_add_tracks(user, self.id, new_tracks[i : i + 50])


def get_playlist_tracks(spotify: spotipy.Spotify, playlist_id):
    """Load all songs from the given playlist."""
    # 50 is max limit for api
    result = spotify.user_playlist_tracks(None, playlist_id)
    results = result["items"]
    while result["next"]:
        result = spotify.next(result)
        results.extend(result["items"])

    return dicts_to_tracks(select_fields(results, "track"))


def get_saved_songs(spotify: spotipy.Spotify):
    """Load all songs from the users saved songs."""
    # 50 is max limit for api
    songs = get_all(spotify, spotify.current_user_saved_tracks(limit=50))

    return dicts_to_tracks(select_fields(songs, "track"))


def get_playlists(spotify: spotipy.Spotify):
    """Get a list of user playlist names and ids."""
    playlists = get_all(spotify, spotify.current_user_playlists())

    return select_fields(playlists, None, PLAYLIST_FIELDS)


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


def select_fields(items, root=None, fields=TRACK_FIELDS):
    """Convert api results to dicts."""
    return [
        {k: t[root][k] if root is not None else t[k] for k in fields} for t in items
    ]


def dicts_to_tracks(dicts):
    """Convert api result dicts to tracks."""
    return [Track(*(map(d.get, TRACK_FIELDS))) for d in dicts]


if __name__ == "__main__":
    main()
