# Tasks

- [ ] Determine what I want out of this program and how best to approach it  
- [ ] Only query library as often as necessary -- get playlists and saved songs once at start

Basic smart playlists

- fav instrumental/bands, etc
- update on cronjob on pi

Handle local files

Generate playlists with songs from albums with at least one song I listen to a lot  
Generate shuffled playlists every so often with song likelihoods based on number of listens from last.fm

Watch for playlists with command names

- e.g. a "/gen shuffle" playlist triggers above feature and deletes command playlist (check in separate cronjob on pi frequently)
- Better interface?

Handle duplicate songs

- Remove songs with same track id
- String distance matching?
- Perhaps email when finding potential dupes?

Clean faved songs (remove potential duplicates)

Tracked playlists which remove songs as you listen and moves them to a corresponding history playlist

Backup playlists to rpi

- Restore playlists from backups

Checkout genre seeds and recommendations

Checkout entire documentation

Place smart playlists into folder