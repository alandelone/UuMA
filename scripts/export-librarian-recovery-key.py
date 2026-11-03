"""Interactive offline recovery-key export; never accepts a password in arguments."""

from __future__ import annotations

import argparse
import ctypes
import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from uuma.librarian_keys import export_offline


def main() -> None:
    parser = argparse.ArgumentParser(description="Export an encrypted Librarian offline recovery key")
    parser.add_argument("--destination", type=Path, required=True,
                        help="New file on a separate offline disk or USB drive")
    parser.add_argument("--key-directory", type=Path,
                        help="Recovery-key directory; automatically located if unambiguous")
    args = parser.parse_args()
    if sys.platform != "win32":
        raise SystemExit("Export must run as the original Windows user on the workstation.")
    destination = args.destination
    if not destination.is_absolute() or not destination.parent.is_dir():
        raise SystemExit("Choose an absolute destination in an existing offline drive directory.")
    workstation_drive = Path(os.environ["LOCALAPPDATA"]).drive.casefold()
    if not destination.drive or destination.drive.casefold() == workstation_drive:
        raise SystemExit("Choose a separate offline drive, not the workstation system drive.")
    drive_type = ctypes.windll.kernel32.GetDriveTypeW(destination.anchor)
    if drive_type not in (2, 3):
        raise SystemExit("Choose a local removable disk or USB drive, not a network share.")
    key_directory = args.key_directory
    if key_directory is None:
        devices = Path(os.environ["LOCALAPPDATA"]) / "UuMA" / "Librarian" / "devices"
        candidates = [p for p in devices.glob("workstation-*/recovery-key") if p.is_dir()]
        if len(candidates) != 1:
            raise SystemExit("Recovery key directory is ambiguous; specify --key-directory.")
        key_directory = candidates[0]
    first = getpass.getpass("Offline recovery passphrase (at least 12 bytes): ").encode("utf-8")
    second = getpass.getpass("Repeat offline recovery passphrase: ").encode("utf-8")
    if first != second:
        raise SystemExit("Passphrases did not match; nothing was exported.")
    fingerprint = export_offline(key_directory, destination, first)
    print("Encrypted key exported and independently checked. Public fingerprint:", fingerprint)
    print("Keep the offline drive and its passphrase separately from this workstation and NAS.")


if __name__ == "__main__":
    main()
