"""Create default playlists."""
import warnings

from playlists import (
    get_credentials,
    get_spotify,
    get_saved_songs,
    Playlist,
    Track, results_to_tracks,
)

import pylast


creds = get_credentials()
spotify = get_spotify(creds["spotify"])


def create_smart_playlists():
    saved_songs = get_saved_songs(spotify)
    p_saved_songs = Playlist(spotify, "Liked Songs")
    p_saved_songs += saved_songs

    p_instrumental = Playlist(spotify, "All Instrumental", populate=True)

    p_saved_bands = Playlist(spotify, "Liked Songs - Bands", populate=True)
    # remove_nonlocal(p_saved_bands)
    p_saved_bands += p_saved_songs - p_instrumental
    p_saved_bands.name = "Liked Songs - Bands"
    p_saved_bands.publish()

    p_saved_instrumentals = Playlist(
        spotify, "Liked Songs - Instrumentals", populate=True
    )
    # remove_nonlocal(p_saved_instrumentals)
    p_saved_instrumentals += p_instrumental & saved_songs
    p_saved_instrumentals.name = "Liked Songs - Instrumentals"
    p_saved_instrumentals.publish()

    p_save_songs_all = Playlist(spotify, "Liked Songs - All", populate=True)
    # remove_nonlocal(p_save_songs_all)
    p_save_songs_all += p_saved_instrumentals + p_saved_bands
    p_save_songs_all.name = "Liked Songs - All"
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
    lastfm_network = get_lastfm(creds["last.fm"])
    lastfm_user = lastfm_network.get_authenticated_user()
    lastfm_top_tracks_all = lastfm_user.get_top_tracks(
        limit=100, period="PERIOD_OVERALL"
    )
    lastfm_top_tracks_recent = lastfm_user.get_top_tracks(
        limit=100, period="PERIOD_3MONTHS"
    )

    tracks = []
    for result in lastfm_top_tracks_all + lastfm_top_tracks_recent:
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
        query = f'"{name}"'
        if artist:
            query += f' artist:"{artist}"'
        if album:
            query += f' album:"{album}"'

        results = spotify.search(q=query, type="track")
        result_tracks = results_to_tracks(results["tracks"]["items"], [])
        if not result_tracks:
            warnings.warn(f"Could not find spotify match for {query}")
            continue

        match = result_tracks[0]
        for result in result_tracks:
            if result.name != name:
                continue
            if result.album != album:
                continue
            if result.artist != artist:
                continue
            match = result
            break
        else:
            warnings.warn(f"Using imperfect spotify match for {query}: {match}")
        tracks.append(match)

    current_rotation = Playlist(spotify, "Current Rotation", populate=True)
    current_rotation += tracks
    current_rotation.publish()
#     TODO: maintain list of failed/imperfect matches. Traverse entire spotify user lib to find fuzzy matches


# create_smart_playlists()
create_lastfm_playlist()
