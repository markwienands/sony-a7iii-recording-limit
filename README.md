# Sony A7 III recording limit (macOS)

Raises the Sony A7 III (ILCE-7M3) video recording limit from 29m50s to 13h01m, using Sony's service mode.

**Unofficial and at your own risk.** An interrupted or wrong write could damage your camera's settings or make it unusable, and may affect your warranty. The settings copies this saves are not a guaranteed recovery. Not affiliated with or endorsed by Sony. If that is not acceptable, use an external HDMI recorder instead.

## Known configuration

The method has worked on one camera, once:

| | |
|---|---|
| Camera | ILCE-7M3, firmware 4.04, region code `CX62201_AP2` |
| Settings version | `37114_13.2026020901` |
| Computer | Apple silicon Mac, Python 3.9 |
| Result | Read 13h01m after a reconnect, then recorded past 30 minutes |

`write` and `undo` refuse any other model or settings version. An earlier write by the same method on firmware 3.01 did not survive a restart; the reason is unknown.

**Not yet tried:** `undo` on a real camera, the save-to-disk fallback (it was not needed), a settings reset, and both HD and 4K. Windows and Linux are not supported.

## Before you start

- Update to firmware 4.04 with Sony's own updater.
- Copy your card. Use a full battery and a direct cable, not a hub.
- Set USB Connection to **Mass Storage**, and Power Save Start Time to 30 minutes.

## Use

    ./setup.sh
    ./run.sh check     # read-only

Follow the prompts. Continue only if `check` shows `ILCE-7M3`, the settings version above and `0h 29m 50s`, for both memory and the stored copy.

    ./run.sh write

Type `YES` only if it shows 4 or 5 bytes changing and `from 0h29m50s to 13h01m00s`. Then don't touch the camera, cable or Mac until `FINISHED`.

| You see | Do this |
|---|---|
| `STORED VERIFIED` | Power switch off, wait 10 seconds, unplug. Restart and run `./run.sh check`; it should say 13h. |
| `NOT STORED`, `A write WAS attempted`, or any error after `YES` | Leave the camera on and connected. Do not retry. Keep the log. |
| `Nothing was written`, or an error before `YES` | No settings were written. |

Then record for 35 minutes and play it back. Heat, battery and card space can still end a recording. Don't leave it unattended.

`./run.sh undo` puts 29m50s back.

## How it works

It reads the whole settings block, changes the three limit bytes and the checksum, writes the block back, and compares. Every command goes through an allowlist: `check` can only read; `write` allows one exact payload, once, and at most one save. Because the whole block is written back, a counter that changes in the moment between reading and writing can be set back.

## Privacy

`backups/` contains your camera's **serial number**. Never post those files in an issue. Both `backups/` and `logs/` are ignored by Git.

## Credits

Built on [Sony-PMCA-RE](https://github.com/ma1co/Sony-PMCA-RE) by ma1co, which found the setting and the service-mode protocol. See [THIRD_PARTY.md](THIRD_PARTY.md). Written with Claude Code. MIT licensed.
