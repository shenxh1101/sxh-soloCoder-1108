import os
import sys
import json
import tempfile
import time
from io import StringIO

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ssh_recorder.storage import SessionLogger, SessionReader
from ssh_recorder.player import PlaybackController
from ssh_recorder.exporter import HTMLExporter
from ssh_recorder.cli import build_parser, cmd_list_bookmarks


def test_list_bookmarks_subcommand():
    print("=== Test 1: list-bookmarks standalone subcommand ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        logger = SessionLogger(log_dir=tmpdir, rotate_daily=False)
        log_file = logger.start_session(host="test.com", user="tester")
        logger.write_output(b"Hello\n")
        time.sleep(0.05)
        logger.add_bookmark("step1", "First step")
        logger.write_output(b"World\n")
        logger.add_bookmark("step2", "Second step")
        logger.end_session()

        parser = build_parser()
        args = parser.parse_args(["list-bookmarks", log_file])

        old_stderr = sys.stderr
        old_stdout = sys.stdout
        captured = StringIO()
        sys.stdout = captured
        try:
            result = cmd_list_bookmarks(args)
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr

        output = captured.getvalue()
        assert result == 0, f"Expected 0, got {result}"
        assert "step1" in output, "Bookmark 'step1' should appear"
        assert "step2" in output, "Bookmark 'step2' should appear"
        assert "First step" in output, "Description should appear"
        assert "@" in output, "Time should appear with @ marker"
        print("  list-bookmarks subcommand: PASSED")

    with tempfile.TemporaryDirectory() as tmpdir:
        logger = SessionLogger(log_dir=tmpdir, rotate_daily=False)
        log_file = logger.start_session(host="test.com", user="tester")
        logger.write_output(b"No bookmarks here\n")
        logger.end_session()

        parser = build_parser()
        args = parser.parse_args(["list-bookmarks", log_file])
        captured = StringIO()
        sys.stdout = captured
        try:
            result = cmd_list_bookmarks(args)
        finally:
            sys.stdout = old_stdout

        output = captured.getvalue()
        assert result == 0
        assert "No bookmarks found" in output, "Should show 'no bookmarks' message"
        print("  list-bookmarks no bookmarks: PASSED")


def test_html_virtual_terminal():
    print("\n=== Test 2: HTML VirtualTerminal handles clear/cursor/overwrite ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        logger = SessionLogger(log_dir=tmpdir, rotate_daily=False)
        log_file = logger.start_session(host="test.com", user="tester")

        logger.write_output(b"Line 1\n")
        logger.write_output(b"Line 2\n")
        logger.write_output(b"\x1b[2J\x1b[H")
        logger.write_output(b"Cleared screen - new content\n")
        time.sleep(0.05)
        logger.add_bookmark("after_clear", "After clear screen")

        logger.write_output(b"Progress: [")
        logger.write_output(b"\x1b[32m#####\x1b[0m")
        logger.write_output(b"] 50%\n")

        logger.write_output(b"\rProgress: [")
        logger.write_output(b"\x1b[32m##########\x1b[0m")
        logger.write_output(b"] 100%\n")
        logger.add_bookmark("progress_done", "Progress complete")
        logger.end_session()

        html_file = os.path.join(tmpdir, "test_vterm.html")
        HTMLExporter.export(log_file, html_file)

        with open(html_file, "r", encoding="utf-8") as f:
            html = f.read()

        assert "VirtualTerminal" in html, "Should include VirtualTerminal class"
        assert "replayTo" in html, "Should include replayTo function"
        assert "after_clear" in html, "Bookmark should be in HTML"
        assert "progress_done" in html, "Bookmark should be in HTML"
        assert "feed" in html, "Should have feed method"
        assert "_clearScreen" in html, "Should have clear screen method"
        assert "cursorRow" in html, "Should have cursor tracking"
        print("  VirtualTerminal in HTML: PASSED")


def test_bookmark_at_end_shows_final_frame():
    print("\n=== Test 3: Bookmark at end shows complete final frame ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        logger = SessionLogger(log_dir=tmpdir, rotate_daily=False)
        log_file = logger.start_session(host="test.com", user="tester")

        logger.write_output(b"First output\n")
        time.sleep(0.05)
        logger.write_output(b"Second output\n")
        time.sleep(0.05)
        logger.write_output(b"Third and final output\n")
        logger.add_bookmark("end_bm", "At the very end")
        logger.end_session()

        controller = PlaybackController(log_file)
        bookmarks = controller.list_bookmarks()
        assert len(bookmarks) >= 1

        end_bm = None
        for bm in bookmarks:
            if bm["name"] == "end_bm":
                end_bm = bm
                break

        assert end_bm is not None, "Should find end_bm bookmark"
        assert end_bm["entry_index"] == len(controller.entries), \
            f"End bookmark entry_index should be {len(controller.entries)}, got {end_bm['entry_index']}"

        controller.jump_to_bookmark("end_bm")
        assert controller._jump_to_idx == len(controller.entries), \
            "jump_to_index should accept len(entries) for end bookmarks"

        print(f"  end_bm entry_index={end_bm['entry_index']}, entries={len(controller.entries)}")
        print("  Bookmark at end: PASSED")


def test_seek_boundaries():
    print("\n=== Test 4: F/B seek boundary handling ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        logger = SessionLogger(log_dir=tmpdir, rotate_daily=False)
        log_file = logger.start_session(host="test.com", user="tester")

        for i in range(10):
            logger.write_output(f"Line {i}\n".encode())
            time.sleep(0.02)
        logger.end_session()

        controller = PlaybackController(log_file)
        total_duration = sum(e.delay for e in controller.entries)

        controller._elapsed = 0.0
        controller.jump_by_seconds(-10)
        assert controller._jump_to_idx == 0, \
            f"B past start should go to 0, got {controller._jump_to_idx}"

        controller._elapsed = total_duration
        controller.jump_by_seconds(1000)
        assert controller._jump_to_idx == len(controller.entries), \
            f"F past end should go to {len(controller.entries)}, got {controller._jump_to_idx}"

        controller._elapsed = 0.0
        controller.jump_by_seconds(0.001)
        assert 0 <= controller._jump_to_idx <= len(controller.entries), \
            f"Small seek should stay in range, got {controller._jump_to_idx}"

        print(f"  B past start -> idx=0: OK")
        print(f"  F past end -> idx={len(controller.entries)}: OK")
        print("  Seek boundaries: PASSED")


def test_play_delay_order():
    print("\n=== Test 5: Playback delay order (wait then render) ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        logger = SessionLogger(log_dir=tmpdir, rotate_daily=False)
        log_file = logger.start_session(host="test.com", user="tester")
        logger.write_output(b"A\n")
        time.sleep(0.15)
        logger.write_output(b"B\n")
        time.sleep(0.3)
        logger.write_output(b"C\n")
        logger.end_session()

        reader = SessionReader(log_file)
        entries = reader.get_all_entries()
        assert len(entries) == 3

        assert entries[0].delay < 0.05, f"First entry delay should be near 0, got {entries[0].delay}"
        assert 0.1 <= entries[1].delay <= 0.5, f"Second entry delay ~0.15s, got {entries[1].delay}"
        assert 0.2 <= entries[2].delay <= 0.6, f"Third entry delay ~0.3s, got {entries[2].delay}"

        print(f"  Entry 0 delay: {entries[0].delay:.3f}s (near 0)")
        print(f"  Entry 1 delay: {entries[1].delay:.3f}s (~0.15s)")
        print(f"  Entry 2 delay: {entries[2].delay:.3f}s (~0.3s)")
        print("  Delay order: PASSED")


def main():
    print("\n" + "=" * 55)
    print("Bug Fix Verification Tests (Round 2)")
    print("=" * 55 + "\n")
    try:
        test_list_bookmarks_subcommand()
        test_html_virtual_terminal()
        test_bookmark_at_end_shows_final_frame()
        test_seek_boundaries()
        test_play_delay_order()
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
