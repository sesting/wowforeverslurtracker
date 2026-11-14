# Slur Tracker client

This repository contains the WoW Forever EU addon and its desktop companion.

The addon tracks configured terms in public chat. The companion uploads saved
counts and downloads the shared leaderboard. Open it in game with `/st`.

The companion connects to `https://notaracistaddon.airdns.org:35607` using
the bundled public certificate. Configure terms in `SlurTracker/Terms.lua`.
See the [installer build instructions](packaging/README.md).
