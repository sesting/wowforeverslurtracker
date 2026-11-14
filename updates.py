"""Download a platform installer from a published GitHub release."""
from hashlib import sha256
import json
from pathlib import Path
import platform
import re
import subprocess
import sys
from tempfile import NamedTemporaryFile
from urllib.request import Request, urlopen

REPO = "sesting/wowforeverslurtracker"
LIMIT = 512 * 1024 * 1024


def version(value):
    if not re.fullmatch(r"v?[0-9]+\.[0-9]+\.[0-9]+", value):
        raise ValueError("Invalid release version")
    return tuple(map(int, value.lstrip("v").split(".")))


def installer(tag):
    if sys.platform == "win32" and platform.machine().lower() in ("amd64", "x86_64"):
        return "SlurTracker-Windows-x64-Setup.exe"
    if sys.platform == "darwin":
        return "SlurTracker-macOS.pkg"
    if sys.platform.startswith("linux"):
        distro = platform.freedesktop_os_release()
        families = {distro.get("ID"), *distro.get("ID_LIKE", "").split()}
        if families & {"fedora", "rhel", "centos"}:
            return f"slur-tracker-{tag}-1.noarch.rpm"
        if families & {"debian", "ubuntu"}:
            return f"slur-tracker_{tag}_all.deb"
    raise ValueError("No matching installer for this system")


def download_update(current, directory):
    request = Request(f"https://api.github.com/repos/{REPO}/releases/latest",
                      headers={"Accept": "application/vnd.github+json"})
    with urlopen(request, timeout=15) as response:
        release = json.loads(response.read(1024 * 1024))
    tag = release["tag_name"]
    if release["draft"] or release["prerelease"] or version(tag) <= version(current):
        return None
    name = installer(tag.lstrip("v"))
    asset = next((item for item in release["assets"] if item["name"] == name), None)
    url = f"https://github.com/{REPO}/releases/download/{tag}/{name}"
    if not asset or asset["browser_download_url"] != url:
        raise ValueError("This release has no matching installer")
    digest = asset.get("digest") or ""
    size = asset["size"]
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest) or not 0 < size <= LIMIT:
        raise ValueError("Installer verification data is missing or invalid")

    folder = Path(directory) / tag
    folder.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=folder, delete=False) as file:
        temporary = Path(file.name)
        try:
            checksum, length = sha256(), 0
            with urlopen(url, timeout=30) as response:
                while chunk := response.read(1024 * 1024):
                    length += len(chunk)
                    if length > size:
                        raise ValueError("Installer exceeds the published size")
                    checksum.update(chunk)
                    file.write(chunk)
            if length != size or "sha256:" + checksum.hexdigest() != digest:
                raise ValueError("Installer failed verification")
        except BaseException:
            file.close()
            temporary.unlink(missing_ok=True)
            raise
    target = folder / name
    try:
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def launch_installer(path):
    if sys.platform == "win32":
        subprocess.Popen([str(path)])
    else:
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(path)])
