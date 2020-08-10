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
BLACK_LIST_PLAYLIST = "4eRsAraBhmj3kXU0CY5byO"
ORDERED_BIAS = 3
FAMILY_PLAYLISTS_NAMES = ("Erin", "Randy", "Brady", "Graham", "Reece", "FAT", "651")
MAIN_PLAYLISTS = 5  # First # playlists are preferred
PLAYLISTS_ORDERED = (False, False, False, False, True, False, False)
SONG_LIST_FILE = "song_list.txt"

MAX_RUN = 3  # Maximum number of songs one person can have in a row
MAX_WAIT = 20  # Number of minutes someone can wait before being forced
SCALE = 2  # Take weights to this power

UPDATE = True
FUZZY_DUPE_CHECKING = True

creds = pl.get_credentials()
spotify = pl.get_spotify(creds["spotify"])

playlists = [pl.Playlist(spotify, None, id_, True) for id_ in FAMILY_PLAYLISTS]
cum_wait = OrderedDict((player.id, 0) for player in playlists)

playlist_roadtrip = pl.Playlist(spotify, "2020 Family Summer Vacation")
playlist_blacklist = pl.Playlist(spotify, None, id_=BLACK_LIST_PLAYLIST, populate=True)
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


def get_symbol(playlist_id: str, wait_):
    """Get the symbol with which to prefix a cumulative wait time."""
    prefix = " "
    suffix = " "
    if wait_ == max(cum_wait.values()):
        suffix = "m"
    if playlist_id == playlist_chosen.id:
        prefix = "x"

    return prefix + suffix


run = 1
last_playlist = None
dupes = []
person_song_map = []
last_play = {playlist: 0 for playlist in FAMILY_PLAYLISTS}
main_end = False
while playlists:
    playlist_options = []
    for playlist in playlists[:MAIN_PLAYLISTS]:
        wait = last_play[playlist.id]
        if wait > MAX_WAIT:
            playlist_options.append(playlist)

    if playlist_options:
        option_names = [(FAMILY_PLAYLISTS_NAMES[FAMILY_PLAYLISTS.index(p.id)], round(last_play[p.id], 2)) for p in playlist_options]
        print(f"Playlist choice limited to wait times > {MAX_WAIT}: ", option_names)
    else:
        playlist_options = playlists

    while True:
        playlist_chosen = random.choices(
            playlist_options, weights=tuple(weight ** SCALE for weight in [cum_wait[p.id] for p in playlist_options])
        )[0]
        # Stop long runs
        if (
            len(playlists) > 1
            and last_playlist == playlist_chosen.id
            and run >= MAX_RUN
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
    behind_chosen_by = most_behind - cum_wait[playlist_chosen.id]
    least_behind = min(cum_wait.values())

    behind_before = cum_wait[playlist_chosen.id] - least_behind
    remaining_ids = [playlist.id for playlist in playlists]

    cum_before = []
    for playlist_id in FAMILY_PLAYLISTS:
        for playlist_id_wait in cum_wait:
            if playlist_id_wait == playlist_id:
                wait = cum_wait[playlist_id_wait]
                cum_before.append(f"{get_symbol(playlist_id_wait, wait)} {format_p(wait)}")
                break
        else:
            cum_before.append(" " * (WAIT_LEN - 2))

    cum_before = ", ".join(cum_before)

    if not playlist_chosen:
        # Out of songs!
        playlists.remove(playlist_chosen)
        del cum_wait[playlist_chosen.id]

    for playlist_id in FAMILY_PLAYLISTS[:MAIN_PLAYLISTS]:
        if playlist_id not in [playlist.id for playlist in playlists]:
            # One of the main playlists has run out.
            main_end = True
            break

    if song in playlist_blacklist:
        print(f"Song for {playlist_author} already played in blacklist:", song)
        continue
    if FUZZY_DUPE_CHECKING:
        match = find_match(playlist_blacklist, song)
        if match:
            print(
                f"Fuzzy match for {playlist_author} already played in blacklist:", song
            )
            continue

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

    duration = song.duration_ms / 1000 / 60
    person_song_map.append(
        (
            playlist_author,
            format_p(last_play[playlist_chosen.id]),
            format_p(duration),
            len(playlist_chosen),
            song.name,
            song.artist,
            song.album,
            main_end,
        )
    )

    last_play[playlist_chosen.id] = 0
    for playlist in playlists:
        if playlist is not playlist_chosen:
            last_play[playlist.id] += duration
            cum_wait[playlist.id] += duration

    min_run = min(cum_wait.values()) if playlists else 0
    for playlist in playlists:
        cum_wait[playlist.id] -= min_run

    behind_after = (
        (cum_wait[playlist_chosen.id] - min(cum_wait.values()))
        if playlist_chosen in playlists
        else -1
    )
    print(
        msg_format.format(
            cum_before,
            most_behind_by_name,
            format_(behind_chosen_by),
            playlist_author,
            format_(duration),
            format_(behind_before),
            format_(behind_after),
            song.name,
        )
    )

playlist_roadtrip += songs
print(playlist_roadtrip)
for dupe in dupes:
    print("FUZZY DUPLICATES REMOVED:", dupe)
print("\nSONG_LIST")
line_format = "{:<10}\t{:<10}\t{:<10}\t{:<10}\t{:<50.50}\t{:<20.20}\t{:<50.50}\t{:<4}"
header = line_format.format(
    "author", "wait (min)", "song len.", "songs left", "song name", "artist", "album", "END"
)
print(header)
with open(SONG_LIST_FILE, "w") as f:
    f.write("")
with open(SONG_LIST_FILE, "a") as f:
    f.write(header + "\n")
    for song_info in person_song_map:
        line = line_format.format(*song_info)
        f.write(line + "\n")
        print(line)

end_index = 0
for i, song_info in enumerate(person_song_map):
    if song_info[7]:
        end_index = i
        break

wait_times = [time for time in sorted(person_song_map[:end_index+1], key=lambda s: float(s[1]), reverse=True) if FAMILY_PLAYLISTS_NAMES.index(time[0]) < MAIN_PLAYLISTS]
print("\n5 greatest wait times")
print(wait_times[:5])
print("\n Average wait time")
print(sum([float(info[1]) for info in wait_times])/len(wait_times))

if UPDATE:
    playlist_roadtrip.publish(public=True)
