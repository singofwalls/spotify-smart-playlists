"""Create default playlists."""
import re
import warnings
import calendar
from datetime import datetime, timedelta

import pylast
from tqdm import tqdm

from playlists import (
    get_credentials,
    get_spotify,
    get_saved_songs,
    Playlist,
    Track,
    search,
    get_playlists,
    get_playlist_tracks,
)

# warnings.simplefilter("ignore")
from utility import find_match

print = tqdm.write

creds = get_credentials()
spotify = get_spotify(creds["spotify"])

saved_songs = get_saved_songs(spotify)
p_saved_songs = Playlist(spotify, "Liked Songs")
p_saved_songs += saved_songs

p_current_rotation = Playlist(spotify, "Current Rotation", populate=True)
p_lastfm_top = Playlist(spotify, "Lastfm Top", populate=True)
p_instrumental = Playlist(spotify, "All Instrumental", populate=True)
p_all_monthly = Playlist(spotify, "All Monthly", populate=True)

today = datetime.today()
# number of months before today to include in monthly_playlist
monthly_num_months_previous = 12
cutoff_date = datetime.today() - timedelta(days=monthly_num_months_previous * 30)
cutoff_date = cutoff_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def create_smart_playlists():
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


def update_lastfm_playlist():
    """Get top tracks from last.fm data."""
    global p_lastfm_top

    lastfm_network = get_lastfm(creds["last.fm"])
    lastfm_user = lastfm_network.get_authenticated_user()
    lastfm_top_tracks = []
    # Available periods as per last.fm docs (NOT PYLAST DOCS): overall | 7day | 1month | 3month | 6month | 12month
    # Using pylast period format (PERIOD_OVERALL | PERIOD_7DAYS | PERIOD_1MONTH | etc) just returns results for overall
    for num, period in (
        (150, "overall"),
        (100, "3month"),
        (30, "1month"),
        (10, "7day"),
    ):
        lastfm_top_tracks += lastfm_user.get_top_tracks(limit=num, period=period)

    tracks = []
    missing = []
    searched_tracks = []
    for result in tqdm(
        lastfm_top_tracks, "Finding lastfm songs on Spotify", leave=False,
    ):
        name = result.item.get_name()
        album = None
        artist = None
        try:
            album = result.item.get_album().get_name()
        except AttributeError:
            pass
            # warnings.warn(f"No album associated with {name}")
        try:
            artist = result.item.get_artist().get_name()
        except AttributeError:
            warnings.warn(f"No artist associated with {name}")

        # Search current_rotation and saved_songs
        target = Track(name=name, album=album, artist=artist)
        if target in searched_tracks:
            continue
        searched_tracks.append(target)

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

        if best_result:
            tracks.append(best_result)
            continue
        else:
            warnings.warn(
                f"Could not find any spotify match for {(name, album, artist)}"
            )
            missing.append(target)

    if missing:
        print("\n**Could not find matches for", missing)

    p_lastfm_top.tracks.clear()
    p_lastfm_top += tracks
    p_lastfm_top -= p_instrumental

    p_lastfm_top.publish()

    return tracks, missing


def update_all_monthly_playlist():
    """Compile all monthly playlists into one."""
    global p_all_monthly

    months = tuple(month.lower() for month in calendar.month_name)[1:]
    months_str = "|".join(months)
    match = re.compile(f"({months_str})(-({months_str}))" + "{0,1} [0-9]{4}")
    monthly_playlist_ids = []
    for playlist_id in get_playlists(spotify):
        name = playlist_id["name"].lower()
        if match.match(name):
            first_month, year = name.split(" ")
            if "-" in name:
                first_month = name.split("-")[0]

            date = datetime.strptime(f"{first_month.title()} {year}", "%B %Y")
            if date >= cutoff_date:
                monthly_playlist_ids.append(playlist_id["id"])

    p_all_monthly.tracks.clear()
    for playlist_id in monthly_playlist_ids:
        p_all_monthly += get_playlist_tracks(spotify, playlist_id)

    p_all_monthly.publish()

    return p_all_monthly


def create_current_rotation(update_lastfm=False, update_monthly=True):
    """Create the current rotation playlist."""
    global p_current_rotation
    if update_lastfm:
        update_lastfm_playlist()
    if update_monthly:
        update_all_monthly_playlist()

    p_current_rotation.tracks.clear()
    p_current_rotation += p_lastfm_top
    p_current_rotation += p_all_monthly

    p_current_rotation -= p_instrumental

    p_current_rotation.publish()


search_lists = {
    "p_lastfm_top": p_lastfm_top,
    "saved_songs": p_saved_songs,
}

# create_smart_playlists()
create_current_rotation(True)
