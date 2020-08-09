"""Create default playlists."""
import warnings

import pylast
from tqdm import tqdm

from playlists import (
    get_credentials,
    get_spotify,
    get_saved_songs,
    Playlist,
    Track,
    search,
)

# warnings.simplefilter("ignore")
from utility import MINIMUM_SCORE, find_match

creds = get_credentials()
spotify = get_spotify(creds["spotify"])

saved_songs = get_saved_songs(spotify)
p_saved_songs = Playlist(spotify, "Liked Songs")
p_saved_songs += saved_songs

p_current_rotation = Playlist(spotify, "Current Rotation", populate=True)


def create_smart_playlists():
    p_instrumental = Playlist(spotify, "All Instrumental", populate=True)
    p_local = Playlist(spotify, "Local Files", populate=True)

    p_all_saved = p_saved_songs + p_local
    p_all_saved.name = "All Saved"

    p_saved_bands = Playlist(spotify, "Liked Songs - Bands")
    p_saved_bands += p_all_saved - p_instrumental
    p_saved_bands.publish()

    p_saved_instrumentals = Playlist(spotify, "Liked Songs - Instrumentals")
    p_saved_instrumentals += p_instrumental & p_all_saved
    p_saved_instrumentals.publish()

    p_save_songs_all = Playlist(spotify, "Liked Songs - All")
    p_save_songs_all += p_saved_instrumentals + p_saved_bands
    p_save_songs_all.publish()


def get_lastfm(l_creds):
    """Get the lastfm network object from which to make requests."""
    lastfm_password = l_creds["password"]
    lastfm_pass_hash = pylast.md5(lastfm_password)
    return pylast.LastFMNetwork(
        api_key=l_creds["api_key"],
        api_secret=l_creds["api_secret"],
        username=l_creds["username"],
        password_hash=lastfm_pass_hash,
    )


def create_lastfm_playlist():
    """Create playlists from last.fm data."""
    global p_current_rotation

    lastfm_network = get_lastfm(creds["last.fm"])
    lastfm_user = lastfm_network.get_authenticated_user()
    lastfm_top_tracks_all = lastfm_user.get_top_tracks(
        limit=100, period="PERIOD_OVERALL"
    )
    lastfm_top_tracks_recent = lastfm_user.get_top_tracks(
        limit=100, period="PERIOD_3MONTHS"
    )

    tracks = []
    missing = []
    for result in tqdm(
        lastfm_top_tracks_all + lastfm_top_tracks_recent,
        "Finding lastfm songs on Spotify",
        leave=False,
    ):
        name = result.item.get_name()
        album = None
        artist = None
        try:
            album = result.item.get_album().get_name()
        except AttributeError:
            warnings.warn(f"No album associated with {name}")
        try:
            artist = result.item.get_artist().get_name()
        except AttributeError:
            warnings.warn(f"No artist associated with {name}")

        # Search current_rotation and saved_songs
        target = Track(name=name, album=album, artist=artist)
        found = False
        for group in search_lists:
            best_result = find_match(search_lists[group], target, group)
            if best_result:
                tracks.append(best_result)
                found = True
                break
        if found:
            continue

        warnings.warn(f"Could not find match for {target} in user library")

        # Try spotify search

        best_result = search(spotify, name, album, artist)
        if not best_result:
            warnings.warn(
                f"Could not find any spotify match for {(name, album, artist)}"
            )
            missing.append(target)
            continue

        if best_result:
            tracks.append(best_result)
            continue

    print("Could not find matches for", missing)
    p_current_rotation += tracks
    p_current_rotation.publish()


search_lists = {
    "current_rotation": p_current_rotation,
    "saved_songs": p_saved_songs,
}

# create_smart_playlists()
create_lastfm_playlist()

