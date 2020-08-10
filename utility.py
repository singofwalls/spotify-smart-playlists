import re
import string
from collections import OrderedDict, namedtuple
from itertools import groupby
from typing import Union, Iterable

from textdistance import levenshtein
from tqdm import tqdm
from unidecode import unidecode

MINIMUM_SCORES = {"artist": 0.8, "name": 0.7, "album": 0}
MINIMUM_SCORE = 1

TRACK_FIELDS = OrderedDict(
    name=("name",),
    artist=("artists", 0, "name"),
    album=("album", "name"),
    is_local=("is_local",),
    id=("id",),
    duration_ms=("duration_ms",),
    available_markets=("available_markets",),
    linked_from=("linked_from", "id"),
    is_playable=("is_playable",),
)
TRACK_ROOT = ("track",)


class Track:
    """Maintain fields related to a single track in a playlist."""

    keys = ("name", "artist", "album", "is_local")

    def __init__(self, *args, **kwargs):
        # Hardcode attributes so intellisense doesn't go mad
        self.name = None
        self.artist = None
        self.album = None
        self.id = None
        self.is_local = None
        self.duration_ms = None
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


# Tracks which appear to be matches but are actually different
MATCH_TRACK_EXCEPTIONS = (
    (
        Track(
            "Day After Day - Remastered 2010",
            "Badfinger",
            "Straight Up (Remastered 2010 / Deluxe Edition)",
            False,
        ),
        Track(
            "No Matter What - Remastered 2010",
            "Badfinger",
            "No Dice (Remastered 2010 / Deluxe Edition)",
            False,
        ),
    ),
    (
        Track("The Hurt Is Gone", "Yellowcard", "The Hurt Is Gone", False,),
        Track("The Hurt Is Gone", "Yellowcard", "Yellowcard", False,),
    ),
)
# Albums which appear to be matches but are actually different
AlbumException = namedtuple("AlbumException", "artist albums")
MATCH_ALBUM_EXCEPTIONS = (
    AlbumException(
        "Forget About Tomorrow",
        ("Bermuda", "Sooner Than Later EP", "Better Days EP", "Long Walk Home"),
    ),
)


def remove_extra(name):
    """Remove the parentheses and hyphens from a song name."""
    return re.sub(r"-[\S\s]*", "", re.sub(r"\([\w\W]*\)", "", name))


def clean(name):
    """Remove potential discrepencies from the string."""
    name = unidecode(name)  # Remove diacritics
    name = "".join(
        (c for c in name if c in (string.ascii_letters + string.digits + " "))
    )
    name = name.lower().strip()
    return name


def distance(str1, str2):
    """Return the inverse of the Needleman-Wunsch similarity between two strings.

    Closer to 1 is a better match.
    """
    return 1 - levenshtein.normalized_distance(clean(str1), clean(str2))


def search_list(
    search_tracks: Union[str, Iterable], target_track, search_tracks_name=None
):
    """Search through search_tracks for matches resembling target_track.

    :param target_track: the track to fuzzy search for by name, album, and artist
    :param search_tracks: list of tracks. groupby artist and then search
    :param search_tracks_name: if provided, check if search_tracks is memoized by name and memoize groups if not
    """
    if "grouped_lists" not in search_list.__dict__:
        search_list.grouped_lists = {}

    suffix = ""
    artist = target_track.artist.lower()
    if artist:
        # Check if memoized
        if search_tracks_name and search_tracks_name in search_list.grouped_lists:
            try:
                suffix = f" in {search_tracks.name}"
            except AttributeError:
                suffix = f" in {search_tracks}"
            grouped_list = search_list.grouped_lists[search_tracks_name]
            if artist in grouped_list:
                search_tracks = grouped_list[artist]
            else:
                search_tracks = []
        else:
            groups = group_by_artist(search_tracks)
            # Memoize
            if search_tracks_name:
                search_list.grouped_lists[search_tracks_name] = groups
            if artist in groups:
                search_tracks = groups[artist]

    album_exceptions = []
    for exception_group in MATCH_ALBUM_EXCEPTIONS:
        if (
            exception_group.artist == target_track.artist
            and target_track.album in exception_group.albums
        ):
            album_exceptions = list(exception_group.albums)
            album_exceptions.remove(target_track.album)
    track_exceptions = []
    for exception_group in MATCH_TRACK_EXCEPTIONS:
        if target_track in exception_group:
            track_exceptions = list(exception_group)
            track_exceptions.remove(target_track)
    matches = []
    for track in tqdm(
        search_tracks, desc=f"Searching for {target_track.name}" + suffix, leave=False
    ):
        # Is automatically not a match for anything in track_exceptions or album exceptions
        if track in track_exceptions:
            continue
        if track.album in album_exceptions:
            continue
        good = True
        scores = []
        for score_name in MINIMUM_SCORES:
            score = 0
            if target_track.__dict__[score_name] and track.__dict__[score_name]:
                score = distance(
                    target_track.__dict__[score_name], track.__dict__[score_name]
                )
            if score < MINIMUM_SCORES[score_name]:
                good = False
                break
            scores.append(score * MINIMUM_SCORES[score_name])
        if not good:
            continue

        match = (sum(scores), track)
        matches.append(match)
        if sum(scores) == sum(MINIMUM_SCORES.values()):
            return [match]  # Perfect match

    return sorted(matches, key=lambda a: a[0], reverse=True)


def find_match(
    search_tracks: Union[str, Iterable], target_track, search_tracks_name=None
):
    """Search through search_tracks for closest match to target_track.

    :param target_track: the track to fuzzy search for by name, album, and artist
    :param search_tracks: list of tracks. groupby artist and then search
    :param search_tracks_name: if provided, check if search_tracks is memoized by name and memoize groups if not
    """
    matches = search_list(search_tracks, target_track, search_tracks_name)

    if not matches:
        return None
    best_result = matches[0]
    if best_result[0] >= MINIMUM_SCORE:
        return best_result[1]

    return None


def group_by_artist(search_tracks):
    """Group a list of tracks by artist."""
    key = lambda t: t.artist
    return {
        k.lower(): tuple(v) for k, v in groupby(sorted(search_tracks, key=key), key=key)
    }
