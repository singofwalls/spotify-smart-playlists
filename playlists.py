"""Create dynamic Spotify playlists using Playlist objects."""
import json
import reprlib
import warnings
from collections import namedtuple
from itertools import chain
from typing import Iterable, List, Mapping, Dict, Optional, OrderedDict

import spotipy
from spotipy import util

# TODO: Remove duplicates
from tqdm import tqdm

from utility import find_match, clean, remove_extra

print = tqdm.write

CREDS_FILE = "creds.json"

TRACK_ROOT = ("track",)
TRACK_FIELDS = {
    "id": ("id",),
    "name": ("name",),
    "is_local": ("is_local",),
    "duration_ms": ("duration_ms",),
    "album": ("album", "name"),
    "artist": ("artists", 0, "name"),
    "available_markets": ("available_markets",),
    "linked_from": ("linked_from", "id"),
    "is_playable": ("is_playable",),
}
PLAYLIST_FIELDS = {"id": ("id",), "name": ("name",)}

API_LIMIT = 50
USER_MARKET = "US"


class Track:
    """Maintain fields related to a single track in a playlist."""

    keys = ("name", "album", "artist", "is_local")

    def __init__(self, *args, **kwargs):
        # Hardcode attributes so intellisense doesn't go mad
        self.id = None
        self.name = None
        self.is_local = None
        self.duration_ms = None
        self.album = None
        self.artist = None
        self.available_markets = None
        self.linked_from = None
        self.original_id = None

        self.__dict__ = {key: None for key in TRACK_FIELDS.keys()}
        self.__dict__.update(
            {key: value for key, value in zip(TRACK_FIELDS.keys(), args)}
        )
        self.__dict__.update(kwargs)

        if self.linked_from:
            self.original_id = self.id
            self.id = self.linked_from

        self.__slots__ = tuple(TRACK_FIELDS.keys())

    def get_fields(self):
        """Get fields of this track for display."""
        return {k: self.__dict__[k] for k in self.__class__.keys}

    def __hash__(self):
        return hash(tuple(self.get_fields().items()))

    def __repr__(self):
        return f"{self.__class__.__name__}({', '.join(f'{key}={repr(val)}' for key, val in self.get_fields().items())})"

    def __eq__(self, other):
        return self.get_fields() == other.get_fields()

    def copy(self):
        """Return a shallow copy of this track."""
        return Track(**self.__dict__)


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
            self.load_tracks_from_spotify()

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
        new.tracks = self.tracks[:]
        return new

    def load_tracks_from_spotify(self):
        """Overwrite the playlist with tracks from the playlist id."""
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

        def get_track_name(track_id: str, track_list: Iterable[Track]) -> Optional[str]:
            """Find a track's name from id in a list of tracks."""
            for t in track_list:
                if t.id == track_id:
                    return t.name
            return None

        TrackPos = namedtuple("TrackPos", "pos id")

        name = self.name if name is None else name
        user = self.spotify.me()["id"]

        if always_new or self.id is None:
            playlist = self.spotify.user_playlist_create(user, name, public, desc)
            self.id = playlist["id"]

        tracks_online_old = get_playlist_tracks(self.spotify, self.id)
        tracks_online, no_match = update_tracks(self.spotify, tracks_online_old)

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
                    # print(
                    #     f"Moving track in {self.name}: {track.name} from {shifted_track_index} to {online_index}"
                    # )
                    self.spotify.user_playlist_reorder_tracks(
                        user, self.id, shifted_track_index, online_index
                    )
                    # Update local copy
                    tracks_online.insert(
                        online_index, tracks_online.pop(shifted_track_index)
                    )
                    online_index += 1
                else:
                    warnings.warn(
                        f"No local file for {track.name} available in online playlist {self.name} to move to spot {online_index + 1}"
                    )
            else:
                # Track missing from playlist, record position to insert into later
                new_tracks.append(TrackPos(online_index + added, track.id))
                added += 1

        # Remove extra tracks at end which are in wrong place
        num_extra_tracks_local = 0
        while online_index < len(tracks_online):
            # Partition tracks to be removed
            tracks = tracks_online[online_index : online_index + API_LIMIT]
            # print(
            #     f"Removing from {self.name}: ", [t.name for t in tracks],
            # )
            extra_tracks_uri_dicts = []
            extra_tracks_local = []
            extra_tracks_id_map = {}
            extra_tracks_local_num_map = {}
            local_files = 0
            for pos, track in enumerate(tracks):
                if track.is_local or (
                    track.available_markets is not None and not track.available_markets
                ):
                    index = online_index
                    local_files += 1
                    extra_tracks_local.append(index)
                    extra_tracks_local_num_map[index + local_files] = track
                else:
                    track_uri_dict = {
                        "uri": track.id,
                        "positions": [online_index + pos],
                    }
                    extra_tracks_id_map[track.id] = track
                    extra_tracks_uri_dicts.append(track_uri_dict)

            # Update local copy
            for i in range(online_index, online_index + API_LIMIT):
                if online_index < len(tracks_online):
                    # Local copy must believe local tracks were removed even though they are actually placed on the end
                    tracks_online.pop(online_index)

            # Update remote copy
            failed = remove_tracks(self.spotify, extra_tracks_uri_dicts, self.id, user)
            if failed:
                raise RuntimeError(
                    f"Failed to remove {[extra_tracks_id_map[t_uri_dict['uri']].name for t_uri_dict in failed]} from {self.name}"
                )

            num_extra_tracks_local += len(extra_tracks_local)
            tracks_to_move = [extra_tracks_local_num_map[num + i + 1] for i, num in enumerate(extra_tracks_local)]
            for track_pos in extra_tracks_local:
                self.spotify.user_playlist_reorder_tracks(
                    user, self.id, track_pos, len(tracks_online) + num_extra_tracks_local
                )
            if extra_tracks_local:
                print(
                    f"Added {len(extra_tracks_local)} extra local tracks to end of {self.name}: {[track.name for track in tracks_to_move]}"
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
            # print(
            #     f"Adding to {self.name}: ",
            #     [(get_track_name(t.id, self.tracks), t.pos) for t in tracks],
            # )
            self.spotify.user_playlist_add_tracks(
                user,
                self.id,
                [track.id for track in tracks],
                tracks[0].pos,  # All tracks must be added from a single pos
            )
            tracks = []

        print(f"{self.name} complete.\n")


def update_tracks(spotify: spotipy.Spotify, tracks, exclude=False):
    """Get links to tracks available in the USER_MARKET.

    :param exclude: Remove tracks from playlist if not available in USER_MARKET
    """
    new_tracks = []
    failed = []
    for track in tracks:
        closest_track = track
        # if track.available_markets is None, it was found in a search for USER_MARKET and is therefore already updated
        if (
            not track.is_local
            and track.available_markets is not None
            and not track.available_markets
        ):
            best_result = search(spotify, track.name, track.album, track.artist)

            if best_result:
                closest_track = best_result
            else:
                # If no markets, track must be out of date
                track.available_markets = tuple()
                failed.append(track)
                if exclude:
                    continue

        new_tracks.append(closest_track)

    if failed:
        suffix = " Removing"
        if not exclude:
            suffix = " Not removing because exclude flag is False"
        warnings.warn(
            f"Could not find tracks in {USER_MARKET} market: {failed}." + suffix
        )

    return new_tracks, failed


def remove_tracks(
    spotify: spotipy.Spotify, track_uri_dict: List[Dict], playlist_id: str, user: str
) -> List[Dict]:
    """Remove tracks from remote playlist.

    :param track_uri_dict: list of track dicts containing uri and position
    :returns: List of track_uri_dicts which failed to upload
    """
    try:
        spotify.user_playlist_remove_specific_occurrences_of_tracks(
            user, playlist_id, track_uri_dict
        )
    except spotipy.exceptions.SpotifyException:
        if len(track_uri_dict) == 1:
            return track_uri_dict
        bottom_half = remove_tracks(
            spotify, track_uri_dict[len(track_uri_dict) // 2 :], playlist_id, user
        )
        top_half = remove_tracks(
            spotify, track_uri_dict[: len(track_uri_dict) // 2], playlist_id, user
        )
        return top_half + bottom_half
    return []


def search(spotify: spotipy.Spotify, name, album=None, artist=None, market=USER_MARKET):
    """Get search results from spotify for a given song."""

    def create_query(track):
        """Create a search query from a track."""
        query = f'"{track.name}"'
        if track.artist:
            query += f' artist:"{track.artist}"'
        if track.album:
            query += f' album:"{track.album}"'
        return query

    def album_searches(album_):
        """Yield various potential album name searches."""
        yield album_

        if not album_:
            return None

        yield clean(album_)
        # Cleaning removes symbols which remove_extra looks for. remove_extra on original album only!
        album_ = remove_extra(album_)
        yield album_
        album_ = clean(album_)
        yield album_
        yield None

    for album_search in album_searches(album):
        target_track = Track(name=name, album=album_search, artist=artist)
        results = spotify.search(q=create_query(target_track), market=market)
        matches = results_to_tracks(results["tracks"]["items"], [])
        best_result = find_match(matches, target_track)
        if best_result:
            return best_result


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
    results = get_all(spotify, spotify.playlist_tracks(playlist_id, market=USER_MARKET))

    return results_to_tracks(results)


def get_saved_songs(spotify: spotipy.Spotify):
    """Load all songs from the users saved songs."""
    results = get_all(spotify, spotify.current_user_saved_tracks(limit=API_LIMIT))

    return results_to_tracks(results)


def get_playlists(spotify: spotipy.Spotify, reload=False) -> List[Dict[str, str]]:
    """Get a list of user playlist names and ids. Memoized."""
    if "playlists" not in get_playlists.__dict__ or reload:
        playlists = get_all(spotify, spotify.current_user_playlists())
        get_playlists.playlists = select_fields(playlists, fields=PLAYLIST_FIELDS)

    return get_playlists.playlists


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
            missing = False
            for part in field:
                try:
                    track = track[part]
                except KeyError:
                    missing = True
                    break
            if missing:
                continue
            if isinstance(track, list):
                track = tuple(track)
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
