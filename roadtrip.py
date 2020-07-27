from collections import namedtuple, OrderedDict

import playlists as pl

import random


FAMILY_PLAYLISTS = ("5cTkATCHoowXXcAnBa0FyZ", "4mE8nSohxr9m6m9yCN0HFQ", "3RuaHkL1UqCGMp26SmWqrf", "0O9GQn8ElOFTHcMCKf9nZn", "5JCtgNVLjrGKhyYNWptrrH")
SCALE = 5

creds = pl.get_credentials()
spotify = pl.get_spotify(creds)

playlists = [pl.Playlist(spotify, id_, id_, True) for id_ in FAMILY_PLAYLISTS]
cum_wait = OrderedDict((player, 0) for player in playlists)

print(playlists)

playlist_roadtrip = pl.Playlist(spotify, "2020 Family Summer Vacation")
songs = []

format_p = lambda val: "{:<06.2f}".format(val)
format_ = lambda val: "{:<6.2f}".format(val)

while playlists:
    playlist_chosen = random.choices(playlists, cum_weights=tuple(weight**SCALE for weight in cum_wait.values()))[0]
    song = random.choice(playlist_chosen)
    playlist_chosen -= song
    songs.append(song)

    behind_before = cum_wait[playlist_chosen] - min(cum_wait.values())
    cum_before = ", ".join(format_p(val) for val in cum_wait.values())

    if not playlist_chosen:
        # Out of songs!
        playlists.remove(playlist_chosen)
        del cum_wait[playlist_chosen]

    for playlist in playlists:
        if playlist is not playlist_chosen:
            cum_wait[playlist] += song.duration_ms / 1000 / 60

    min_run = min(cum_wait.values()) if playlists else 0
    for playlist in playlists:
        cum_wait[playlist] -= min_run

    behind_after = (cum_wait[playlist_chosen] - min(cum_wait.values())) if playlist_chosen in playlists else -1
    print("{:<40} {:<3} {:<9} {:<9} {:<9} {:<50}".format(cum_before, FAMILY_PLAYLISTS.index(playlist_chosen.name), format_(song.duration_ms/1000/60), format_(behind_before), format_(behind_after), song.name))

playlist_roadtrip += songs
print(playlist_roadtrip)

playlist_roadtrip.publish(public=True)

# TODO[reece]: Look for duplicates
