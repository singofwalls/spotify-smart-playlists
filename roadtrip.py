import random
from collections import OrderedDict

import playlists as pl
from utility import find_match

FAMILY_PLAYLISTS = (
    "33zZ5PLhHylehEY0nN6dkU",
    "21WAQQVuS4Gz0IG8MD9XRz",
    "6LCfJrtLW6zyKh6QOd5eyw",
    "0h2AE2G95T1D4s2l2IeoJX",
    "0l1OHmq3g40tBHPOL6b34J",
    "1WN0DhY37vI954VYCuopVl",
    "5cTkATCHoowXXcAnBa0FyZ",
)
ORDERED_BIAS = 2
FAMILY_PLAYLISTS_NAMES = ("Erin", "Randy", "Brady", "Graham", "Reece", "FAT", "651")
PLAYLISTS_ORDERED = (False, False, False, False, True, False, False)

MAX_RUN = 3  # Maximum number of songs one person can have in a row
SCALE = 2  # Take weights to this power

UPDATE = False
FUZZY_DUPE_CHECKING = True

creds = pl.get_credentials()
spotify = pl.get_spotify(creds["spotify"])

playlists = [pl.Playlist(spotify, None, id_, True) for id_ in FAMILY_PLAYLISTS]
cum_wait = OrderedDict((player, 0) for player in playlists)

playlist_roadtrip = pl.Playlist(spotify, "2020 Family Summer Vacation")
songs = []

WAIT_LEN = 10  # Length of the cumulative waits displays
format_p = lambda val: "{:<05.2f}".format(val)
format_n_str = f"{{:^{WAIT_LEN}.{WAIT_LEN}}}"
format_n = lambda val: format_n_str.format(val)
format_ = lambda val: "{:<5.2f}".format(val)

msg_format = "{:%d} {:<15.15} {:<14} {:<15.15} {:<10} {:<12} {:<12} {:<50.50}" % (
    len(playlists) * WAIT_LEN
)

print("Cumulative waits")
print(
    msg_format.format(
        "".join([format_n(playlist) for playlist in FAMILY_PLAYLISTS_NAMES]),
        "Most behind",
        "Behind chosen",
        "Chosen Playlist",
        "Song Dur.",
        "Behind bef.",
        "Behind now",
        "Song Name",
    )
)


def get_symbol(playlist, wait_):
    """Get the symbol with which to prefix a cumulative wait time."""
    prefix = " "
    suffix = " "
    if wait_ == max(cum_wait.values()):
        suffix = "m"
    if playlist == playlist_chosen:
        prefix = "x"

    return prefix + suffix


run = 1
last_playlist = None
dupes = []
while playlists:
    while True:
        playlist_chosen = random.choices(
            playlists, weights=tuple(weight ** SCALE for weight in cum_wait.values())
        )[0]
        # Stop long runs
        if (
            len(playlists) > 1
            and last_playlist == playlist_chosen.id
            and run == MAX_RUN
        ):
            pass
        else:
            break
    if playlist_chosen.id != last_playlist:
        run = 1
        last_playlist = playlist_chosen.id
    else:
        run += 1
    playlist_author = FAMILY_PLAYLISTS_NAMES[FAMILY_PLAYLISTS.index(playlist_chosen.id)]

    chosen_playlist_static_index = FAMILY_PLAYLISTS.index(playlist_chosen.id)
    weights = None
    if PLAYLISTS_ORDERED[chosen_playlist_static_index]:
        weights = [
            weight ** ORDERED_BIAS for weight in range(len(playlist_chosen), 0, -1)
        ]

    song = random.choices(playlist_chosen.tracks, weights=weights)[0]
    playlist_chosen -= song

    most_behind = max(cum_wait.values())
    index = tuple(cum_wait.values()).index(most_behind)
    most_behind_static_index = FAMILY_PLAYLISTS.index(playlists[index].id)
    most_behind_by_name = FAMILY_PLAYLISTS_NAMES[most_behind_static_index]
    behind_chosen_by = most_behind - cum_wait[playlist_chosen]
    least_behind = min(cum_wait.values())

    behind_before = cum_wait[playlist_chosen] - least_behind
    remaining_ids = [playlist.id for playlist in playlists]

    cum_before = []
    for playlist_id in FAMILY_PLAYLISTS:
        for playlist in cum_wait:
            if playlist.id == playlist_id:
                wait = cum_wait[playlist]
                cum_before.append(f"{get_symbol(playlist, wait)} {format_p(wait)}")
                break
        else:
            cum_before.append(" " * (WAIT_LEN - 2))

    cum_before = ", ".join(cum_before)

    if not playlist_chosen:
        # Out of songs!
        playlists.remove(playlist_chosen)
        del cum_wait[playlist_chosen]

    if song in songs:
        print(f"Exact duplicate found for {playlist_author} in master playlist:", song)
        continue

    if FUZZY_DUPE_CHECKING:
        match = find_match(songs, song)
        if match:
            dupes.append((match, song))
            print(
                f"Duplicate found for {playlist_author} in master playlist (first, dupe):",
                match,
                song,
            )
            continue
    songs.append(song)

    for playlist in playlists:
        if playlist is not playlist_chosen:
            cum_wait[playlist] += song.duration_ms / 1000 / 60

    min_run = min(cum_wait.values()) if playlists else 0
    for playlist in playlists:
        cum_wait[playlist] -= min_run

    behind_after = (
        (cum_wait[playlist_chosen] - min(cum_wait.values()))
        if playlist_chosen in playlists
        else -1
    )
    print(
        msg_format.format(
            cum_before,
            most_behind_by_name,
            format_(behind_chosen_by),
            playlist_author,
            format_(song.duration_ms / 1000 / 60),
            format_(behind_before),
            format_(behind_after),
            song.name,
        )
    )

playlist_roadtrip += songs
print(playlist_roadtrip)
for dupe in dupes:
    print("DUPLICATES REMOVED:", dupe)

if UPDATE:
    playlist_roadtrip.publish(public=True)

# TODO[reece]: Look for duplicates
