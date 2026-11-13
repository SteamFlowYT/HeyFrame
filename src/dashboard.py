#!/usr/bin/env python3
"""Dedicated Hey Frame SteamVR dashboard tab, independent of SFRecorder's tab.

Runs via the existing SFRecorder isolated Python (which has pyopenvr and Pillow
with the ARM64 Valve OpenVR loader). On/off buttons invoke the safe Hey Frame
CLI. No evdev/uinput, no global volume mutations, no controller spoofing.
"""
from __future__ import annotations
import ctypes
from datetime import datetime
import json
import os
from pathlib import Path
import queue
import shutil
import socket
import stat
import subprocess
import sys
import threading
import time

from glados_mode import get_mode

APP_KEY = 'steamflow.heyframe.dashboard'
BIN = Path.home() / '.local' / 'bin' / 'hey-frame'
SYSPY = Path.home() / '.local' / 'share' / 'sfrecorder' / 'venv' / 'bin' / 'python'
SHEET_DIR = Path.home() / '.local' / 'share' / 'hey-frame-v3'


def is_listening() -> bool:
    try:
        p = subprocess.run(['systemctl', '--user', 'is-active', '--quiet', 'hey-frame.service'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2)
        return p.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def is_enabled() -> bool:
    try:
        return subprocess.run(['systemctl', '--user', 'is-enabled', '--quiet', 'hey-frame.service'],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def source_available() -> bool:
    return BIN.is_file() and (SHEET_DIR / 'src' / 'assistant.py').is_file()


def invoke_hey_frame(action: str) -> str:
    """Only selected named CLI subcommands; never interpret user-provided shell text."""
    if action not in ('start', 'stop', 'mode-glados', 'mode-normal'):
        raise ValueError('Unknown dashboard command')
    # Emergency stop must work even if Hey Frame's Python wrapper or models
    # are missing/corrupted. systemd owns the microphone process, not Python.
    if action != 'stop' and not source_available():
        return 'Hey Frame is not installed.'
    try:
        # Emergency stop bypasses the diagnostic-heavy CLI and directly stops
        # the user service. It is safe even when native speech modules fail.
        if action == 'stop':
            args = ['systemctl', '--user', 'disable', '--now', 'hey-frame.service']
        else:
            args = ([str(BIN), 'mode', action.removeprefix('mode-')]
                    if action.startswith('mode-') else [str(BIN), action])
        result = subprocess.run(args, capture_output=True, text=True,
                                timeout=45 if action == 'start' else 8)
    except (OSError, subprocess.SubprocessError) as exc:
        return f'Unable to change Hey Frame: {exc}'[:120]
    if result.returncode:
        return (result.stderr.strip() or result.stdout.strip() or 'Unable to change listener')[-150:]
    if action.startswith('mode-'):
        return 'GLaDOS mode enabled.' if action == 'mode-glados' else 'Normal replies enabled.'
    if action == 'stop':
        return ('Listening stopped. Automatic startup disabled.' if not is_listening()
                else 'Stop command returned, but listening is still active. Check the service.')
    return 'Listening enabled for future sessions.'


def socket_file() -> Path:
    runtime = Path(os.environ.get('XDG_RUNTIME_DIR') or f'/run/user/{os.getuid()}')
    return runtime / 'hey-frame' / 'vr-dashboard.sock'


class DashboardSocket:
    def __init__(self, location: Path | None = None):
        self.path = location or socket_file()
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.path.parent.stat().st_uid != os.getuid():
            raise RuntimeError('Dashboard socket directory has unexpected owner')
        self.path.parent.chmod(0o700)
        if self.path.exists() or self.path.is_symlink():
            old = self.path.lstat()
            if not stat.S_ISSOCK(old.st_mode) or old.st_uid != os.getuid():
                raise RuntimeError('Unsafe existing dashboard socket')
            self.path.unlink()
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            self.server.bind(str(self.path))
            self.path.chmod(0o600)
            self.server.listen(4)
            self.server.setblocking(False)
        except Exception:
            self.server.close()
            raise

    def poll(self, handler):
        for _ in range(4):
            try:
                conn, _ = self.server.accept()
            except (BlockingIOError, OSError):
                return
            with conn:
                try:
                    conn.settimeout(0.08)
                    command = conn.recv(80).decode('ascii', 'strict').strip()
                    answer = handler(command) if command in ('open_dashboard', 'screenshot') else 'Invalid dashboard request.'
                    conn.sendall(json.dumps({'message': answer[:250]}).encode('utf-8'))
                except (OSError, UnicodeError, ValueError):
                    pass

    def close(self):
        self.server.close()
        try:
            if self.path.is_socket():
                self.path.unlink()
        except OSError:
            pass


def font(size):
    from PIL import ImageFont
    for face in ('/usr/share/fonts/TTF/DejaVuSans-Bold.ttf',
                 '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
                 '/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf'):
        if Path(face).is_file():
            return ImageFont.truetype(face, size)
    return ImageFont.load_default()


class Panel:
    WIDTH, HEIGHT = 800, 990
    BG = (6, 11, 20, 255)
    FG = (240, 248, 252, 255)
    DIM = (146, 171, 189, 255)
    BLUE = (20, 141, 228, 255)
    GREEN = (21, 177, 134, 255)
    RED = (190, 60, 77, 255)

    def __init__(self):
        self.big, self.mid, self.small = font(54), font(32), font(23)
        self.hitboxes = []

    def button(self, draw, top, title, action, enabled=True, color=None):
        box = (64, top, 736, top + 94)
        draw.rounded_rectangle(box, radius=20, fill=(color or self.BLUE) if enabled else (37, 48, 60, 255))
        draw.text((400, top + 46), title, font=self.mid, fill=self.FG if enabled else self.DIM, anchor='mm')
        if enabled:
            self.hitboxes.append((*box, action))

    def draw(self, listening, busy, info, rec='unknown', glados=False):
        from PIL import Image, ImageDraw
        image = Image.new('RGBA', (self.WIDTH, self.HEIGHT), self.BG)
        d = ImageDraw.Draw(image)
        self.hitboxes = []
        d.text((400, 78), 'HEY FRAME', font=self.big, fill=self.FG, anchor='mm')
        color = self.GREEN if listening else self.RED
        d.ellipse((150, 126, 194, 170), fill=color)
        d.text((213, 148), 'MICROPHONE LISTENING' if listening else 'LISTENING OFF',
               font=self.mid, fill=self.FG, anchor='lm')
        # Two independent toggles: voice listening and response personality.
        # Mode can be changed even while the microphone is disabled.
        for box, title, action, color in (
            ((64, 205, 390, 299), 'LISTEN: ON' if listening else 'LISTEN: OFF',
             'listen_stop' if listening else 'listen_start',
             self.RED if listening else self.GREEN),
            ((410, 205, 736, 299), 'GLaDOS: ON' if glados else 'GLaDOS: OFF',
             'mode_toggle', self.GREEN if glados else self.BLUE),
        ):
            # STOP LISTENING is ALWAYS available, including during a busy
            # recording or voice-model check. Other controls can be disabled.
            enabled = not busy or action == 'listen_stop'
            d.rounded_rectangle(box, radius=20,
                                fill=color if enabled else (37, 48, 60, 255))
            d.text(((box[0] + box[2]) // 2, 252),
                   title if enabled else 'Working...',
                   font=self.mid, fill=self.FG if enabled else self.DIM, anchor='mm')
            if enabled:
                self.hitboxes.append((*box, action))
        self.button(d, 323, 'START RECORDING', 'record_start', enabled=not busy)
        self.button(d, 435, 'STOP / SAVE RECORDING', 'record_stop', enabled=not busy, color=self.RED)
        self.button(d, 547, 'MARK HIGHLIGHT', 'marker', enabled=not busy)
        self.button(d, 659, 'TAKE VR SCREENSHOT', 'screenshot', enabled=not busy)
        d.text((400, 790), f'Recorder: {rec[:34]}', font=self.small, fill=self.DIM, anchor='mm')
        for i, line in enumerate(split_lines(info, 46)[:2]):
            d.text((400, 830 + i * 31), line, font=self.small, fill=self.FG, anchor='mm')
        d.text((400, 930), 'OFF prevents listening until you enable it again.',
               font=self.small, fill=self.DIM, anchor='mm')
        return image

    def clicked(self, x: float, y: float):
        for x1,y1,x2,y2,act in self.hitboxes:
            if x1 <= x <= x2 and y1 <= y <= y2:
                return act
        return None

    @staticmethod
    def icon():
        from PIL import Image, ImageDraw
        im = Image.new('RGBA', (256,256), (0,0,0,0))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle((85,30,171,156),radius=43,fill=(35,199,151,255))
        d.arc((58,82,198,201), start=0,end=180,fill=(245,245,245,255),width=14)
        d.line((128,200,128,228),fill=(245,245,245,255),width=14)
        d.line((93,229,163,229),fill=(245,245,245,255),width=12)
        return im


def split_lines(text: str, width: int) -> list[str]:
    words = text.split()
    lines, curr = [], ''
    for word in words:
        if len(curr) + len(word) + 1 > width and curr:
            lines.append(curr)
            curr = word
        else:
            curr = (curr + ' ' + word).strip()
    return lines + ([curr] if curr else [])


def recording_request(command: str) -> str:
    from recording import request
    return request(command)


def mark_request() -> str:
    from gaming import mark_moment
    return mark_moment()


def take_screenshot(vr):
    """Ask the SteamVR compositor, not the gamepad, to capture a stereo screenshot."""
    destination = Path.home() / 'Pictures' / 'HeyFrame'
    destination.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    preview = destination / f'frame_{stamp}_preview.png'
    stereo = destination / f'frame_{stamp}_stereo.png'
    try:
        result = vr.VRScreenshots().takeStereoScreenshot(str(preview), str(stereo))
        # PyOpenVR returns the handle on success, but versions may return a tuple.
        if isinstance(result, tuple) and any(isinstance(x, int) and x not in (0,1) for x in result):
            return 'Screenshot requested. Check Pictures/HeyFrame.'
        return 'Screenshot requested. Check Pictures/HeyFrame.'
    except Exception as exc:
        return 'SteamVR screenshot failed. ' + str(exc)[:80]


def run_panel():
    import openvr
    from PIL import Image
    del Image
    overlay_system = openvr.init(openvr.VRApplication_Overlay)
    del overlay_system
    overlay = openvr.VROverlay()
    panel = Panel()
    handle, thumb = overlay.createDashboardOverlay(APP_KEY, 'Hey Frame')
    overlay.setOverlayWidthInMeters(handle, 1.35)
    overlay.setOverlayInputMethod(handle, openvr.VROverlayInputMethod_Mouse)
    scale = openvr.HmdVector2_t()
    scale[0], scale[1] = Panel.WIDTH, Panel.HEIGHT
    overlay.setOverlayMouseScale(handle, scale)
    icon = panel.icon()
    raw = (ctypes.c_ubyte * len(icon.tobytes())).from_buffer_copy(icon.tobytes())
    overlay.setOverlayRaw(thumb, raw, icon.width, icon.height, 4)
    conn = DashboardSocket()
    listener = is_listening()
    glados = get_mode() == 'glados'
    busy = False
    info = 'Ready. Select an action using the controller.'
    recorder_state = 'checking'
    results = queue.Queue()
    event = openvr.VREvent_t()
    refresh_at, check_at = 0.0, 0.0

    def schedule(label, work, emergency=False):
        nonlocal busy, info
        if busy and not emergency:
            return
        busy = True
        info = label
        def job():
            try:
                response = work()
            except Exception as exc:
                response = 'Command failed: ' + str(exc)[:150]
            results.put(response)
        threading.Thread(target=job, daemon=True).start()

    def handle_remote(command):
        if command == 'open_dashboard':
            try:
                overlay.showDashboard(APP_KEY)
                return 'Dashboard opened.'
            except Exception:
                return 'Unable to open SteamVR dashboard.'
        if command == 'screenshot':
            return take_screenshot(openvr)
        return 'Unsupported dashboard command.'

    def redraw():
        image = panel.draw(listener, busy, info, recorder_state, glados=glados)
        pixels = image.tobytes()
        raw = (ctypes.c_ubyte * len(pixels)).from_buffer_copy(pixels)
        overlay.setOverlayRaw(handle, raw, image.width, image.height, 4)

    redraw()
    try:
        while True:
            now = time.monotonic()
            conn.poll(handle_remote)
            try:
                while True:
                    info = results.get_nowait()
                    busy = False
                    listener = is_listening()
                    glados = get_mode() == 'glados'
                    redraw()
            except queue.Empty:
                pass
            if now >= check_at and not busy:
                check_at = now + 2.0
                current = is_listening()
                current_glados = get_mode() == 'glados'
                if current != listener or current_glados != glados:
                    listener = current
                    glados = current_glados
                    redraw()
            while openvr.VRSystem().pollNextEvent(event):
                if event.eventType == openvr.VREvent_Quit:
                    openvr.VRSystem().acknowledgeQuit_Exiting()
                    return
            while overlay.pollNextOverlayEvent(handle, event)[0]:
                if event.eventType == openvr.VREvent_MouseButtonUp:
                    x = event.data.mouse.x
                    y = Panel.HEIGHT - event.data.mouse.y
                    action = panel.clicked(x, y)
                    if action == 'listen_stop':
                        # Fixed STOP action, not a deferred toggle based on
                        # listener state that may change before worker executes.
                        schedule('Stopping microphone immediately...',
                                 lambda: invoke_hey_frame('stop'), emergency=True)
                        redraw()
                    elif action == 'listen_start':
                        schedule('Starting microphone...',
                                 lambda: invoke_hey_frame('start'))
                        redraw()
                    elif action == 'mode_toggle':
                        schedule('Switching response personality...', lambda: invoke_hey_frame(
                            'mode-normal' if glados else 'mode-glados'))
                        redraw()
                    elif action == 'record_start':
                        schedule('Starting recorder...', lambda: recording_request('start'))
                        redraw()
                    elif action == 'record_stop':
                        schedule('Saving recording...', lambda: recording_request('stop'))
                        redraw()
                    elif action == 'marker':
                        schedule('Marking moment...', mark_request)
                        redraw()
                    elif action == 'screenshot':
                        info = take_screenshot(openvr)
                        redraw()
            if now >= refresh_at and overlay.isOverlayVisible(handle):
                refresh_at = now + 5.0
                from recording import recorder_socket
                new_state = 'connected' if recorder_socket().is_socket() else 'not connected'
                if new_state != recorder_state:
                    recorder_state = new_state
                    redraw()
            time.sleep(0.05 if overlay.isOverlayVisible(handle) or busy else 0.4)
    finally:
        conn.close()
        openvr.shutdown()


def main():
    # Dashboard is idle until SteamVR is available; no microphone input here.
    import openvr
    while True:
        try:
            openvr.init(openvr.VRApplication_Background)
            openvr.shutdown()
            break
        except Exception:
            time.sleep(5)
    run_panel()


if __name__ == '__main__':
    main()
