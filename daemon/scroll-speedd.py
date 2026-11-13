#!/usr/bin/env python3
"""scroll-speedd - multiply mouse-wheel scrolling by a configurable factor.

Grabs every real mouse, forwards all of its events through a virtual (uinput)
clone, and scales the wheel. Scrolling is emitted as high-resolution wheel
events (120 units = one notch), so fractional factors (slower than 1x) work
smoothly in apps that support it, while classic notch events are accumulated
for everything else.

The factor is read from SCROLL_SPEED_FILE (a single float, e.g. "2.5") and is
re-read whenever the file changes.
"""
import os
import select
import signal
import sys

import evdev
from evdev import InputDevice, UInput, ecodes as e

CONFIG = os.environ.get("SCROLL_SPEED_FILE", "/etc/scroll-speed/factor")
VIRT_PREFIX = "scroll-speedd"
MIN_FACTOR, MAX_FACTOR = 0.1, 10.0
HIRES_PER_NOTCH = 120

AXES = {
    # legacy code   -> hi-res code
    e.REL_WHEEL: e.REL_WHEEL_HI_RES,
    e.REL_HWHEEL: e.REL_HWHEEL_HI_RES,
}
HIRES_TO_AXIS = {hi: lo for lo, hi in AXES.items()}


def log(*args):
    print(*args, file=sys.stderr, flush=True)


def is_mouse(dev):
    if dev.name.startswith(VIRT_PREFIX):
        return False
    rel = dev.capabilities().get(e.EV_REL, [])
    return e.REL_X in rel and e.REL_WHEEL in rel


class Mouse:
    def __init__(self, dev):
        self.dev = dev
        caps = dev.capabilities(absinfo=True)
        caps.pop(e.EV_SYN, None)
        caps.pop(e.EV_FF, None)
        rel = set(caps.get(e.EV_REL, []))
        self.native_hires = {axis: hi in rel for axis, hi in AXES.items()}
        for axis, hi in AXES.items():
            if axis in rel:
                rel.add(hi)
        caps[e.EV_REL] = sorted(rel)

        self.ui = UInput(
            caps,
            name=f"{VIRT_PREFIX} {dev.name}"[:79],
            vendor=dev.info.vendor,
            product=dev.info.product,
            version=dev.info.version,
            bustype=dev.info.bustype,
        )
        self.remainder = {axis: 0.0 for axis in AXES}  # sub-unit hi-res leftovers
        self.notches = {axis: 0 for axis in AXES}  # hi-res units not yet a full notch
        dev.grab()
        log(f"grabbed {dev.path}: {dev.name}")

    def fileno(self):
        return self.dev.fd

    def scroll(self, axis, amount):
        total = self.remainder[axis] + amount
        hires = int(round(total))
        self.remainder[axis] = total - hires
        if not hires:
            return
        self.ui.write(e.EV_REL, AXES[axis], hires)
        self.notches[axis] += hires
        whole = int(self.notches[axis] / HIRES_PER_NOTCH)  # truncates toward zero
        if whole:
            self.ui.write(e.EV_REL, axis, whole)
            self.notches[axis] -= whole * HIRES_PER_NOTCH

    def handle(self, ev, factor):
        if ev.type == e.EV_REL and (ev.code in AXES or ev.code in HIRES_TO_AXIS):
            if ev.code in AXES:
                if self.native_hires[ev.code]:
                    return  # device also sends hi-res events; derive notches from those
                self.scroll(ev.code, ev.value * HIRES_PER_NOTCH * factor)
            else:
                self.scroll(HIRES_TO_AXIS[ev.code], ev.value * factor)
            return
        if ev.type == e.EV_SYN and ev.code == e.SYN_DROPPED:
            return
        self.ui.write(ev.type, ev.code, ev.value)

    def close(self):
        for fn in (self.dev.ungrab, self.dev.close, self.ui.close):
            try:
                fn()
            except OSError:
                pass
        log(f"released {self.dev.path}")


def mtime(path):
    try:
        return os.stat(path).st_mtime_ns
    except OSError:
        return None


def read_factor():
    try:
        with open(CONFIG) as f:
            value = float(f.read().strip())
    except (OSError, ValueError):
        return 1.0
    return min(MAX_FACTOR, max(MIN_FACTOR, value))


def main():
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    mice = {}  # fd -> Mouse
    dir_mtime = cfg_mtime = object()
    factor = 1.0

    try:
        while True:
            m = mtime("/dev/input")
            if m != dir_mtime:
                dir_mtime = m
                managed = {mouse.dev.path for mouse in mice.values()}
                for path in evdev.list_devices():
                    if path in managed:
                        continue
                    try:
                        dev = InputDevice(path)
                    except OSError:
                        continue
                    if not is_mouse(dev):
                        dev.close()
                        continue
                    try:
                        mouse = Mouse(dev)
                    except OSError as err:
                        log(f"cannot take {path}: {err}")
                        dev.close()
                        continue
                    mice[mouse.fileno()] = mouse

            m = mtime(CONFIG)
            if m != cfg_mtime:
                cfg_mtime = m
                factor = read_factor()
                log(f"scroll factor = {factor:g}")

            ready, _, _ = select.select(list(mice), [], [], 0.5)
            for fd in ready:
                mouse = mice[fd]
                try:
                    for ev in mouse.dev.read():
                        mouse.handle(ev, factor)
                except OSError:  # unplugged
                    mouse.close()
                    del mice[fd]
    finally:
        for mouse in mice.values():
            mouse.close()


if __name__ == "__main__":
    main()
