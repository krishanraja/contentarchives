"""The tests that matter.

Each one encodes a failure that actually happened. If one of these starts failing,
the toolkit has regressed into a state that previously destroyed data.

    python -m pytest tests/ -v        (or just: python tests/test_safety_and_dedupe.py)
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from contentarchives.dedupe import Index, file_hash, file_signature  # noqa: E402
from contentarchives.safety import DeletionRefused, Guard, looks_camera_original  # noqa: E402


# --------------------------------------------------------------------- safety

def test_guard_refuses_library_files():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        lib, scratch = root / "library", root / "scratch"
        lib.mkdir(); scratch.mkdir()
        victim = lib / "2019" / "IMG_0001.jpg"
        victim.parent.mkdir(parents=True); victim.write_bytes(b"x")

        g = Guard(scratch_dir=scratch, protected_roots=[lib])
        for reason in ("scratch", "verified-duplicate", "consumed-archive"):
            assert g.would_refuse(victim, reason, proof=victim, accounted=True)
        assert victim.exists(), "guard must not have deleted a protected file"


def test_guard_refuses_the_file_that_was_actually_lost():
    """The real path that a '\\Downloads\\' substring rule destroyed."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        scratch = root / "scratch"; scratch.mkdir()
        victim = (root / "work backup 2020" / "Downloads"
                  / "Samsung S9 Edge Backup - April 2019" / "DCIM" / "Camera"
                  / "20181019_215516.mp4")
        victim.parent.mkdir(parents=True); victim.write_bytes(b"x")
        other = root / "elsewhere.mp4"; other.write_bytes(b"x")

        g = Guard(scratch_dir=scratch, protected_roots=[])
        assert g.would_refuse(victim, "scratch")
        # even with a genuine duplicate proof, camera-originals are refused
        msg = g.would_refuse(victim, "verified-duplicate", proof=other)
        assert msg and "camera-original" in msg
        assert victim.exists()


def test_guard_refuses_scratch_inside_a_protected_root():
    """If scratch lived inside the library, the scratch allowlist would be a hole
    straight through the guard."""
    with tempfile.TemporaryDirectory() as tmp:
        lib = Path(tmp) / "library"; (lib / "tmp").mkdir(parents=True)
        try:
            Guard(scratch_dir=lib / "tmp", protected_roots=[lib])
        except DeletionRefused:
            return
        raise AssertionError("Guard accepted scratch inside a protected root")


def test_guard_allows_the_narrow_cases():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        scratch = root / "scratch"; scratch.mkdir()
        junk = scratch / "extract.tmp"; junk.write_bytes(b"x")
        arc = root / "archive.zip"; arc.write_bytes(b"x")
        proof = root / "kept.bin"; proof.write_bytes(b"x")
        dupe = root / "spare.bin"; dupe.write_bytes(b"x")

        g = Guard(scratch_dir=scratch, protected_roots=[])
        g.remove(junk, "scratch")
        g.remove(arc, "consumed-archive", accounted=True)
        g.remove(dupe, "verified-duplicate", proof=proof)
        assert not junk.exists() and not arc.exists() and not dupe.exists()
        assert proof.exists()


def test_camera_detection():
    for name in ("IMG_1234.jpg", "PXL_20240101_120000.jpg", "GOPR0144.MP4",
                 "DJI_0257.MP4", "MVI_2617.MOV", "20181019_215516.mp4",
                 "WhatsApp Image 2021-01-01.jpeg"):
        assert looks_camera_original(name), name
    assert looks_camera_original(Path("x") / "DCIM" / "Camera" / "anything.mp4")
    # DVDSCR must not match DSC - this false positive inflated a loss report
    assert not looks_camera_original("The.Wolf.of.Wall.Street.2013.DVDSCR.XviD.avi")
    assert not looks_camera_original("product-homepage-render.mp4")


# --------------------------------------------------------------------- dedupe

def test_same_name_same_size_different_content_is_not_a_duplicate():
    """The exact trap: identical filename, identical byte count, different bytes.
    A name+size shortcut would silently discard the second file."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        held = root / "held"; held.mkdir()
        a = held / "IMG_0002.jpg"; a.write_bytes(b"A" * 4096)
        b = root / "IMG_0002.jpg"; b.write_bytes(b"B" * 4096)   # same name, same size

        idx = Index.from_roots([held])
        assert os.path.getsize(a) == os.path.getsize(b)
        assert idx.find_duplicate(b) is None, "different content declared duplicate"


def test_identical_content_is_found():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        held = root / "held"; held.mkdir()
        a = held / "one.jpg"; a.write_bytes(b"Z" * 4096)
        b = root / "totally_different_name.jpg"; b.write_bytes(b"Z" * 4096)

        idx = Index.from_roots([held])
        assert idx.find_duplicate(b) == str(a), "identical content not matched"


def test_novel_size_short_circuits_without_io():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        held = root / "held"; held.mkdir()
        (held / "a.bin").write_bytes(b"x" * 100)
        idx = Index.from_roots([held])
        assert idx.size_is_novel(999999)
        assert not idx.size_is_novel(100)


def test_signature_is_not_trusted_alone():
    """Head+tail may collide; only the whole-file hash decides."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        head = b"H" * 262144
        tail = b"T" * 262144
        a = root / "a.bin"; a.write_bytes(head + b"\x00" * 1024 + tail)
        b = root / "b.bin"; b.write_bytes(head + b"\xff" * 1024 + tail)
        assert file_signature(a) == file_signature(b), "expected a signature collision"
        assert file_hash(a) != file_hash(b)

        held = root / "held"; held.mkdir()
        moved = held / "a.bin"; a.rename(moved)
        idx = Index.from_roots([held])
        assert idx.find_duplicate(b) is None, "signature collision declared a duplicate"


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  PASS  {name}")
            except Exception as exc:                       # noqa: BLE001
                failures += 1
                print(f"  FAIL  {name}: {exc}")
    print(f"\n{'all tests passed' if not failures else f'{failures} FAILED'}")
    sys.exit(1 if failures else 0)
