"""Desktop companion for Slur Tracker."""
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import secrets
import ssl
import sys
from tempfile import NamedTemporaryFile
from threading import Thread
import time
from urllib.request import HTTPSHandler, ProxyHandler, Request, build_opener

from PySide6.QtCore import QLockFile, QStandardPaths, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QLabel,
    QLineEdit, QMenu, QMessageBox, QPushButton, QSystemTrayIcon, QVBoxLayout,
    QWidget,
)

from sync import NoRedirect, read_seal, write_board

ROOT = Path(__file__).resolve().parent
SERVER = "https://notaracistaddon.airdns.org:35607"
CONNECTED = "successful connection: tracking slurs"
WAITING = "waiting for addon"
FAILED = "connection fails: not tracking slurs"
HEX_KEY = re.compile(r"[0-9a-f]{64}")


def wow_candidates():
    home = Path.home()
    roots = [home / "World of Warcraft"]
    if sys.platform == "win32":
        for name in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432"):
            if os.environ.get(name):
                roots.append(Path(os.environ[name]) / "World of Warcraft")
    elif sys.platform == "darwin":
        roots.extend([Path("/Applications/World of Warcraft"),
                      home / "Applications/World of Warcraft"])
    else:
        prefixes = [home / ".wine"]
        if os.environ.get("WINEPREFIX"):
            prefixes.append(Path(os.environ["WINEPREFIX"]))
        for pattern in (
            "Games/*", ".local/share/bottles/bottles/*",
            ".var/app/com.usebottles.bottles/data/bottles/bottles/*",
            ".local/share/Steam/steamapps/compatdata/*/pfx",
            ".steam/steam/steamapps/compatdata/*/pfx",
            ".var/app/com.valvesoftware.Steam/data/Steam/steamapps/compatdata/*/pfx",
        ):
            prefixes.extend(home.glob(pattern))
        for prefix in prefixes:
            for folder in ("Program Files (x86)", "Program Files", "Games", ""):
                roots.append(prefix / "drive_c" / folder / "World of Warcraft")
    found = set()
    for root in roots:
        for edition in (root, *root.glob("_*")):
            if is_wow_folder(edition) and (
                "forever" in edition.name.lower() or saved_files(edition)
                or (edition / "Interface/AddOns/SlurTracker/SlurTracker.toc").is_file()
            ):
                found.add(edition.resolve())
    return sorted(found)


def is_wow_folder(folder):
    return (folder / "WTF").is_dir() and (folder / "Interface").is_dir() or any(
        (folder / executable).exists()
        for executable in ("Wow.exe", "WowClassic.exe", "World of Warcraft.app",
                           "World of Warcraft Classic.app")
    )


def saved_files(game):
    return sorted((game / "WTF/Account").glob("*/SavedVariables/SlurTracker.lua"))


def install_addon(game, key=None):
    addon = game / "Interface/AddOns/SlurTracker"
    addon.mkdir(parents=True, exist_ok=True)
    packaged = ROOT / "SlurTracker"
    for filename in ("Seal.lua", "Tracker.lua", "Dashboard.lua", "SealKey.lua", "Leaderboard.lua"):
        target = addon / filename
        if filename in ("SealKey.lua", "Leaderboard.lua") and target.exists():
            continue
        shutil.copyfile(packaged / filename, target)
    terms = (packaged / "Terms.lua").read_bytes()
    digest = sha256(terms).hexdigest()
    stamp = addon / ".slurtracker-terms"
    if not stamp.is_file() or stamp.read_text(encoding="ascii") != digest or not (addon / "Terms.lua").is_file():
        (addon / "Terms.lua").write_bytes(terms)
        stamp.write_text(digest, encoding="ascii")
    shutil.copyfile(packaged / "SlurTracker.toc", addon / "SlurTracker.toc")
    if key:
        with NamedTemporaryFile(mode="w", encoding="ascii", dir=addon, delete=False) as file:
            file.write(f'SlurTrackerSealKey = "{key}"\n')
            temporary = Path(file.name)
        try:
            temporary.replace(addon / "SealKey.lua")
        finally:
            temporary.unlink(missing_ok=True)
    return addon


def status_icon():
    image = QPixmap(64, 64)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#26385c"))
    painter.drawRoundedRect(2, 2, 60, 60, 14, 14)
    painter.setPen(QColor("#ffffff"))
    font = QFont()
    font.setPixelSize(29)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(image.rect(), Qt.AlignmentFlag.AlignCenter, "ST")
    painter.end()
    return QIcon(image)


class Setup(QDialog):
    def __init__(self, parent, config):
        super().__init__(parent)
        self.setWindowTitle("Slur Tracker setup")
        self.config = config
        self.game = QLineEdit(config.get("game", ""))
        choose_game = QPushButton("Choose WoW folder")
        choose_game.clicked.connect(self.choose_game)
        form = QFormLayout(self)
        form.addRow("WoW Forever folder", self.game)
        form.addRow("", choose_game)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.validate)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)
        self.resize(465, self.sizeHint().height())

    def choose_game(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose the WoW Forever game folder",
                                                   self.game.text())
        if folder:
            self.game.setText(folder)

    def validate(self):
        game = Path(self.game.text().strip()).expanduser()
        try:
            if not self.game.text().strip() or not is_wow_folder(game):
                raise ValueError("Choose the WoW Forever game folder.")
            if self.config.get("game") != str(game.resolve()):
                self.config.pop("save", None)
            self.config["game"] = str(game.resolve())
            install_addon(game, self.config.get("seal_key"))
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Slur Tracker", str(error))
            return
        self.accept()


class Companion(QWidget):
    finished = Signal(str, int)
    enrolled = Signal(int)

    def __init__(self, config_path):
        super().__init__()
        self.config_path = config_path
        try:
            self.config = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.config = {}
        self.generation = 0
        self.busy = False
        self.last_seal = None
        self.next_board = 0
        self.setWindowTitle("Slur Tracker")
        self.setWindowIcon(status_icon())
        self.label = QLabel(WAITING)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        settings = QPushButton("Settings")
        settings.clicked.connect(self.setup)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 18)
        layout.addWidget(self.label)
        layout.addWidget(settings, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.setFixedWidth(345)
        self.tray = QSystemTrayIcon(self.windowIcon(), self)
        self.tray.setToolTip(f"Slur Tracker — {WAITING}")
        self.menu = QMenu(self)
        self.menu.addAction("Show Slur Tracker", self.show_window)
        self.menu.addAction("Settings", self.setup)
        self.menu.addAction("Quit", self.quit)
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self.activate_tray)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()
        self.finished.connect(self.update_status)
        self.enrolled.connect(self.complete_enrolment)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.timer.start(5000)
        if not self.config.get("game"):
            candidates = wow_candidates()
            if len(candidates) == 1:
                self.config["game"] = str(candidates[0])
            QTimer.singleShot(0, self.setup)
        else:
            try:
                install_addon(Path(self.config["game"]), self.config.get("seal_key"))
            except OSError:
                QTimer.singleShot(0, self.setup)
        QTimer.singleShot(0, self.poll)

    def setup(self):
        self.show_window()
        dialog = Setup(self, self.config.copy())
        if dialog.exec():
            self.config = dialog.config
            self.prepare_enrolment()
            try:
                self.save_config()
            except OSError as error:
                QMessageBox.warning(self, "Slur Tracker", str(error))
                return
            self.generation += 1
            self.last_seal = None
            self.next_board = 0
            self.poll()

    def prepare_enrolment(self):
        if self.config.get("game") and not HEX_KEY.fullmatch(self.config.get("token", "")):
            self.config.update(token=secrets.token_hex(32), seal_key=secrets.token_hex(32),
                               enrolment_pending=True)

    def save_config(self):
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.config_path.parent,
                                delete=False) as file:
            temporary = Path(file.name)
            json.dump(self.config, file)
        try:
            temporary.replace(self.config_path)
        finally:
            temporary.unlink(missing_ok=True)

    def poll(self):
        if not self.busy:
            self.prepare_enrolment()
            if self.config.get("enrolment_pending"):
                try:
                    self.save_config()
                except OSError:
                    self.update_status(FAILED, self.generation)
                    return
            self.busy = True
            Thread(target=self.check, args=(self.config.copy(), self.generation), daemon=True).start()

    def check(self, config, generation):
        status = FAILED
        try:
            context = ssl.create_default_context(cafile=str(ROOT / "cert.pem"))
            opener = build_opener(ProxyHandler({}), HTTPSHandler(context=context), NoRedirect())
            with opener.open(SERVER + "/health", timeout=8):
                pass
            status = WAITING
            token = config.get("token", "")
            if not config.get("game") or not HEX_KEY.fullmatch(token):
                return
            game = Path(config["game"])
            if config.get("enrolment_pending"):
                status = FAILED
                key = config["seal_key"]
                with opener.open(Request(SERVER + "/enrol", (token + key).encode()), timeout=10):
                    pass
                if generation != self.generation:
                    return
                install_addon(game, key)
                self.enrolled.emit(generation)
                status = WAITING
            files = [Path(config["save"])] if config.get("save") else saved_files(game)
            if len(files) != 1:
                return
            try:
                seal = read_seal(files[0])
            except (OSError, ValueError):
                return
            status = FAILED
            headers = {"Authorization": "Bearer " + token, "Content-Type": "application/octet-stream"}
            changed = seal != self.last_seal
            if changed:
                with opener.open(Request(SERVER + "/sync", seal, headers), timeout=10):
                    pass
                if generation == self.generation:
                    self.last_seal = seal
            if changed or time.monotonic() >= self.next_board:
                with opener.open(Request(SERVER + "/leaderboard", headers=headers), timeout=10) as response:
                    board = json.load(response)
                if generation == self.generation:
                    write_board(game / "Interface/AddOns/SlurTracker", board)
                    self.next_board = time.monotonic() + 60
            status = CONNECTED
        except (OSError, ValueError):
            pass
        finally:
            self.finished.emit(status, generation)

    def complete_enrolment(self, generation):
        if generation == self.generation:
            self.config.pop("enrolment_pending", None)
            try:
                self.save_config()
            except OSError:
                self.config["enrolment_pending"] = True

    def update_status(self, status, generation):
        self.busy = False
        if generation != self.generation:
            self.poll()
            return
        self.label.setText(status)
        self.tray.setToolTip(f"Slur Tracker — {status}")

    def quit(self):
        self.tray.hide()
        QApplication.instance().quit()

    def show_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def activate_tray(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger,
                      QSystemTrayIcon.ActivationReason.DoubleClick):
            self.show_window()

    def changeEvent(self, event):
        super().changeEvent(event)
        if self.isMinimized() and self.tray.isVisible():
            QTimer.singleShot(0, self.hide)

    def closeEvent(self, event):
        if self.tray.isVisible():
            event.ignore()
            self.hide()
        else:
            super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("Slur Tracker")
    base = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation))
    base.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(base / "companion.lock"))
    if not lock.tryLock(0):
        sys.exit(0)
    window = Companion(base / "settings.json")
    window.show()
    sys.exit(app.exec())
