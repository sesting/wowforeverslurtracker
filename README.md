# Slur Tracker client

This repository contains the WoW Forever EU addon and its desktop companion.

The addon tracks configured terms in public chat. The companion uploads saved
counts and downloads the shared leaderboard. Open it in game with `/st`.

The companion connects to `https://notaracistaddon.airdns.org:35607` using
the bundled public certificate. Configure terms in `SlurTracker/Terms.lua`.
See the [installer build instructions](packaging/README.md).

## Refreshing the shared leaderboard

1. Leave the companion running and type `/reload` in WoW. This saves the addon's
   current counters to disk and loads the leaderboard snapshot already on disk.
2. Give the companion a few seconds to upload those counts and download the
   updated shared leaderboard.
3. Type `/reload` again, then open `/st` to see the newly downloaded snapshot.

The companion checks for saved counters about every five seconds and refreshes
the shared leaderboard about once a minute while syncing. If it has already
downloaded a newer snapshot, one `/reload` is enough to display it. Changing zones
or reopening `/st` keeps the snapshot WoW already loaded. Logging out also saves
your counters, and logging back in loads the latest downloaded snapshot.
