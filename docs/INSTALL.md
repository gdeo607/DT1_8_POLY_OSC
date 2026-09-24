# Install and revert

## Before the first flash (once)
1. With the **official** OS still installed, back up ALL projects, sounds and samples with the manufacturer's
   transfer app.
2. Keep the official OS 1.53 file (from the manufacturer's download page) somewhere safe.
3. Have a physical MIDI interface + cable ready (the startup-menu recovery cannot use USB).

## Get the image
- Build it: `python3 tools/build.py --official <official OS 1.53 .syx> --tool <container tool>` (see README), or

## Flash
1. Connect the unit by USB, open the transfer app, drop the `.syx` onto it, confirm with YES on the unit.
2. Do not power off during the update. After reboot the OS version shows **1.5b**.
3. Quick check: FUNC+SRC on an audio track lists POLY after SLICE; the "..." key opens the scope.

## Revert to the official OS
**A. Unit starts normally**
1. Set POLY tracks back to ONESHOT (FUNC+SRC) and re-save anything you want to keep, or plan to restore a backup.
2. Send the official OS 1.53 `.syx` with the transfer app, confirm with YES, don't power off.
3. If a kit looks wrong afterwards, restore your backup.

**B. Unit does not start / freezes**
1. Power off and open the startup menu (see the unit's manual: OS upgrade via the startup menu).
2. Send the official OS `.syx` over **physical MIDI** from the transfer app's SysEx page.

## Safe testing order
Flash one build at a time and test it before moving on. If anything is odd, go back to the last build that
worked (v3n / 1.5Z is hardware-confirmed) or to the official OS.
