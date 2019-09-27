import spotipy
from spotipy import util

import json


CREDS_FILE = "creds.json"


def main():
    creds = get_credentials()
    spotify = get_spotify(creds)

    with open("songs.json", "w") as f:
        json.dump(get_all_songs(spotify), f)



def get_all_songs(spotify: spotipy.Spotify):
    """Load all songs from the users save songs."""
    # 50 is max limit for api
    result = spotify.current_user_saved_tracks(limit=50)
    results = result["items"]
    while result["next"]:
        result = spotify.next(result)
        results.extend(result["items"])

    return results



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


if __name__ == "__main__":
    main()
