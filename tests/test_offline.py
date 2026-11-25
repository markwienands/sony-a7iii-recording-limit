"""Offline tests using synthetic settings (no camera, no real camera data)."""
import builtins
import os
import struct
import sys
import unittest
from types import SimpleNamespace as NS

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import reclimit as r


def make(model=r.MODEL, version=r.KNOWN_VERSION, limit=r.ORIGINAL, attr=0, noise=b''):
    subs = 0x3f
    counts = {0x3c: 0x376, 0x3e: 6}
    nprops = sum(counts.values())
    table = 0x100 + subs * r.BackupFile.__init__.__globals__['SubsystemTableEntry'].size
    data_off = table + nprops * 6
    data = bytes(limit) + model.ljust(16, b'\0') + noise.ljust(8192, b'\0')
    h = struct.pack('<III4sIIII', 0, 0, 0, b'BK4\0', subs, nprops, data_off, len(data))
    h += struct.pack('<III', 0, 0, 1)
    h = h.ljust(0x40, b'\0') + version.ljust(0x20, b'\0')
    h = h.ljust(0x100, b'\0')
    st = b''.join(struct.pack('<HI', counts.get(i, 0), 0x376 if i == 0x3e else 0) for i in range(subs))
    props = [(0, 0xffffffff)] * nprops
    for k in range(3):
        props[0x373 + k] = (attr, 1 << 24 | data_off + k)
    props[0x376 + 5] = (0, 16 << 24 | data_off + 3)
    b = bytearray(h + st + b''.join(struct.pack('<HI', *p) for p in props) + data)
    struct.pack_into('<I', b, 0x20, sum(b) & 0xffffffff)
    return bytes(b)


class Cam:
    def __init__(self, mem, apply=True, autostore=True, store=True, post=None):
        self.mem, self.st, self.a, self.auto, self.s, self.post = mem, make(), apply, autostore, store, post
        self.writes = self.saves = 0
        self.dev = NS(approved=None, save_approved=False, driver=NS(backend=NS(dev=NS())))

    def getBackupPresetData(self, memory):
        return self.mem if memory else self.st

    def setBackupPresetData(self, mode, out):
        assert mode == 2 and self.dev.approved == (2).to_bytes(4, 'little') + out
        self.writes += 1
        if self.a:
            self.mem = self.post or out
            if self.auto:
                self.st = self.mem

    def saveBackup(self, n):
        assert self.dev.save_approved
        self.saves += 1
        if self.s:
            self.st = self.mem


class Tests(unittest.TestCase):
    def setUp(self):
        r.save = lambda *a: None
        r.time.sleep = lambda *a: None
        self.answer('YES')

    def answer(self, a):
        builtins.input = lambda *_: a

    def go(self, cam, blob=None):
        r.change(cam, blob or make(), r.ORIGINAL, r.EXTENDED)
        return cam.writes, cam.saves

    def test_write_and_undo(self):
        out = r.build(make(), r.ORIGINAL, r.EXTENDED)
        self.assertEqual(r.limit(out), r.EXTENDED)
        self.assertEqual(r.build(out, r.EXTENDED, r.ORIGINAL), make())

    def test_refuses(self):
        for kw in (dict(model=b'ILCE-7M4'), dict(version=b'37114_07.2019041701'),
                   dict(limit=(0, 30, 0)), dict(attr=1)):
            with self.subTest(kw), self.assertRaises(RuntimeError):
                r.build(make(**kw), r.ORIGINAL, r.EXTENDED)

    def test_flow(self):
        self.assertEqual(self.go(Cam(make())), (1, 0))
        self.assertEqual(self.go(Cam(make(noise=b'x' * 300))), (1, 0))
        self.assertEqual(self.go(Cam(make(), autostore=False)), (1, 1))
        self.assertEqual(self.go(Cam(make(), autostore=False, store=False)), (1, 1))

    def test_too_much_drift(self):
        self.assertEqual(self.go(Cam(make(noise=b'x' * 5000))), (0, 0))

    def test_cancel(self):
        self.answer('yes')
        self.assertEqual(self.go(Cam(make())), (0, 0))

    def test_bad_readback(self):
        for cam in (Cam(make(), apply=False), Cam(make(), post=make(limit=r.EXTENDED, noise=b'x' * 5000))):
            with self.assertRaises(RuntimeError):
                self.go(cam)
            self.assertEqual((cam.writes, cam.saves), (1, 0))

    def test_allowlist(self):
        d = r.GuardedDevice.__new__(r.GuardedDevice)
        for cmd in (r.C.SONY_ADJUST_BACKUP_PDT_WRITE, r.C.SONY_ADJUST_BACKUP_SAVE, (0x603, 0x7777)):
            h = r.C.CommandHeader.pack(category=cmd[0], command=cmd[1])
            with self.assertRaisesRegex(RuntimeError, 'BLOCKED'):
                d.sendSenserPacket(r.C.SONY_PFUNC_AdjustControl, h + b'\0\0')
        with self.assertRaisesRegex(RuntimeError, 'BLOCKED'):
            d.writeTerminal(b'x')


if __name__ == '__main__':
    unittest.main()
