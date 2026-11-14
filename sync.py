"""Watch WoW's saved counters and sync them to the shared leaderboard."""
import argparse
import json
import os
from pathlib import Path
import re
import ssl
import sys
import time
from urllib.parse import urlsplit
from urllib.request import HTTPSHandler, HTTPRedirectHandler, Request, build_opener

MAX_SAVE_BYTES = 1_030_000


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def read_seal(path):
    with path.open("rb") as file:
        source = file.read(MAX_SAVE_BYTES + 1)
    if len(source) > MAX_SAVE_BYTES:
        raise ValueError("SavedVariables file is too large")
    match = re.fullmatch(rb'\s*SlurTrackerSealed\s*=\s*"(v1:[0-9a-f]{128,1024128})"\s*',
                         source[3:] if source.startswith(b"\xef\xbb\xbf") else source)
    if not match or len(match[1]) % 2 != 1:
        raise ValueError("Waiting for a complete sealed Slur Tracker save")
    return match[1]


def write_board(folder, board):
    def quote_lua(text):
        return '"' + "".join(f"\\{byte:03d}" for byte in text.encode()) + '"'

    lines = [f"SlurTrackerLeaderboardUpdated = {int(time.time())}", "SlurTrackerLeaderboard = {"]
    for row in board:
        if not row.get("ruleset"):
            continue
        terms = ", ".join(f"[{quote_lua(term)}] = {int(count)}"
                          for term, count in row["terms"].items())
        lines.append(f'  {{player = {quote_lua(row["player"])}, '
                     f'ruleset = {quote_lua(row["ruleset"])}, total = {int(row["total"])}, terms = {{{terms}}}}},')
    lines.append("}")
    target = folder / "Leaderboard.lua"
    temporary = target.with_suffix(".tmp")
    temporary.write_text("\n".join(lines) + "\n", encoding="ascii")
    temporary.replace(target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("saved_variables", type=Path)
    parser.add_argument("--url", default="https://notaracistaddon.airdns.org:35607")
    parser.add_argument("--addon", type=Path, help="Installed SlurTracker folder")
    parser.add_argument("--ca", required=True, help="Trusted tracker certificate")
    parser.add_argument("--once", action="store_true", help="Sync once and exit")
    args = parser.parse_args()
    url = urlsplit(args.url)
    if (url.scheme != "https" or not url.hostname or url.username is not None
            or url.path not in ("", "/") or url.query or url.fragment):
        parser.error("enter an HTTPS server address without credentials or a path")
    token = os.environ.get("TRACKER_TOKEN", "")
    if not re.fullmatch(r"[0-9a-f]{64}", token):
        parser.error("set TRACKER_TOKEN to your installation token")
    if args.addon and not (args.addon / "SlurTracker.toc").is_file():
        parser.error("--addon must point to the installed SlurTracker folder")
    context = ssl.create_default_context(cafile=args.ca)
    opener = build_opener(HTTPSHandler(context=context), NoRedirect())
    headers = {"Authorization": "Bearer " + token, "Content-Type": "application/octet-stream"}
    base = args.url.rstrip("/")
    last_seal = None
    next_refresh = 0
    last_error = None
    while True:
        try:
            seal = read_seal(args.saved_variables)
            changed = seal != last_seal
            if changed:
                request = Request(base + "/sync", seal, headers)
                with opener.open(request, timeout=12):
                    pass
                last_seal = seal
                print("Counters synced.", flush=True)
            if (args.addon or args.once) and (changed or time.monotonic() >= next_refresh):
                with opener.open(Request(base + "/leaderboard", headers=headers), timeout=12) as response:
                    board = json.load(response)
                if args.addon:
                    write_board(args.addon, board)
                if args.once:
                    for row in board:
                        details = ", ".join(f"{term} {count}" for term, count in sorted(row["terms"].items()))
                        print(f'{row.get("ruleset", "")}  {row["player"]}  {row["total"]}  ({details})')
                next_refresh = time.monotonic() + 60
            last_error = None
            if args.once:
                return 0
            time.sleep(5)
        except (OSError, ValueError) as error:
            message = str(error)
            if message != last_error:
                print(message, file=sys.stderr, flush=True)
            last_error = message
            if args.once:
                return 1
            time.sleep(15)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
