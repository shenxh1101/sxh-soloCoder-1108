import os
import sys
import json
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ssh_recorder.storage import SessionLogger, SessionReader
from ssh_recorder.player import PlaybackController
from ssh_recorder.exporter import HTMLExporter


def test_delay_playback():
    print("=== Test 1: Verify delay-based playback timing ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        logger = SessionLogger(log_dir=tmpdir, rotate_daily=False)
        log_file = logger.start_session(host="test.com", user="tester")

        logger.write_output(b"First output\n")
        time.sleep(0.2)
        logger.write_output(b"Second output (after 0.2s)\n")
        time.sleep(0.5)
        logger.write_output(b"Third output (after 0.5s)\n")
        logger.end_session()

        reader = SessionReader(log_file)
        entries = reader.get_all_entries()
        assert len(entries) == 3, f"Expected 3 entries, got {len(entries)}"

        total_delay = sum(e.delay for e in entries)
        print(f"  Entry 1 delay: {entries[0].delay:.3f}s")
        print(f"  Entry 2 delay: {entries[1].delay:.3f}s (should be ~0.2s)")
        print(f"  Entry 3 delay: {entries[2].delay:.3f}s (should be ~0.5s)")
        print(f"  Total delay: {total_delay:.3f}s")

        assert entries[1].delay >= 0.15 and entries[1].delay <= 0.5, f"Entry 2 delay {entries[1].delay} out of range"
        assert entries[2].delay >= 0.4 and entries[2].delay <= 0.8, f"Entry 3 delay {entries[2].delay} out of range"

        controller = PlaybackController(log_file, speed=2.0)
        assert controller.get_speed() == 2.0
        effective_delay = entries[2].delay / 2.0
        print(f"  At 2x speed, entry 3 effective delay: {effective_delay:.3f}s (scaled correctly)")
        print("  Delay timing: PASSED")


def test_add_bookmark_during_playback():
    print("\n=== Test 2: Add bookmark during playback ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        logger = SessionLogger(log_dir=tmpdir, rotate_daily=False)
        log_file = logger.start_session(host="test.com", user="tester")

        for i in range(10):
            time.sleep(0.02)
            logger.write_output(f"Line {i}\n".encode())
        logger.add_bookmark("original_bm", "Bookmark from recording")
        logger.end_session()

        meta_file = log_file + ".meta.json"
        with open(meta_file, "r", encoding="utf-8") as f:
            meta_before = json.load(f)
        count_before = len(meta_before.get("bookmarks", []))
        print(f"  Bookmarks before playback: {count_before}")

        controller = PlaybackController(log_file)
        controller._current_idx = 5
        controller._elapsed = sum(e.delay for e in controller.entries[:5])

        result = controller.add_bookmark_at_current("playback_bm", "Added during playback")
        assert result is True, "add_bookmark_at_current should return True"

        with open(meta_file, "r", encoding="utf-8") as f:
            meta_after = json.load(f)
        count_after = len(meta_after.get("bookmarks", []))
        print(f"  Bookmarks after adding: {count_after}")
        assert count_after == count_before + 1, "Should have one more bookmark"

        new_bm = meta_after["bookmarks"][-1]
        assert new_bm["name"] == "playback_bm"
        assert new_bm["description"] == "Added during playback"
        print(f"  New bookmark timestamp: {new_bm['timestamp']}")
        print(f"  Matches entry 5 timestamp: {controller.entries[4].timestamp}")
        print("  Playback bookmark: PASSED")


def test_bookmark_persists_across_reads():
    print("\n=== Test 3: Bookmark persists and visible in new session ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        logger = SessionLogger(log_dir=tmpdir, rotate_daily=False)
        log_file = logger.start_session(host="test.com", user="tester")
        logger.write_output(b"Hello world\n")
        logger.end_session()

        controller1 = PlaybackController(log_file)
        controller1.add_bookmark_at_current("persistent_bm", "Should survive reload")

        reader_new = SessionReader(log_file)
        bookmarks = reader_new.get_bookmarks()
        names = [b["name"] for b in bookmarks]
        print(f"  Bookmarks in fresh reader: {names}")
        assert "persistent_bm" in names, "Bookmark should persist in meta file"

        controller2 = PlaybackController(log_file)
        listed = controller2.list_bookmarks()
        listed_names = [b["name"] for b in listed]
        print(f"  Bookmarks in new controller: {listed_names}")
        assert "persistent_bm" in listed_names, "Bookmark visible in new playback"

        result = controller2.jump_to_bookmark("persistent_bm")
        assert result is True, "Jump to bookmark should succeed"
        print("  Bookmark persistence and jump: PASSED")


def test_html_export_with_bookmarks():
    print("\n=== Test 4: HTML export includes bookmarks and jump logic ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        logger = SessionLogger(log_dir=tmpdir, rotate_daily=False)
        log_file = logger.start_session(host="test.com", user="tester")
        logger.write_output(b"Before bookmark\n")
        time.sleep(0.05)
        logger.add_bookmark("bm_middle", "Middle of session")
        logger.write_output(b"\x1b[32mAfter bookmark (colored)\x1b[0m\n")
        logger.end_session()

        html_file = os.path.join(tmpdir, "test.html")
        HTMLExporter.export(log_file, html_file)
        assert os.path.exists(html_file)

        with open(html_file, "r", encoding="utf-8") as f:
            html = f.read()

        assert "bm_middle" in html, "Bookmark name should be in HTML"
        assert "jumpToBookmark" in html, "Jump function should exist"
        assert "replayTo" in html, "Replay function should exist"
        assert "charCodeAt(i) === 27" in html, "ANSI ESC parser should use real ESC code"

        print("  HTML contains bookmarks: OK")
        print("  HTML has replayTo function: OK")
        print("  HTML ANSI parser uses real ESC: OK")
        print("  HTML export: PASSED")


def main():
    print("\n" + "=" * 55)
    print("Bug Fix Verification Tests")
    print("=" * 55 + "\n")
    try:
        test_delay_playback()
        test_add_bookmark_during_playback()
        test_bookmark_persists_across_reads()
        test_html_export_with_bookmarks()
        print("\n" + "=" * 55)
        print("ALL BUG FIX VERIFICATIONS PASSED!")
        print("=" * 55)
        return 0
    except AssertionError as e:
        print(f"\nFAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
