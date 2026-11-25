#!/bin/zsh
# Usage: ./run.sh check | write | undo
cd "$(dirname "$0")" || exit 1
case "$1" in check|write|undo) ;; *) echo "Usage: ./run.sh check|write|undo"; exit 2;; esac
[[ -x venv/bin/python ]] || { echo "Run ./setup.sh first."; exit 1; }
umask 077
mkdir -p logs backups
LOG=logs/$1-$(date +%Y%m%d-%H%M%S).txt
present() { ioreg -p IOUSB -w0 | grep -q ILCE-7M3 }
echo "Mode: $1. Enter your Mac password (needed for USB access):"
sudo -v || exit 1
echo "1) In Finder, eject the camera's volumes. Turn the camera off and unplug it."
while present; do sleep 1; done
echo "   Camera disconnected."
echo "2) Wait 10 seconds, turn it on, plug it in, then leave it alone."
until present; do sleep 1; done
sleep 8
# Mass-storage disks whose media name marks them as Sony's.
disks=()
for d in $(diskutil list external physical | awk '/^\/dev\/disk/{print $1}'); do
  diskutil info "$d" | grep -Eq 'Media Name:.*(Sony|DSC)' && disks+=("$d")
done
if (( ${#disks} == 0 )); then
  echo "Could not identify the camera's disks; nothing was sent." | tee -a "$LOG"; exit 1
fi
for d in $disks; do
  diskutil unmountDisk "$d" || { echo "Unmount failed; nothing was sent." | tee -a "$LOG"; exit 1; }
done
sudo venv/bin/python -I -u reclimit.py "$1" 2>&1 | tee -a "$LOG"
echo "FINISHED. If there was no error: power switch off, wait 10 seconds, unplug." | tee -a "$LOG"
