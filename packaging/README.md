# Build the desktop packages

Routine development uses `make check` from the repository root. Build
installers when preparing a release. Pass just `linux`, `windows`, or
`macos` to build a single platform.

Run `build.py` on a Linux build machine with Python 3.12+, PySide6,
ImageMagick, NSIS, rpmbuild, GNU cpio and bomutils' mkbom. Windows uses
Python's official 3.14.10 x64 embeddable ZIP. Place the following verified
downloads in the directory passed as `--dependencies`:

- PySide6 Essentials and Shiboken6 6.12.0 wheels for `win_amd64` and
  `macosx_14_0_universal2`, from PyPI.
- Astral python-build-standalone 20261110 CPython 3.14.10
  `install_only_stripped` macOS archives for aarch64 and x86_64.

Pass the public TLS certificate and the local release term list. The output never
requires the server's TLS key, installation tokens, or addon sealing keys.

```sh
python3 packaging/build.py --certificate cert.pem \
  --terms .private/Terms.lua \
  --dependencies /path/to/downloads \
  --windows-runtime /path/to/python-3.14.10-embed-amd64.zip \
  --output /path/to/installers --work /path/to/new-build-directory \
  linux windows macos
```

The macOS PKG installs a dual-architecture application in /Applications.
The Windows NSIS installer installs per user. The Linux packages install the
app and its launcher system-wide. All four packages configure the addon
under the current user's WoW folder when the companion's Settings are saved.
