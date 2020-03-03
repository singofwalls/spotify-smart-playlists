"""Create dynamic Spotify playlists using Playlist objects."""

import spotipy
from spotipy import util

import json

CREDS_FILE = "creds.json"

SMART_PLAYLISTS = {"FAVORITE INSTRUMENTALS": ("07fdYUs00cdxyoXt7x23i1", "")}
TRACK_FIELDS = ("id", "name", "is_local")
PLAYLIST_FIELDS = ("id", "name")


def main():
    """Create default playlists."""
    creds = get_credentials()
    spotify = get_spotify(creds)

    fav_tracks = get_all_songs(spotify)
    playlists = get_playlists(spotify)

    bands = Playlist("Bands")
    bands.find_tracks(spotify)
    # fav_bands = Playlist()


class Playlist:
    """Maintain a list of tracks and allow for easy updating of the list."""

    def __init__(self, name: str, id: str = None, spotify: spotipy.Spotify = None):
        super(Playlist, self).__init__()
        self.name = name
        self.publish_name = None
        self.tracks: set = set()
        self.id = id
        if self.id is not None:
            self._populate(spotify, self.id)

    def __add__(self, other):
        """Add tracks from both playlists."""
        new = self.copy(" plus " + other.name)
        new.tracks += other.tracks
        return new

    def __sub__(self, other):
        """Remove tracks in right playlist from left playlist."""
        new = self.copy(" minus " + other.name)
        new.tracks -= other.tracks
        return new

    def __and__(self, other):
        """Intersect tracks of both playlists."""
        new = self.copy(" and " + other.name)
        new.tracks &= other.tracks
        return new

    def __or__(self, other):
        """Combine tracks of both playlists."""
        new = self.copy(" or " + other.name)
        new.tracks |= other.tracks
        return new

    def copy(self, name_addition=None):
        """Copy tracks into new playlist."""
        name = self.name if name_addition is None else f"({self.name}){name_addition}"
        new = Playlist(name)
        new.publish_name = self.publish_name
        new.tracks = self.tracks
        return new

    def _populate(self, spotify: spotipy.Spotify, id):
        """Populate the playlist with tracks from the playlist id."""
        self.tracks = set(get_playlist_tracks(spotify, id))

    def find_tracks(self, spotify: spotipy.Spotify):
        """Update tracks with tracks from matching playlist name in Spotify."""
        playlists = get_playlists(spotify)
        pass

    def publish(self, spotify: spotipy.Spotify, playlists):
        """Publish the playlist to spotify."""
        name = self.name if self.publish_name is None else self.publish_name
        name_exists = False
        # spotify.user_playlist_create


def get_playlist_tracks(spotify: spotipy.Spotify, playlist_id):
    """Load all songs from the given playlist."""
    # 50 is max limit for api
    result = spotify.user_playlist_tracks(spotify, playlist_id)
    results = result["items"]
    while result["next"]:
        result = spotify.next(result)
        results.extend(result["items"])

    return select_fields(results)


def get_all_songs(spotify: spotipy.Spotify):
    """Load all songs from the users saved songs."""
    # 50 is max limit for api
    result = spotify.current_user_saved_tracks(limit=50)
    results = result["items"]
    while result["next"]:
        result = spotify.next(result)
        results.extend(result["items"])

    return select_fields(results)


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


def select_fields(tracks, root="track", fields=TRACK_FIELDS):
    """Convert api results to dict."""
    return [{k: t[root][k] for k in fields} for t in tracks]


def get_playlists(spotify: spotipy.Spotify):
    """Get a list of user playlist names and ids."""
    results = spotify.user_playlists("spotify")
    playlists = []
    while results:
        for i, playlist in enumerate(results["items"]):
            playlists.append((playlist["name"], playlist["id"]))
        if results["next"]:
            results = spotify.next(results)
        else:
            results = None

    return select_fields(playlists, "", PLAYLIST_FIELDS)


if __name__ == "__main__":
    main()
