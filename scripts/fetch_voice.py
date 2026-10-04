"""Fetch the optional official voice pack, resume downloads and verify source audio.

Run with the project virtualenv: python scripts/fetch_voice.py.
The pinned archive and extracted WAVs remain under ignored data/.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import time
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
REVISION = "40f1331762b2bd6b38a8c9ac4b5d6dfbf0a50b11"
ARCHIVE = "maple_collections_voice.zip"
SIZE = 2357726654
SHA256 = "fcbe7a7e1af7eef40eed874c457f604dc02e9b4c119bd913a5b24a52b5164234"
URL = f"https://huggingface.co/datasets/nuxsh/maple-collections-hackathon/resolve/{REVISION}/{ARCHIVE}"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def download(target: Path) -> None:
    if target.exists():
        return
    partial = target.with_suffix(".zip.part")
    offset = partial.stat().st_size if partial.exists() else 0
    if offset > SIZE:
        raise ValueError("Partial voice archive exceeds published size; remove it and retry.")
    if offset < SIZE:
        request = urllib.request.Request(URL, headers={"Range": f"bytes={offset}-"} if offset else {})
        with urllib.request.urlopen(request, timeout=60) as response:
            if offset and response.status != 206:
                offset = 0  # Server ignored Range: restart safely instead of appending.
            elif offset and not response.headers.get("Content-Range", "").startswith(f"bytes {offset}-"):
                raise ValueError("Publisher returned an unexpected download range.")
            with partial.open("ab" if offset else "wb") as output:
                last = time.monotonic()
                while chunk := response.read(8 * 1024 * 1024):
                    output.write(chunk)
                    offset += len(chunk)
                    if time.monotonic() - last >= 10:
                        print(f"Voice archive: {offset / SIZE:.1%} ({offset:,}/{SIZE:,} bytes)", flush=True)
                        last = time.monotonic()
    if partial.stat().st_size != SIZE or sha256(partial) != SHA256:
        raise ValueError("Voice archive does not match the publisher's size/checksum.")
    partial.replace(target)


def safe_voice_members(archive: zipfile.ZipFile) -> list[tuple[zipfile.ZipInfo, str]]:
    members = []
    seen = set()
    for item in archive.infolist():
        path = PurePosixPath(item.filename)
        if path.is_absolute() or ".." in path.parts or "\\" in item.filename:
            raise ValueError("Unsafe path in voice archive.")
        if stat.S_ISLNK(item.external_attr >> 16):
            raise ValueError("Archive symlinks are not accepted.")
        # The publisher README specifies copying the pack's files/ folder into
        # maple_collections_release; retain its files/voice/<id>.wav structure.
        if not item.is_dir() and len(path.parts) >= 3 and path.parts[-3:-1] == ("files", "voice"):
            name = path.name
            if not name.endswith(".wav") or name in seen:
                raise ValueError("Unexpected or duplicate voice member.")
            members.append((item, name))
            seen.add(name)
    if not members:
        raise ValueError("Voice archive contains no files/voice WAV recordings.")
    return members


def fetch() -> dict:
    data = ROOT / "data"
    data.mkdir(exist_ok=True)
    release = Path(os.environ.get("COPILOT_DATASET", str(data / "maple_collections_release")))
    metadata = release / "data" / "voice_samples.csv"
    if not metadata.exists():
        raise FileNotFoundError("Download the main dataset before fetching its optional voice pack.")
    target = data / ARCHIVE
    print(f"Pinned official voice pack: {REVISION}", flush=True)
    download(target)
    if target.stat().st_size != SIZE or sha256(target) != SHA256:
        raise ValueError("Existing voice archive fails the publisher checksum; move it aside and retry.")
    with metadata.open(newline="", encoding="utf-8-sig") as source:
        rows = {row["voice_sample_id"] + ".wav": row for row in csv.DictReader(source)}
    destination = release / "files" / "voice"
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target) as archive:
        members = safe_voice_members(archive)
        if set(name for _, name in members) != set(rows):
            raise ValueError("Voice pack membership does not match voice_samples.csv.")
        for index, (item, name) in enumerate(members, 1):
            output = destination / name
            row = rows[name]
            if not (output.exists() and output.stat().st_size == int(row["file_size_bytes"]) and sha256(output) == row["checksum_sha256"]):
                partial = output.with_suffix(".wav.part")
                with archive.open(item) as source, partial.open("wb") as out:
                    shutil.copyfileobj(source, out, length=1024 * 1024)
                if partial.stat().st_size != int(row["file_size_bytes"]) or sha256(partial) != row["checksum_sha256"]:
                    raise ValueError(f"Voice sample checksum mismatch: {name}")
                partial.replace(output)
            if index % 250 == 0:
                print(f"Verified voice recordings: {index}/{len(members)}", flush=True)
    provenance = {"revision": REVISION, "url": URL, "sha256": SHA256,
                  "archive_bytes": SIZE, "verified_against_publisher": True,
                  "verified_recordings": len(rows), "per_recording_checksums_verified": True,
                  "destination": str(destination.relative_to(ROOT)) if destination.is_relative_to(ROOT) else str(destination)}
    (data / "voice-provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    print(f"Ready: {len(rows)} verified WAV recordings in {destination}", flush=True)
    return provenance


if __name__ == "__main__":
    fetch()
