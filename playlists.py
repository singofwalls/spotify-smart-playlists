"""Create dynamic Spotify playlists using Playlist objects."""
import warnings
from collections import namedtuple
from typing import Iterable, List, Mapping, Dict, Optional, Sequence, OrderedDict

import spotipy
from spotipy import util

import json
import reprlib
from itertools import chain

# TODO: TQDM
# TODO: Remove duplicates
# TODO: Find latest ids for tracks on Spotify


CREDS_FILE = "creds.json"

TRACK_ROOT = ("track",)
TRACK_FIELDS = {
    "id": ("id",),
    "name": ("name",),
    "is_local": ("is_local",),
    "duration_ms": ("duration_ms",),
    "album": ("album", "name"),
    "artist": ("artists", 0, "name"),
}
PLAYLIST_FIELDS = {"id": ("id",), "name": ("name",)}


API_LIMIT = 50


class Track:
    """Maintain fields related to a single track in a playlist."""

    def __init__(self, *args, **kwargs):
        # Hardcode attributes so intellisense doesn't go mad
        self.id = None
        self.name = None
        self.is_local = None
        self.duration_ms = None
        self.album = None
        self.artist = None

        self.__dict__ = {key: None for key in TRACK_FIELDS.keys()}
        self.__dict__.update(
            {key: value for key, value in zip(TRACK_FIELDS.keys(), args)}
        )
        self.__dict__.update(kwargs)

        self.__slots__ = tuple(TRACK_FIELDS.keys())

    def __hash__(self):
        if not self.is_local:
            return hash(self.id)
        return hash(tuple(self.__dict__.items()))

    def __repr__(self):
        return f"{self.__class__.__name__}({', '.join(f'{key}={repr(value)}' for key, value in self.__dict__.items() if not key.startswith('_'))})"

    def __eq__(self, other):
        if not self.is_local:
            return self.id == other.id
        return self.__dict__ == other.__dict__


class Playlist:
    """Maintain a list of tracks and allow for easy updating of the list."""

    def __init__(
        self,
        spotify: spotipy.Spotify,
        name: str,
        id_: str = None,
        populate: bool = False,
        allow_duplicates: bool = False,
    ):
        self.spotify = spotify
        self.name = name
        self.tracks: list = []
        self.id = id_
        self.allow_duplicates = allow_duplicates
        if self.id is None:
            self._find_id()
        if self.id is not None and populate:
            self._populate()

    def __repr__(self):
        tracks = [track.name for track in self.tracks]
        return f"Playlist(name={self.name}, tracks={reprlib.repr(tracks)})"

    def __add__(self, other):
        """Add tracks from both playlists or tracklist."""
        # Set addition is really union "or"
        return self._membership_op(other, lambda s, o: list(chain(s, o)))

    def __sub__(self, other):
        """Remove tracks in right playlist from left playlist."""
        return self._membership_op(other, sub_lists)

    def __and__(self, other):
        """Intersect tracks of both playlists."""
        return self._membership_op(other, intersect_lists)

    def __or__(self, other):
        """Combine tracks of both playlists."""
        return self.__add__(other)

    def __iadd__(self, other):
        """Add tracks from both playlists or tracklist inplace."""
        # Set addition is really union "or"
        return self._membership_op(other, lambda s, o: list(chain(s, o)), True)

    def __isub__(self, other):
        """Remove tracks in right playlist from left playlist inplace."""
        return self._membership_op(other, sub_lists, True)

    def __iand__(self, other):
        """Intersect tracks of both playlists inplace."""
        return self._membership_op(other, intersect_lists, True)

    def __ior__(self, other):
        """Combine tracks of both playlists inplace."""
        return self.__iadd__(other)

    def _membership_op(self, other, operation, inplace=False):
        """Perform a membership operation on the Playlist."""
        if inplace:
            new = self
        else:
            new = self.copy()

        if isinstance(other, Playlist):
            new.tracks = operation(new.tracks, other.tracks)
        elif isinstance(other, Track):
            new.tracks = operation(new.tracks, [other])
        else:  # Could check for inplace here to stop non-augmented operations from accepting types other than Playlist
            try:
                tracks = list(other)
            except TypeError:
                return NotImplemented
            new.tracks = operation(new.tracks, tracks)
        if not self.allow_duplicates:
            new.tracks = list(OrderedDict.fromkeys(new.tracks))
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

    def __getitem__(self, index):
        return tuple(self.tracks)[index]

    def copy(self):
        """Copy tracks into new playlist."""
        new = Playlist(self.spotify, self.name, self.id, populate=False)
        new.tracks = self.tracks
        return new

    def _populate(self):
        """Populate the playlist with tracks from the playlist id."""
        self.tracks = list(get_playlist_tracks(self.spotify, self.id))

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

        def get_track_name(
            track_id: str, search_list: Iterable[Track]
        ) -> Optional[str]:
            """Find a track's name from id in a list of tracks."""
            for t in search_list:
                if t.id == track_id:
                    return t.name
            return None

        TrackPos = namedtuple("TrackPos", "pos id")

        name = self.name if name is None else name
        user = self.spotify.me()["id"]

        if always_new or self.id is None:
            playlist = self.spotify.user_playlist_create(user, name, public, desc)
            self.id = playlist["id"]

        tracks_online = get_playlist_tracks(self.spotify, self.id)

        # Move, remove, and add tracks to correct positions
        new_tracks = []
        online_index = 0
        added = 0
        for current_index in range(len(self.tracks)):
            if (
                online_index < len(tracks_online)
                and self.tracks[current_index] == tracks_online[online_index]
            ):
                # Track already in position
                online_index += 1
                continue

            # Track missing or in wrong position
            track = self.tracks[current_index]
            if track.is_local:
                # Only move local tracks. Otherwise, batch add at end
                if track in tracks_online[online_index:]:
                    # Move track to correct position
                    shifted_track_index = tracks_online.index(track, online_index)
                    print(
                        f"Moving track in {self.name}: {track.name} from {shifted_track_index} to {online_index}"
                    )
                    self.spotify.user_playlist_reorder_tracks(
                        user, self.id, shifted_track_index, online_index
                    )
                    tracks_online.insert(
                        online_index, tracks_online.pop(shifted_track_index)
                    )
                    online_index += 1
                else:
                    warnings.warn(
                        f"No local file for {track.name} available in online playlist {self.name} to move to spot {online_index+1}"
                    )
            else:
                # Track missing from playlist, record position to insert into later
                new_tracks.append(TrackPos(online_index + added, track.id))
                added += 1

        # Remove extra tracks at end which are in wrong place
        print(
            f"Removing from {self.name}: ",
            [t.name for t in tracks_online[online_index:]],
        )
        while online_index < len(tracks_online):
            tracks = tracks_online[online_index : online_index + API_LIMIT]
            extra_tracks = [
                {"uri": track.id, "positions": [online_index + pos]}
                for pos, track in enumerate(tracks)
                if track.id is not None
            ]
            for i in range(online_index, online_index + API_LIMIT):
                if online_index < len(tracks_online):
                    tracks_online.pop(online_index)
            self.spotify.user_playlist_remove_specific_occurrences_of_tracks(
                user, self.id, extra_tracks
            )

        # Insert missing tracks
        tracks = []
        while new_tracks:
            # Create run of sequential tracks
            while not tracks or (
                new_tracks
                and new_tracks[0].pos == tracks[-1].pos + 1
                and len(tracks) < API_LIMIT
            ):
                tracks.append(new_tracks.pop(0))
            print(
                f"Adding to {self.name}: ",
                [(get_track_name(t.id, self.tracks), t.pos) for t in tracks],
            )
            self.spotify.user_playlist_add_tracks(
                user,
                self.id,
                [track.id for track in tracks],
                tracks[0].pos,  # All tracks must be added from a single pos
            )
            tracks = []

        print("Done.\n")


def sub_lists(own, other):
    """Remove tracks from own which are present in other inplace."""
    for track in other:
        if track in own:
            own.remove(track)
    return own


def intersect_lists(own, other):
    """Remove tracks from own which are not present in both lists inplace."""
    new = []
    for track in other:
        if track in own:
            new.append(track)
    own.clear()
    own.extend(new)
    return own


def get_playlist_tracks(spotify: spotipy.Spotify, playlist_id: str) -> List[Track]:
    """Load all songs from the given playlist."""
    results = get_all(spotify, spotify.playlist_tracks(playlist_id))

    return results_to_tracks(results)


def get_saved_songs(spotify: spotipy.Spotify):
    """Load all songs from the users saved songs."""
    results = get_all(spotify, spotify.current_user_saved_tracks(limit=API_LIMIT))

    return results_to_tracks(results)


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


def select_fields(
    items: Iterable[Mapping],
    root: Optional[Iterable[str]] = None,
    fields: Dict[str, Iterable[str]] = dict(TRACK_FIELDS),
) -> List[Dict]:
    """Convert spotify api results to dicts.

    :param items: A list of dictionary tracks.
    :param root: A list of subcomponents of the track dictionaries which should be traversed before finding the fields.
    :param fields: A dict of field names and the corresponding path (iterable) through a track dictionary to retrieve
                   the associated value.
    """

    results = []
    for item in items:
        if root is not None:
            for part in root:
                item = item[part]
        result = {}
        for key, field in fields.items():
            track = dict(item)
            for part in field:
                track = track[part]
            result[key] = track
        results.append(result)
    return results


def results_to_tracks(results: dict, root=TRACK_ROOT) -> List[Track]:
    """Convert spotify api result dicts to tracks."""
    dicts = select_fields(results, root)
    return [Track(**d) for d in dicts]


def remove_nonlocal(playlist: Playlist):
    """Remove all nonlocal tracks from the playlist in-place."""
    playlist -= [track for track in playlist if not track.is_local]
    return playlist
