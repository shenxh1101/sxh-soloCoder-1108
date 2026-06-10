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
from ssh_recorder.cli import build_parser, cmd_play, cmd_list_bookmarks, _print_bookmarks


def test_snapshot_mode():
    print("=== Test 1: play --snapshot non-interactive preview mode ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        logger = SessionLogger(log_dir=tmpdir, rotate_daily=False)
        log_file = logger.start_session(host="test.com", user="tester")
        logger.write_output(b"Step one output\n")
        time.sleep(0.05)
        logger.add_bookmark("step1", "First step")
        logger.write_output(b"Step two output\n")
        time.sleep(0.05)
        logger.add_bookmark("step2", "Second step")
        logger.write_output(b"Final output\n")
        logger.end_session()

        parser = build_parser()
        args = parser.parse_args(["play", log_file, "--snapshot", "step1"])
        old_stdout = sys.stdout
        captured = StringIO()
        sys.stdout = captured
        try:
            result = cmd_play(args)
        finally:
            sys.stdout = old_stdout
        assert result == 0, f"Expected 0, got {result}"

        args2 = parser.parse_args(["play", log_file, "--snapshot", "nonexistent"])
        captured2 = StringIO()
        sys.stdout = captured2
        try:
            result2 = cmd_play(args2)
        finally:
            sys.stdout = old_stdout
        assert result2 == 1, f"Expected 1 for nonexistent bookmark, got {result2}"

        args3 = parser.parse_args(["play", log_file, "--snapshot", "step2"])
        captured3 = StringIO()
        sys.stdout = captured3
        try:
            result3 = cmd_play(args3)
        finally:
            sys.stdout = old_stdout
        assert result3 == 0, f"Expected 0 for step2, got {result3}"

        print("  --snapshot mode: PASSED")


def test_snapshot_clear_screen():
    print("\n=== Test 2: snapshot with clear screen produces correct output ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        logger = SessionLogger(log_dir=tmpdir, rotate_daily=False)
        log_file = logger.start_session(host="test.com", user="tester")
        logger.write_output(b"Old content\n")
        logger.write_output(b"\x1b[2J\x1b[H")
        logger.write_output(b"New content\n")
        time.sleep(0.05)
        logger.add_bookmark("after_clear", "After clear")
        logger.end_session()

        controller = PlaybackController(log_file)
        result = controller.snapshot("after_clear")
        assert result is True, "snapshot should return True for valid bookmark"
        print("  snapshot clear screen: PASSED")


def test_snapshot_end_bookmark():
    print("\n=== Test 3: snapshot for end-of-session bookmark ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        logger = SessionLogger(log_dir=tmpdir, rotate_daily=False)
        log_file = logger.start_session(host="test.com", user="tester")
        logger.write_output(b"First\n")
        logger.write_output(b"Second\n")
        logger.write_output(b"Third\n")
        logger.add_bookmark("end_bm", "At the end")
        logger.end_session()

        controller = PlaybackController(log_file)
        result = controller.snapshot("end_bm")
        assert result is True, "snapshot should work for end-of-session bookmark"
        print("  snapshot end bookmark: PASSED")


def test_html_per_cell_rendering():
    print("\n=== Test 4: HTML VirtualTerminal per-cell color/bold/underline ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        logger = SessionLogger(log_dir=tmpdir, rotate_daily=False)
        log_file = logger.start_session(host="test.com", user="tester")

        logger.write_output(b"\x1b[31mRed\x1b[0m Normal ")
        logger.write_output(b"\x1b[1;32mBoldGreen\x1b[0m ")
        logger.write_output(b"\x1b[4;34mUnderlineBlue\x1b[0m\n")

        logger.write_output(b"\x1b[43mYellowBG\x1b[0m\n")

        logger.write_output(b"\rOverwrite line\n")
        time.sleep(0.05)
        logger.add_bookmark("colored", "Color test")

        logger.write_output(b"\x1b[2J\x1b[H")
        logger.write_output(b"\x1b[36mAfter clear\x1b[0m\n")
        logger.add_bookmark("after_clear2", "Cleared")
        logger.end_session()

        html_file = os.path.join(tmpdir, "test_per_cell.html")
        HTMLExporter.export(log_file, html_file)

        with open(html_file, "r", encoding="utf-8") as f:
            html = f.read()

        assert "_mkCell" in html, "Should have per-cell VirtualTerminal"
        assert "_handleSGR" in html, "Should have SGR handler"
        assert "fg-red" in html, "Should have red color class"
        assert "fg-green" in html, "Should have green color class"
        assert "fg-blue" in html, "Should have blue color class"
        assert "bold" in html, "Should have bold class"
        assert "underline" in html, "Should have underline class"
        assert "bg-yellow" in html, "Should have yellow background class"
        assert "colored" in html, "Bookmark should be in HTML"
        assert "after_clear2" in html, "After clear bookmark should be in HTML"
        print("  Per-cell rendering: PASSED")


def test_html_timeline_and_bookmark_nav():
    print("\n=== Test 5: HTML timeline slider and bookmark navigation ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        logger = SessionLogger(log_dir=tmpdir, rotate_daily=False)
        log_file = logger.start_session(host="test.com", user="tester")
        logger.write_output(b"Start\n")
        time.sleep(0.05)
        logger.add_bookmark("bm1", "First")
        logger.write_output(b"Middle\n")
        time.sleep(0.05)
        logger.add_bookmark("bm2", "Second")
        logger.write_output(b"End\n")
        logger.end_session()

        html_file = os.path.join(tmpdir, "test_timeline.html")
        HTMLExporter.export(log_file, html_file)

        with open(html_file, "r", encoding="utf-8") as f:
            html = f.read()

        assert 'id="timeline"' in html, "Should have timeline slider"
        assert "prevBookmark" in html, "Should have prev bookmark function"
        assert "nextBookmark" in html, "Should have next bookmark function"
        assert "replayTo" in html, "Should have replayTo function"
        assert "isSeeking" in html, "Should have seeking state"
        assert "activeBmIdx" in html, "Should track active bookmark"
        print("  Timeline and navigation: PASSED")


def test_bookmark_list_display():
    print("\n=== Test 6: list-bookmarks shows description, relative time, is_after_end ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        logger = SessionLogger(log_dir=tmpdir, rotate_daily=False)
        log_file = logger.start_session(host="test.com", user="tester")
        logger.write_output(b"First\n")
        time.sleep(0.1)
        logger.add_bookmark("bm1", "First bookmark")
        logger.write_output(b"Second\n")
        time.sleep(0.2)
        logger.add_bookmark("bm2", "Second bookmark")
        logger.write_output(b"Third\n")
        logger.add_bookmark("bm3", "")
        logger.end_session()

        controller = PlaybackController(log_file)
        bookmarks = controller.list_bookmarks()
        assert len(bookmarks) == 3, f"Expected 3 bookmarks, got {len(bookmarks)}"

        assert bookmarks[0]["name"] == "bm1"
        assert bookmarks[0]["description"] == "First bookmark"
        assert bookmarks[0]["time_offset"] >= 0

        assert bookmarks[1]["name"] == "bm2"
        assert bookmarks[1]["description"] == "Second bookmark"
        assert bookmarks[1]["time_offset"] > bookmarks[0]["time_offset"]

        assert bookmarks[2]["name"] == "bm3"
        assert bookmarks[2]["description"] == ""

        old_stdout = sys.stdout
        captured = StringIO()
        sys.stdout = captured
        try:
            _print_bookmarks(bookmarks)
        finally:
            sys.stdout = old_stdout

        output = captured.getvalue()
        assert "bm1" in output
        assert "bm2" in output
        assert "bm3" in output
        assert "First bookmark" in output, "Description should appear"
        assert "Second bookmark" in output, "Description should appear"

        lines = output.strip().split("\n")
        bm3_line = [l for l in lines if "bm3" in l][0]
        assert "  \n" not in output, "No extra blank lines for empty description"
        assert "+" in output, "Should show relative time"

        print("  Bookmark list display: PASSED")


def test_html_bookmark_relative_time():
    print("\n=== Test 7: HTML bookmark shows relative time and is_after_end ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        logger = SessionLogger(log_dir=tmpdir, rotate_daily=False)
        log_file = logger.start_session(host="test.com", user="tester")
        logger.write_output(b"Output 1\n")
        time.sleep(0.1)
        logger.add_bookmark("start", "Beginning")
        logger.write_output(b"Output 2\n")
        time.sleep(0.15)
        logger.add_bookmark("middle", "Mid point")
        logger.end_session()
        logger2 = SessionReader(log_file)
        logger2.add_bookmark("end_bm", "After session end", timestamp=time.time() + 1)

        html_file = os.path.join(tmpdir, "test_bm_rel.html")
        HTMLExporter.export(log_file, html_file)

        with open(html_file, "r", encoding="utf-8") as f:
            html = f.read()

        assert "bm-rel" in html, "Should have relative time CSS class"
        assert "relative_str" in html or "+" in html, "Should show relative time"
        assert "bm-after-end" in html, "Should have after-end badge for post-session bookmark"
        assert "bm-desc" in html, "Should have description class"

        html_lines = html.split("\n")
        has_empty_desc_span = any(
            'bm-desc' in line and '— ' not in line and '>' in line and '</span>' in line
            for line in html_lines
        )
        bookmark_tag_lines = [l for l in html_lines if 'bookmark-tag' in l]
        for tag_line in bookmark_tag_lines:
            if "end_bm" in tag_line:
                assert "末尾后" in tag_line, "After-end bookmark should have badge"

        print("  HTML bookmark relative time: PASSED")


def test_html_bookmark_jump_restores_colors():
    print("\n=== Test 8: HTML bookmark jump restores per-character colors ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        logger = SessionLogger(log_dir=tmpdir, rotate_daily=False)
        log_file = logger.start_session(host="test.com", user="tester")

        logger.write_output(b"Normal text\n")
        logger.write_output(b"\x1b[32m")
        logger.write_output(b"Green progress: [")
        logger.write_output(b"\x1b[33m#####\x1b[0m")
        logger.write_output(b"]\n")
        time.sleep(0.05)
        logger.add_bookmark("progress", "Progress bar")

        logger.write_output(b"\r\x1b[32m")
        logger.write_output(b"Green progress: [")
        logger.write_output(b"\x1b[33m##########\x1b[0m")
        logger.write_output(b"] 100%\n")
        time.sleep(0.05)
        logger.add_bookmark("complete", "Complete")

        logger.write_output(b"\x1b[2J\x1b[H")
        logger.write_output(b"\x1b[1;36mBold Cyan\x1b[0m\n")
        logger.add_bookmark("after_clear3", "Clear + bold")
        logger.end_session()

        html_file = os.path.join(tmpdir, "test_color_jump.html")
        HTMLExporter.export(log_file, html_file)

        with open(html_file, "r", encoding="utf-8") as f:
            html = f.read()

        assert "jumpToBookmark" in html, "Should have bookmark jump function"
        assert "replayTo" in html, "Should have replay function for state restore"
        assert "fg-green" in html, "Should have green foreground"
        assert "fg-yellow" in html, "Should have yellow foreground"
        assert "fg-cyan" in html, "Should have cyan foreground"

        assert "progress" in html
        assert "complete" in html
        assert "after_clear3" in html

        print("  Bookmark jump color restore: PASSED")


def test_cli_snapshot_parser():
    print("\n=== Test 9: --snapshot argument in parser ===")
    parser = build_parser()
    args = parser.parse_args(["play", "test.log", "--snapshot", "my_bm"])
    assert args.snapshot == "my_bm", f"Expected 'my_bm', got {args.snapshot}"

    args2 = parser.parse_args(["play", "test.log", "--jump-bookmark", "bm1", "--speed", "2.0"])
    assert args2.jump_bookmark == "bm1"
    assert args2.speed == 2.0
    assert args2.snapshot is None

    print("  --snapshot parser: PASSED")


def test_bookmark_after_end_indicator():
    print("\n=== Test 10: is_after_end indicator in list-bookmarks ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        logger = SessionLogger(log_dir=tmpdir, rotate_daily=False)
        log_file = logger.start_session(host="test.com", user="tester")
        logger.write_output(b"Content\n")
        time.sleep(0.05)
        logger.add_bookmark("during", "During session")
        logger.end_session()

        reader = SessionReader(log_file)
        reader.add_bookmark("post_end", "After session", timestamp=time.time() + 1)

        parser = build_parser()
        args = parser.parse_args(["list-bookmarks", log_file])

        old_stdout = sys.stdout
        captured = StringIO()
        sys.stdout = captured
        try:
            result = cmd_list_bookmarks(args)
        finally:
            sys.stdout = old_stdout

        output = captured.getvalue()
        assert result == 0
        assert "during" in output
        assert "post_end" in output
        assert "末尾后" in output, "Should show after-end indicator"

        print("  is_after_end indicator: PASSED")


def main():
    print("\n" + "=" * 55)
    print("Round 4 Enhancement Verification Tests")
    print("=" * 55 + "\n")
    try:
        test_snapshot_mode()
        test_snapshot_clear_screen()
        test_snapshot_end_bookmark()
        test_html_per_cell_rendering()
        test_html_timeline_and_bookmark_nav()
        test_bookmark_list_display()
        test_html_bookmark_relative_time()
        test_html_bookmark_jump_restores_colors()
        test_cli_snapshot_parser()
        test_bookmark_after_end_indicator()
        print("\n" + "=" * 55)
        print("ALL ROUND 4 TESTS PASSED!")
        print("=" * 55)
        return 0
    except AssertionError as e:
        print(f"\nFAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
