import random
from collections import OrderedDict
from statistics import mode

import playlists as pl
from utility import find_match

FAMILY_PLAYLISTS = (
    "3JK6wO7YgZPDymywcG6HB8",
    "4KNOgPEWJhefIXpUGOOSMU",
)
BLACK_LIST_PLAYLIST = None
ORDERED_BIAS = 3
FAMILY_PLAYLISTS_NAMES = (
    "Reece",
    "Jacob",
)
MAIN_PLAYLISTS = 2  # First # playlists are preferred
PLAYLISTS_ORDERED = (True, False)
SONG_LIST_FILE = "song_list2.txt"

MAX_RUN = 3  # Maximum number of songs one person can have in a row
MAX_WAIT = 7  # Number of minutes someone can wait before being forced
SCALE = 3  # Take weights to this power
SUPPRESS_UNIMPORTANT = True  # Set weight of unimportant playlists to max of 1.5 * max weight of important playlists
MAX_SCALE_UNIMPORTANT = 1  # Multiply max important weight by this scale to get max weight possible for unimportant

ASK_UPDATE = False  # Ask for confirmation before updating the playlist
FUZZY_DUPE_CHECKING = True

creds = pl.get_credentials()
spotify = pl.get_spotify(creds["spotify"])

playlists = [pl.Playlist(spotify, None, id_, True) for id_ in FAMILY_PLAYLISTS]
cum_wait = OrderedDict((player.id, 0) for player in playlists)

playlist_roadtrip = pl.Playlist(spotify, "Jacob and Reece Shuffled")

playlist_blacklist = None
if BLACK_LIST_PLAYLIST:
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
last_play = {playlist_id: 0 for playlist_id in FAMILY_PLAYLISTS}
total_cumulative_playtime = {playlist_id: 0 for playlist_id in FAMILY_PLAYLISTS}
total_cumulative_plays = {playlist_id: 0 for playlist_id in FAMILY_PLAYLISTS}
main_end = False
while playlists:
    # TODO: Clean option selection by setting weights to 0 instead of removing
    playlist_options = []
    for playlist_id in FAMILY_PLAYLISTS[:MAIN_PLAYLISTS]:
        if playlist_id not in cum_wait:
            continue
        wait = last_play[playlist_id]
        if wait > MAX_WAIT:
            playlist = [
                playlist for playlist in playlists if playlist.id == playlist_id
            ][0]
            playlist_options.append(playlist)

    if playlist_options:
        option_names = [
            (
                FAMILY_PLAYLISTS_NAMES[FAMILY_PLAYLISTS.index(p.id)],
                round(last_play[p.id], 2),
            )
            for p in playlist_options
        ]
        print(f"Playlist choice limited to wait times > {MAX_WAIT}: ", option_names)
    else:
        playlist_options = playlists[:]

    if run >= MAX_RUN:
        for playlist in playlist_options:
            if last_playlist == playlist.id and len(playlist_options) > 1:
                playlist_options.remove(playlist)

    option_weights = list(
        weight ** SCALE + 1 for weight in [cum_wait[p.id] for p in playlist_options]
    )

    if SUPPRESS_UNIMPORTANT:
        first_unimportant = None
        for weight_num, option in enumerate(playlist_options):
            if FAMILY_PLAYLISTS.index(option.id) >= MAIN_PLAYLISTS:
                # Suppress weight of unimportant playlists
                if first_unimportant is None:
                    first_unimportant = weight_num
                option_weights[weight_num] = min(
                    option_weights[weight_num],
                    max(option_weights[:first_unimportant]) * MAX_SCALE_UNIMPORTANT,
                )

    playlist_chosen = random.choices(playlist_options, weights=option_weights)[0]

    playlist_author = FAMILY_PLAYLISTS_NAMES[FAMILY_PLAYLISTS.index(playlist_chosen.id)]

    chosen_playlist_static_index = FAMILY_PLAYLISTS.index(playlist_chosen.id)
    weights = None
    if PLAYLISTS_ORDERED[chosen_playlist_static_index]:
        weights = [
            weight ** ORDERED_BIAS + 1 for weight in range(len(playlist_chosen), 0, -1)
        ]

    song = random.choices(playlist_chosen.tracks, weights=weights)[0]
    playlist_chosen -= song
    duration = song.duration_ms / 1000 / 60

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
                cum_before.append(
                    f"{get_symbol(playlist_id_wait, wait)} {format_p(wait)}"
                )
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

    if BLACK_LIST_PLAYLIST and song in playlist_blacklist:
        print(f"Song for {playlist_author} already played in blacklist:", song)
        continue
    if BLACK_LIST_PLAYLIST and FUZZY_DUPE_CHECKING:
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

    if playlist_chosen.id != last_playlist:
        run = 1
        last_playlist = playlist_chosen.id
    else:
        run += 1

    person_song_map.append(
        (
            playlist_author,
            last_play[playlist_chosen.id]/1440,
            total_cumulative_playtime[playlist_chosen.id]/1440,
            total_cumulative_plays[playlist_chosen.id],
            len(playlist_chosen),
            song.name,
            song.artist,
            song.album,
            duration/1440,
            sum((s.duration_ms/1000/60 for s in songs))/1440,
            main_end,
        )
    )

    total_cumulative_playtime[playlist_chosen.id] += duration
    total_cumulative_plays[playlist_chosen.id] += 1

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
line_format = "{:<10}\t{:<20}\t{:<20}\t{:<20}\t{:<20}\t{:<50.50}\t{:<20.20}\t{:<50.50}\t{:<20}\t{:<20}\t{:<4}"
header = line_format.format(
    "author",
    "waited",
    "author playtime",
    "songs chosen",
    "songs left",
    "song name",
    "artist",
    "album",
    "song len.",
    "total playtime",
    "END",
)
print(header)
with open(SONG_LIST_FILE, "w", encoding="utf-8") as f:
    f.write("")
with open(SONG_LIST_FILE, "a", encoding="utf-8") as f:
    f.write(header + "\n")
    for song_info in person_song_map:
        line = line_format.format(*song_info)
        f.write(line + "\n")
        print(line)

end_index = 0
for i, song_info in enumerate(person_song_map):
    if song_info[-1]:
        end_index = i
        break

wait_times = [
    time
    for time in sorted(
        person_song_map[: end_index + 1], key=lambda s: float(s[1]), reverse=True
    )
    if FAMILY_PLAYLISTS_NAMES.index(time[0]) < MAIN_PLAYLISTS
]

wait_times_alone = [float(info[1]) for info in wait_times]
print("\n5 greatest wait times")
print(wait_times[:5])
print("\n Average wait time:", sum(wait_times_alone) / len(wait_times) * 1440)
print("\n Most common wait time:", mode([round(time * 1440) for time in wait_times_alone]))


while ASK_UPDATE and not input("UPDATE REMOTE? ('YES')") == "YES":
    pass

playlist_roadtrip.publish(public=True)
