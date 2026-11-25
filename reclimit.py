"""Change the Sony A7 III video recording limit. Usage: reclimit.py check|write|undo

Every Sony command is checked against an allowlist before it is sent. 'check' can only read.
"""
import datetime
import hashlib
import io
import os
import sys
import time
import traceback

sys.dont_write_bytecode = True
BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE, 'Sony-PMCA-RE'))

from pmca.backup import BackupFile
from pmca.usb import MscDevice
from pmca.usb.sony import (SonySenserAuthDevice, SonySenserCamera as C, SonySenserDevice,
                           isSonyMscCamera, isSonySenserCamera)

VENDOR, MSC_PRODUCT = 0x054c, 0x0c01
LIMIT_IDS = [0x003c0373, 0x003c0374, 0x003c0375]  # hours, minutes, seconds
MODEL_ID, MODEL = 0x003e0005, b'ILCE-7M3'
# The settings version from the known configuration (firmware 4.04).
KNOWN_VERSION = b'37114_13.2026020901'
ORIGINAL, EXTENDED = (0, 29, 50), (13, 1, 0)
MAX_DRIFT = 2048  # of about 1.15 million bytes; the camera updates counters by itself
STATE = {'write_attempted': False, 'verified': False}

READS = {
    (C.SONY_PFUNC_ProductInfo,) + C.SONY_PRODUCT_INFO_READ_HASP,
    (C.SONY_PFUNC_AdjustControl,) + C.SONY_ADJUST_BACKUP_PDT_READ,
}
WRITE = (C.SONY_PFUNC_AdjustControl,) + C.SONY_ADJUST_BACKUP_PDT_WRITE
SAVE = (C.SONY_PFUNC_AdjustControl,) + C.SONY_ADJUST_BACKUP_SAVE


class GuardedDevice(SonySenserDevice):
    approved = None  # the one exact write payload allowed, used once
    save_approved = False

    def sendSenserPacket(self, pFunc, data, oData=None):
        n = C.CommandHeader.size
        h = C.CommandHeader.unpack(data[:n])
        cmd = (pFunc, h.category, h.command)
        if cmd == WRITE and self.approved is not None and data[n:] == self.approved:
            self.approved = None
        elif cmd == SAVE and self.save_approved and data[n:] == b'\0\0':
            self.save_approved = False
        elif cmd not in READS:
            raise RuntimeError('BLOCKED: command not approved %r' % (cmd,))
        return super().sendSenserPacket(pFunc, data, oData)

    def writeTerminal(self, data):
        raise RuntimeError('BLOCKED: terminal write')


def parse(blob):
    return BackupFile(io.BytesIO(blob))  # also verifies the checksum


def limit(blob):
    values = [parse(blob).getProperty(i).data for i in LIMIT_IDS]
    if any(len(v) != 1 for v in values):
        raise RuntimeError('Unexpected size for the limit setting')
    return tuple(v[0] for v in values)


def describe(blob):
    b = parse(blob)
    print('Model %s, settings version %s' % (
        b.getProperty(MODEL_ID).data.rstrip(b'\0').decode('latin1'),
        b.header.version.rstrip(b'\0').decode('latin1')))
    print('Recording limit: %dh %02dm %02ds' % limit(blob))


def check_supported(b):
    if b.getProperty(MODEL_ID).data.rstrip(b'\0') != MODEL:
        raise RuntimeError('This is not an A7 III (ILCE-7M3)')
    if b.header.version.rstrip(b'\0') != KNOWN_VERSION:
        raise RuntimeError('Unsupported settings version; see "Known configuration" in the README')
    if b.revision != 4 or b.getId1() != 1:
        raise RuntimeError('Unexpected settings format')


def build(blob, old, new):
    f = io.BytesIO(blob)
    b = BackupFile(f)
    check_supported(b)
    if limit(blob) != old:
        raise RuntimeError('Current limit is %r, expected %r' % (limit(blob), old))
    allowed = set(range(0x20, 0x24))  # checksum
    for i, v in zip(LIMIT_IDS, new):
        p = b._readProperty(i)
        if p.attr & 1 or p.size != 1:
            raise RuntimeError('Unexpected attributes on the limit setting')
        allowed.add(p.ptr)
        b.setProperty(i, bytes([v]))
    b.updateChecksum()
    out = f.getvalue()
    if len(out) != len(blob) or limit(out) != new:
        raise RuntimeError('Patched settings failed the check')
    changed = {i for i in range(len(out)) if out[i] != blob[i]}
    if not changed <= allowed:
        raise RuntimeError('More than the limit and checksum would change')
    print('Bytes that would change: %d of %d (limit + checksum)' % (len(changed), len(out)))
    return out


def diffs(a, b):
    if len(a) != len(b):
        raise RuntimeError('Settings size changed')
    return sum(x != y for x, y in zip(a[0x100:], b[0x100:]))


def save(blob, tag):
    d = os.path.join(BASE, 'backups')
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, '%s-%s.bin' % (tag, datetime.datetime.now().strftime('%Y%m%d-%H%M%S')))
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as f:
        f.write(blob)
        f.flush()
        os.fsync(f.fileno())
    if 'SUDO_UID' in os.environ:
        os.chown(path, int(os.environ['SUDO_UID']), int(os.environ['SUDO_GID']))
    print('Saved %s (SHA-256 %s)' % (os.path.relpath(path, BASE), hashlib.sha256(blob).hexdigest()))


def change(cam, blob, old, new):
    build(blob, old, new)
    print('\nChange limit from %dh%02dm%02ds to %dh%02dm%02ds.' % (old + new))
    if input('Type YES to write it, anything else to cancel: ').strip() != 'YES':
        print('Cancelled. Nothing was written.')
        return
    fresh = cam.getBackupPresetData(True)
    drift = diffs(fresh, blob)
    print('Bytes the camera changed on its own while waiting: %d' % drift)
    if drift > MAX_DRIFT:
        print('Too many. Nothing was written.')
        return
    save(fresh, 'before-write')
    out = build(fresh, old, new)  # repeats every check
    cam.dev.driver.backend.dev.default_timeout = 60000
    cam.dev.approved = (2).to_bytes(4, 'little') + out
    print('Writing. Do not touch the camera or cable...')
    STATE['write_attempted'] = True
    cam.setBackupPresetData(2, out)
    back = cam.getBackupPresetData(True)
    drift = diffs(back, out)
    print('Bytes differing on read-back: %d' % drift)
    if limit(back) != new or drift > MAX_DRIFT:
        raise RuntimeError('Read-back does not match what was written')
    STATE['verified'] = True
    print('MEMORY VERIFIED: %dh %02dm %02ds' % new)
    stored = cam.getBackupPresetData(False)
    if limit(stored) != new:
        print('Stored copy not updated; saving to disk...')
        cam.dev.save_approved = True
        cam.saveBackup(0)
        for _ in range(10):
            time.sleep(1)
            stored = cam.getBackupPresetData(False)
            if limit(stored) == new:
                break
    save(stored, 'after-write')
    print(('STORED VERIFIED: ' if limit(stored) == new else 'NOT STORED, still: ')
          + '%dh %02dm %02ds' % limit(stored))


def run(mode):
    if sys.platform != 'darwin':
        sys.exit('This script has only been used on macOS; stopping.')
    if os.geteuid() != 0:
        sys.exit('Use ./run.sh (USB access needs sudo).')
    import libusb_package
    import usb.backend.libusb1
    lib = str(libusb_package.get_library_path())
    if usb.backend.libusb1.get_backend(find_library=lambda _: lib) is None:
        sys.exit('Could not load libusb.')
    from pmca.usb.driver.generic.libusb import MscContext, VendorSpecificContext

    def find_service():
        ctx = VendorSpecificContext()
        return [ctx.openDevice(d) for d in ctx.listDevices(VENDOR) if isSonySenserCamera(d)]

    drivers = find_service()
    if not drivers:
        ctx = MscContext()
        found = [d for d in ctx.listDevices(VENDOR) if d.idProduct == MSC_PRODUCT]
        if len(found) != 1:
            sys.exit('Expected exactly one A7 III in Mass Storage mode, found %d.' % len(found))
        drv = ctx.openDevice(found[0])
        info = MscDevice(drv).getDeviceInfo()
        if not isSonyMscCamera(info):
            sys.exit('Not recognised as a Sony camera; stopping before service mode.')
        print('Switching to service mode...')
        auth = SonySenserAuthDevice(drv)
        auth.start()
        auth.authenticate()
        for _ in range(20):
            time.sleep(.5)
            try:
                drivers = find_service()
            except Exception:
                drivers = []
            if drivers:
                break
    if len(drivers) != 1:
        sys.exit('Service mode device not found (got %d).' % len(drivers))

    auth = SonySenserAuthDevice(drivers[0])
    try:
        auth.start()
        auth.authenticate()
        cam = C(GuardedDevice(drivers[0]))
        cam.readHasp()
        blob = cam.getBackupPresetData(True)
        save(blob, 'memory')
        print('--- camera memory ---')
        describe(blob)
        if mode == 'check':
            stored = cam.getBackupPresetData(False)
            save(stored, 'stored')
            print('--- stored copy ---')
            describe(stored)
        else:
            old, new = (ORIGINAL, EXTENDED) if mode == 'write' else (EXTENDED, ORIGINAL)
            change(cam, blob, old, new)
    finally:
        auth.stop()


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ('check', 'write', 'undo'):
        sys.exit('Usage: reclimit.py check|write|undo')
    try:
        run(sys.argv[1])
    except BaseException as e:
        if isinstance(e, SystemExit):
            raise
        traceback.print_exc()
        if STATE['verified']:
            print('\nMemory was verified, but the stored copy was NOT confirmed. Do not retry.')
        elif STATE['write_attempted']:
            print('\nA write WAS attempted. Do not retry. Leave the camera on and keep the log.')
        else:
            print('\nStopped before writing. No settings were written.')
        sys.exit(1)


if __name__ == '__main__':
    main()
