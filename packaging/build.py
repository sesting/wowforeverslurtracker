"""Build distribution installers on Linux from pre-fetched platform runtimes."""
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import io
import os
from pathlib import Path
import plistlib
import shutil
import struct
import subprocess
import sys
import tarfile
import xml.etree.ElementTree as xml
import zipfile
import zlib

PACKAGING = Path(__file__).resolve().parent
SOURCE = PACKAGING.parent
VERSION = "0.3.6"
MAC_ID = "org.slurtracker.client"


def copy_payload(target, cert, terms):
    target.mkdir(parents=True)
    for name in ("companion.py", "sync.py", "README.md"):
        shutil.copyfile(SOURCE / name, target / name)
    shutil.copyfile(cert, target / "cert.pem")
    shutil.copyfile(PACKAGING / "qt-notice.txt", target / "qt-notice.txt")
    addon = target / "SlurTracker"
    addon.mkdir()
    for name in ("SlurTracker.toc", "Leaderboard.lua", "Seal.lua", "Tracker.lua", "Dashboard.lua"):
        shutil.copyfile(SOURCE / "SlurTracker" / name, addon / name)
    shutil.copyfile(terms, addon / "Terms.lua")
    (addon / "SealKey.lua").write_text("-- Import the private installation key in Settings.\n")


def icon_png(path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, str(SOURCE))
    from companion import QApplication, status_icon
    app = QApplication.instance() or QApplication([])
    if not status_icon().pixmap(64, 64).save(str(path), "PNG"):
        raise RuntimeError("could not render the ST icon")
    return app


def install_wheels(deps, platform, target):
    for name in ("pyside6_essentials", "shiboken6"):
        wheel, = deps.glob(f"{name}-6.12.0-*-{platform}.whl")
        with zipfile.ZipFile(wheel) as archive:
            archive.extractall(target)


def windows(args, build, icon):
    stage = build / "windows"
    copy_payload(stage, args.certificate, args.terms)
    runtime_zip = args.windows_runtime
    digest = hashlib.sha256(runtime_zip.read_bytes()).hexdigest()
    if digest != "90905e64a840557d8c1bc4f5b74db3d7ee85e3ffb217611cac1c7813acea4159":
        raise ValueError("unexpected Windows runtime checksum")
    runtime = stage / "runtime"
    with zipfile.ZipFile(runtime_zip) as archive:
        archive.extractall(runtime)
    path_config, = runtime.glob("python*._pth")
    path_config.write_text(path_config.read_text() + "\n..\n")
    install_wheels(args.dependencies, "win_amd64", runtime)
    ico = stage / "st.ico"
    subprocess.run(["magick", str(icon), "-define", "icon:auto-resize=64,48,32,16", str(ico)],
                   check=True)
    out = args.output / "SlurTracker-Windows-x64-Setup.exe"
    subprocess.run([args.makensis, "-V2", f"-DVERSION={VERSION}", f"-DOUTFILE={out}",
                    f"-DICONFILE={ico}", f"-DPAYLOAD={stage}", str(PACKAGING / "windows.nsi")],
                   check=True)
    return out


def write_ar(target, members):
    with target.open("wb") as file:
        file.write(b"!<arch>\n")
        for name, data in members:
            header = f"{name + '/':16}{0:<12}{0:<6}{0:<6}{'100644':8}{len(data):<10}`\n"
            file.write(header.encode("ascii"))
            file.write(data)
            if len(data) % 2:
                file.write(b"\n")


def tar_bytes(root):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz", format=tarfile.GNU_FORMAT) as archive:
        def owner(info):
            info.uid = info.gid = 0
            info.uname = info.gname = "root"
            return info
        archive.add(root, arcname=".", filter=owner)
    return stream.getvalue()


def linux(args, build, icon):
    stage = build / "linux"
    copy_payload(stage / "usr/share/slur-tracker", args.certificate, args.terms)
    command = stage / "usr/bin/slur-tracker"
    command.parent.mkdir(parents=True)
    command.write_text('#!/bin/sh\nexec /usr/bin/python3 /usr/share/slur-tracker/companion.py "$@"\n')
    command.chmod(0o755)
    for source, relative in (
        (PACKAGING / "linux.desktop", "usr/share/applications/slur-tracker.desktop"),
        (icon, "usr/share/icons/hicolor/64x64/apps/slur-tracker.png"),
    ):
        target = stage / relative
        target.parent.mkdir(parents=True)
        shutil.copyfile(source, target)
    control = build / "deb-control"
    control.mkdir()
    (control / "control").write_text(
        "Package: slur-tracker\n"
        f"Version: {VERSION}\n"
        "Architecture: all\n"
        "Maintainer: Slur Tracker\n"
        "Section: games\nPriority: optional\n"
        "Depends: python3 (>= 3.10), python3-pyside6.qtwidgets\n"
        "Description: WoW Forever EU Slur Tracker companion\n"
        " Syncs sealed counter snapshots from a WoW compatibility prefix.\n")
    deb = args.output / f"slur-tracker_{VERSION}_all.deb"
    write_ar(deb, [("debian-binary", b"2.0\n"), ("control.tar.gz", tar_bytes(control)),
                   ("data.tar.gz", tar_bytes(stage))])

    rpm_root = build / "rpm"
    rpm_root.mkdir()
    spec = rpm_root / "slur-tracker.spec"
    spec.write_text(f"""Name: slur-tracker
Version: {VERSION}
Release: 1
Summary: WoW Forever EU Slur Tracker companion
License: LicenseRef-Proprietary
BuildArch: noarch
Requires: python3 >= 3.10
Requires: python3-pyside6
%global __brp_python_bytecompile %{{nil}}

%description
Syncs sealed counter snapshots from a WoW compatibility prefix.

%install
mkdir -p "%{{buildroot}}"
cp -a "{stage}/." "%{{buildroot}}"

%files
/usr/bin/slur-tracker
/usr/share/slur-tracker
/usr/share/applications/slur-tracker.desktop
/usr/share/icons/hicolor/64x64/apps/slur-tracker.png
""")
    subprocess.run(["rpmbuild", "-bb", "--define", f"_topdir {rpm_root}", str(spec)], check=True)
    rpm, = rpm_root.glob("RPMS/noarch/*.rpm")
    output = args.output / rpm.name
    shutil.copyfile(rpm, output)
    return deb, output


def write_xar(target, files):
    toc = xml.SubElement(root := xml.Element("xar"), "toc")
    xml.SubElement(toc, "creation-time").text = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    checksum = xml.SubElement(toc, "checksum", style="sha1")
    xml.SubElement(checksum, "offset").text = "0"
    xml.SubElement(checksum, "size").text = "20"
    offset = 20
    for index, path in enumerate(files, start=1):
        item = xml.SubElement(toc, "file", id=str(index))
        for name, value in (("name", path.name), ("type", "file"), ("mode", "0644"),
                            ("uid", "0"), ("gid", "0"), ("user", "root"), ("group", "wheel")):
            xml.SubElement(item, name).text = value
        data = xml.SubElement(item, "data")
        size = path.stat().st_size
        for name, value in (("length", size), ("offset", offset), ("size", size)):
            xml.SubElement(data, name).text = str(value)
        xml.SubElement(data, "encoding", style="application/octet-stream")
        with path.open("rb") as file:
            digest = hashlib.file_digest(file, "sha1").hexdigest()
        for name in ("archived-checksum", "extracted-checksum"):
            xml.SubElement(data, name, style="sha1").text = digest
        offset += size
    plain = xml.tostring(root, encoding="UTF-8", xml_declaration=True)
    compressed = zlib.compress(plain)
    with target.open("wb") as output:
        output.write(struct.pack(">4sHHQQI", b"xar!", 28, 1, len(compressed), len(plain), 1))
        output.write(compressed)
        output.write(hashlib.sha1(compressed).digest())
        for path in files:
            with path.open("rb") as file:
                shutil.copyfileobj(file, output)


def macos(args, build, icon):
    stage = build / "macos"
    app = stage / "Applications/Slur Tracker.app"
    contents = app / "Contents"
    resources = contents / "Resources"
    copy_payload(resources, args.certificate, args.terms)
    launcher = contents / "MacOS/SlurTracker"
    launcher.parent.mkdir()
    shutil.copyfile(PACKAGING / "macos-launcher", launcher)
    launcher.chmod(0o755)
    (contents / "Info.plist").write_bytes(plistlib.dumps({
        "CFBundleIdentifier": MAC_ID,
        "CFBundleName": "Slur Tracker",
        "CFBundleDisplayName": "Slur Tracker",
        "CFBundleExecutable": "SlurTracker",
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": VERSION,
        "CFBundleVersion": VERSION,
        "CFBundleIconFile": "st.icns",
        "LSMinimumSystemVersion": "14.0",
        "NSHighResolutionCapable": True,
    }))
    png = icon.read_bytes()
    (resources / "st.icns").write_bytes(
        struct.pack(">4sI4sI", b"icns", 16 + len(png), b"icp6", 8 + len(png)) + png)
    for cpu, suffix in (("arm64", "aarch64"), ("x86_64", "x86_64")):
        archive, = args.dependencies.glob(
            f"cpython-3.14.10+20261110-{suffix}-apple-darwin-install_only_stripped.tar.gz")
        with tarfile.open(archive) as tar:
            tar.extractall(resources, filter="data")
        (resources / "python").rename(resources / f"runtime-{cpu}")
    install_wheels(args.dependencies, "macosx_14_0_universal2", resources / "qt")

    package = build / "mac-pkg"
    package.mkdir()
    paths = [Path("."), *(path.relative_to(stage) for path in sorted(stage.rglob("*")))]
    raw = b"".join(os.fsencode(path) + b"\0" for path in paths)
    with (package / "Payload").open("wb") as file:
        with gzip.GzipFile(fileobj=file, mode="wb", compresslevel=6, mtime=0) as compressed:
            listing = package / "paths"
            listing.write_bytes(raw)
            with listing.open("rb") as source:
                with subprocess.Popen(["cpio", "--quiet", "--null", "-o", "-H", "odc", "--owner=0:0"], cwd=stage,
                                      stdin=source, stdout=subprocess.PIPE) as process:
                    shutil.copyfileobj(process.stdout, compressed)
                    if process.wait():
                        raise RuntimeError("cpio could not write the macOS payload")
    subprocess.run([args.mkbom, "-u", "0", "-g", "0", str(stage), str(package / "Bom")], check=True)
    info = xml.Element("pkg-info", {"format-version": "2", "identifier": MAC_ID,
                                   "version": VERSION, "install-location": "/",
                                   "auth": "root", "overwrite-permissions": "true"})
    size = sum((stage / path).lstat().st_size for path in paths)
    xml.SubElement(info, "payload", {"numberOfFiles": str(len(paths)),
                                    "installKBytes": str((size + 1023) // 1024)})
    xml.ElementTree(info).write(package / "PackageInfo", encoding="utf-8", xml_declaration=True)
    output = args.output / "SlurTracker-macOS.pkg"
    write_xar(output, [package / name for name in ("Bom", "PackageInfo", "Payload")])
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--terms", type=Path, default=SOURCE / "SlurTracker/Terms.lua",
                        help="Term list to include in the release")
    parser.add_argument("--certificate", type=Path, required=True)
    parser.add_argument("--dependencies", type=Path, required=True)
    parser.add_argument("--windows-runtime", type=Path)
    parser.add_argument("--makensis", default="makensis")
    parser.add_argument("--mkbom", default="mkbom")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("platform", nargs="+", choices=("linux", "windows", "macos"))
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    build = args.work.resolve()
    build.mkdir(parents=True)
    icon = build / "st.png"
    app = icon_png(icon)
    for target in args.platform:
        result = globals()[target](args, build, icon)
        for path in result if isinstance(result, tuple) else (result,):
            print(f"{path.name}: {path.stat().st_size:,} bytes", flush=True)


if __name__ == "__main__":
    main()
