"""Digi Mono's engine (mods/digimono/mono.c) built for this PC and loaded with ctypes, for the tests.

The same C builds for the ColdFire (tests/emu_mono.py checks the two give the same samples), so what these
tests measure is what the unit plays.
"""
import ctypes, os, subprocess, tempfile

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "mods", "digimono", "mono.c")
FS = 48000
BLOCK = 32                                  # frames in one render block of the Digitakt
SIN, NOIS, SAW, PULS, ENS, VO = range(6)
NAMES = ["SIN", "NOIS", "SAW", "PULS", "ENS", "VO"]
VOICE_SIZE = 1112
# struct mono_voice (mono.h): 11 32-bit words, a 16-bit word, 2 bytes, the 16-bit chorus line, then
# 10 32-bit words (VO). The same layout on the ColdFire (big-endian) and on this PC (little-endian).
_LAYOUT = [(0, 44, 4), (44, 46, 2), (46, 48, 1), (48, 1072, 2), (1072, 1112, 4)]


def swap_state(b):
    """A struct mono_voice's bytes in the other byte order (either way)."""
    out = bytearray()
    for lo, hi, w in _LAYOUT:
        out += b"".join(b[i:i + w][::-1] for i in range(lo, hi, w))
    return bytes(out)


class Voice(ctypes.Structure):
    _fields_ = [("raw", ctypes.c_uint8 * VOICE_SIZE)]


def _build():
    out = os.path.join(tempfile.gettempdir(), "digimono_host_%d.so" % os.getpid())
    subprocess.check_call(["gcc", "-O2", "-Wall", "-shared", "-fPIC", "-o", out, SRC])
    return ctypes.CDLL(out)


LIB = _build()
LIB.mono_pitch_inc.restype = ctypes.c_uint32
LIB.mono_pitch_inc.argtypes = [ctypes.c_int32]
LIB.mono_render.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32,
                            ctypes.c_void_p, ctypes.c_int]
LIB.mono_init.argtypes = [ctypes.c_void_p]
LIB.mono_trig.argtypes = [ctypes.c_void_p, ctypes.c_int]


def pitch_inc(note):
    """The phase increment of a (fractional) MIDI note."""
    return LIB.mono_pitch_inc(int(round(note * 128)))


class Engine:
    """One voice. render() takes the parameters and pitch per block, as the Digitakt's render would."""

    def __init__(self, machine, params=None):
        self.v = Voice()
        LIB.mono_init(ctypes.byref(self.v))
        self.machine = machine
        self.params = list(params or [0] * 7)

    def trig(self):
        LIB.mono_trig(ctypes.byref(self.v), self.machine)

    def render(self, frames, note=None, inc=None, block=BLOCK, params=None):
        p = (ctypes.c_uint8 * 7)(*(params or self.params))
        inc = pitch_inc(note) if inc is None else inc
        out = (ctypes.c_int16 * frames)()
        pos = 0
        while pos < frames:
            n = min(block, frames - pos)
            LIB.mono_render(ctypes.byref(self.v), self.machine, p, inc,
                            ctypes.addressof(out) + 2 * pos, n)
            pos += n
        return np.frombuffer(out, dtype=np.int16).astype(np.float64) / 32768.0

    def state(self):
        return bytes(self.v.raw)


def play(machine, params, note, seconds=1.0, block=BLOCK):
    e = Engine(machine, params)
    e.trig()
    return e.render(int(FS * seconds), note=note, block=block)


def note_hz(n):
    return 440.0 * 2 ** ((n - 69) / 12)
