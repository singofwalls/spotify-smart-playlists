import re
import string
from itertools import groupby
from typing import Union, Iterable

from textdistance import levenshtein
from tqdm import tqdm
from unidecode import unidecode


MINIMUM_SCORES = {"artist": 0.8, "name": 0.7, "album": 0}
MINIMUM_SCORE = 1


def remove_extra(name):
    """Remove the parentheses and hyphens from a song name."""
    return re.sub("-[\S\s]*", "", re.sub("\([\w\W]*\)", "", name))


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


def search_list(search_tracks: Union[str, Iterable], target_track, search_tracks_name=None):
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

    matches = []
    for track in tqdm(
        search_tracks, desc=f"Searching for {target_track}" + suffix, leave=False
    ):
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


def find_match(search_tracks: Union[str, Iterable], target_track, search_tracks_name=None):
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