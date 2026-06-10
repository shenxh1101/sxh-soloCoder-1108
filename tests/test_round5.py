import os
import sys
import json
import tempfile
import time
from io import StringIO

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ssh_recorder.storage import SessionLogger, SessionReader
from ssh_recorder.player import PlaybackController
from ssh_recorder.vterminal import VirtualTerminal, Cell
from ssh_recorder.exporter import HTMLExporter
from ssh_recorder.cli import build_parser, cmd_compare, cmd_play


def test_vterminal_basic():
    print("=== Test 1: Python VirtualTerminal basic functionality ===")
    vt = VirtualTerminal()
    vt.feed("Hello World\n")
    vt.feed("Second line\r")
    vt.feed("Overwritten\n")

    text = vt.get_plain_text()
    lines = text.split("\n")

    assert len(lines) >= 3, f"Expected at least 3 lines, got {len(lines)}"
    assert "Hello World" in lines[0], f"Line 0 should contain 'Hello World', got: {repr(lines[0])}"
    assert "Overwritten" in lines[1], f"Line 1 should contain 'Overwritten', got: {repr(lines[1])}"

    print(f"  Plain text lines: {len(lines)}")
    print(f"  Line 0: {repr(lines[0])}")
    print(f"  Line 1: {repr(lines[1])}")
    print("  VirtualTerminal basic: PASSED")


def test_vterminal_clear_screen():
    print("\n=== Test 2: VirtualTerminal clear screen ===")
    vt = VirtualTerminal()
    vt.feed("Line 1\n")
    vt.feed("Line 2\n")
    vt.feed("Line 3\n")
    vt.feed("\x1b[2J\x1b[H")
    vt.feed("New content\n")

    text = vt.get_plain_text()
    lines = text.split("\n")

    assert "Line 1" not in text, "Old content should be cleared"
    assert "New content" in text, "New content should be present"
    assert lines[0].strip() == "New content", f"First line should be 'New content', got: {repr(lines[0])}"

    print(f"  After clear, first line: {repr(lines[0])}")
    print("  VirtualTerminal clear screen: PASSED")


def test_vterminal_colors_and_styles():
    print("\n=== Test 3: VirtualTerminal color/bold/underline per-cell ===")
    vt = VirtualTerminal()
    vt.feed("Normal ")
    vt.feed("\x1b[31mRed\x1b[0m ")
    vt.feed("\x1b[1;32mBoldGreen\x1b[0m ")
    vt.feed("\x1b[4;34mUnderBlue\x1b[0m")

    text = vt.get_plain_text()
    assert "Normal" in text
    assert "Red" in text
    assert "BoldGreen" in text
    assert "UnderBlue" in text

    lines = vt.get_lines()
    assert len(lines) >= 1
    line0 = lines[0]

    red_cell = None
    bold_green_cell = None
    underline_blue_cell = None
    for cell in line0:
        if cell.ch == "R" and cell.fg == "31":
            red_cell = cell
        if cell.ch == "B" and cell.bold and cell.fg == "32":
            bold_green_cell = cell
        if cell.ch == "U" and cell.underline and cell.fg == "34":
            underline_blue_cell = cell

    assert red_cell is not None, "Should find red 'R' cell"
    assert bold_green_cell is not None, "Should find bold green 'B' cell"
    assert underline_blue_cell is not None, "Should find underline blue 'U' cell"
    assert not red_cell.bold, "Red cell should not be bold"
    assert not red_cell.underline, "Red cell should not be underline"

    print("  Per-cell color tracking: PASSED")


def test_vterminal_carriage_return_overwrite():
    print("\n=== Test 4: VirtualTerminal carriage return overwrite ===")
    vt = VirtualTerminal()
    vt.feed("Progress: [----------] 0%")
    vt.feed("\rProgress: [#####-----] 50%")
    vt.feed("\rProgress: [##########] 100%")

    text = vt.get_plain_text()
    lines = text.split("\n")

    assert len(lines) >= 1
    assert "100%" in lines[0], "Final line should show 100%"
    assert "----------" not in lines[0], "Old progress bar should be overwritten"
    assert "##########" in lines[0], "New progress bar should be present"

    print(f"  Final line: {repr(lines[0])}")
    print("  Carriage return overwrite: PASSED")


def test_snapshot_text_no_control_codes():
    print("\n=== Test 5: --snapshot-text produces clean text (no control codes) ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        logger = SessionLogger(log_dir=tmpdir, rotate_daily=False)
        log_file = logger.start_session(host="test.com", user="tester")
        logger.write_output(b"\x1b[32mGreen text\x1b[0m\n")
        logger.write_output(b"\x1b[1mBold\x1b[0m normal\n")
        logger.write_output(b"\x1b[2J\x1b[H")
        logger.write_output(b"After clear\n")
        time.sleep(0.05)
        logger.add_bookmark("snap1", "Test snapshot")
        logger.end_session()

        controller = PlaybackController(log_file)
        text = controller.snapshot_text("snap1")
        assert text is not None

        assert "\x1b" not in text, "No ESC sequences in snapshot text"
        assert "[32m" not in text, "No ANSI codes in snapshot text"
        assert "After clear" in text, "Should contain visible text"
        assert "Green text" not in text, "Cleared content should not appear"

        print(f"  Snapshot text:\n{text}")
        print("  --snapshot-text clean output: PASSED")


def test_snapshot_json():
    print("\n=== Test 6: --snapshot-json structured output ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        logger = SessionLogger(log_dir=tmpdir, rotate_daily=False)
        log_file = logger.start_session(host="test.com", user="tester")
        logger.write_output(b"Hello\n")
        time.sleep(0.05)
        logger.add_bookmark("bm_json", "JSON snapshot test")
        logger.end_session()

        controller = PlaybackController(log_file)
        data = controller.snapshot_json("bm_json")
        assert data is not None

        assert "bookmark" in data
        assert data["bookmark"] == "bm_json"
        assert "time_offset" in data
        assert "plain_text" in data
        assert "terminal" in data
        assert "lines" in data["terminal"]
        assert "cursor_row" in data["terminal"]

        assert "Hello" in data["plain_text"]

        print(f"  Keys: {list(data.keys())}")
        print(f"  Terminal keys: {list(data['terminal'].keys())}")
        print("  --snapshot-json structured output: PASSED")


def test_html_script_injection_safety():
    print("\n=== Test 7: HTML export safe against </script> and special chars ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        logger = SessionLogger(log_dir=tmpdir, rotate_daily=False)
        log_file = logger.start_session(host="test.com", user="tester")

        logger.write_output(b"Normal output\n")
        logger.write_output(b"<script>alert('xss')</script>\n")
        logger.write_output(b'{"key": "value", "nested": {"a": 1}}\n')
        logger.write_output(b"<div>html content</div>\n")
        logger.write_output(b"Special: & < > \" ' \n")
        time.sleep(0.05)
        logger.add_bookmark("special", "Special characters test")
        logger.end_session()

        html_file = os.path.join(tmpdir, "test_safe.html")
        HTMLExporter.export(log_file, html_file)

        with open(html_file, "r", encoding="utf-8") as f:
            html = f.read()

        script_tags = html.count("<script>")
        assert script_tags >= 1, "Should have at least the main script tag"

        assert "</script" not in html.replace("</script>", "", 1), \
            "Only one closing </script> tag (the main one), data should be escaped"

        assert "<\\/script>" in html or "<\\u002fscript>" in html or "alert" not in html.split("<script>")[1].split("</script>")[0], \
            "</script> in data should be escaped"

        assert "special" in html, "Bookmark should be present"

        print("  </script> escaping: PASSED")
        print("  HTML special character safety: PASSED")


def test_compare_same_log_two_bookmarks():
    print("\n=== Test 8: compare same log, two different bookmarks ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        logger = SessionLogger(log_dir=tmpdir, rotate_daily=False)
        log_file = logger.start_session(host="test.com", user="tester")
        logger.write_output(b"First state\n")
        logger.write_output(b"Line two\n")
        time.sleep(0.05)
        logger.add_bookmark("state1", "First state")
        logger.write_output(b"\x1b[2J\x1b[H")
        logger.write_output(b"Second state\n")
        logger.write_output(b"Different content\n")
        time.sleep(0.05)
        logger.add_bookmark("state2", "Second state")
        logger.write_output(b"Third line\n")
        logger.add_bookmark("state3", "Third state")
        logger.end_session()

        parser = build_parser()
        args = parser.parse_args(["compare", log_file, "--bm1", "state1", "--bm2", "state1"])
        result = cmd_compare(args)
        assert result == 0, f"Same bookmark should return 0, got {result}"

        args2 = parser.parse_args(["compare", log_file, "--bm1", "state1", "--bm2", "state2"])
        old_stdout = sys.stdout
        captured = StringIO()
        sys.stdout = captured
        try:
            result2 = cmd_compare(args2)
        finally:
            sys.stdout = old_stdout

        assert result2 == 1, f"Different bookmarks should return 1, got {result2}"
        diff_output = captured.getvalue()
        assert "---" in diff_output or "+++" in diff_output, "Should have unified diff output"
        assert "First state" in diff_output or "Second state" in diff_output, "Diff should contain content"

        print("  Compare same/different bookmarks: PASSED")


def test_compare_two_different_logs():
    print("\n=== Test 9: compare two different log files ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        logger1 = SessionLogger(log_dir=tmpdir, rotate_daily=False)
        log1 = logger1.start_session(host="test.com", user="tester", session_id="log1_sess")
        logger1.write_output(b"Log 1 content\n")
        logger1.write_output(b"Hello from log 1\n")
        time.sleep(0.05)
        logger1.add_bookmark("end", "End of log1")
        logger1.end_session()

        logger2 = SessionLogger(log_dir=tmpdir, rotate_daily=False)
        log2 = logger2.start_session(host="test.com", user="tester", session_id="log2_sess")
        logger2.write_output(b"Log 2 content\n")
        logger2.write_output(b"Hello from log 2\n")
        time.sleep(0.05)
        logger2.add_bookmark("end", "End of log2")
        logger2.end_session()

        parser = build_parser()
        args = parser.parse_args(["compare", log1, log2, "--bm1", "end", "--bm2", "end"])
        old_stdout = sys.stdout
        captured = StringIO()
        sys.stdout = captured
        try:
            result = cmd_compare(args)
        finally:
            sys.stdout = old_stdout

        assert result == 1, f"Different logs should return 1, got {result}"
        output = captured.getvalue()
        assert "log 1" in output.lower() or "log 2" in output.lower() or "diff" in output.lower(), \
            "Should show diff content"

        print("  Compare two different logs: PASSED")


def test_compare_quiet_mode_and_errors():
    print("\n=== Test 10: compare quiet mode and error handling ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        logger = SessionLogger(log_dir=tmpdir, rotate_daily=False)
        log_file = logger.start_session(host="test.com", user="tester")
        logger.write_output(b"Test\n")
        time.sleep(0.05)
        logger.add_bookmark("bm1", "Bookmark 1")
        logger.add_bookmark("bm2", "Bookmark 2")
        logger.end_session()

        parser = build_parser()

        args = parser.parse_args(["compare", log_file, "--bm1", "bm1", "--bm2", "bm1", "--quiet"])
        old_stdout = sys.stdout
        captured = StringIO()
        sys.stdout = captured
        try:
            result = cmd_compare(args)
        finally:
            sys.stdout = old_stdout
        assert result == 0, f"Same should return 0, got {result}"
        assert captured.getvalue() == "", "Quiet mode should produce no output"

        args2 = parser.parse_args(["compare", log_file, "--bm1", "nonexistent", "--bm2", "bm1"])
        result2 = cmd_compare(args2)
        assert result2 == 2, f"Missing bookmark should return 2, got {result2}"

        args3 = parser.parse_args(["compare", "nonexistent.log", "--bm1", "x", "--bm2", "y"])
        result3 = cmd_compare(args3)
        assert result3 == 2, f"Missing file should return 2, got {result3}"

        print("  Quiet mode and error handling: PASSED")


def test_html_copy_download_buttons():
    print("\n=== Test 11: HTML has copy and download snapshot buttons ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        logger = SessionLogger(log_dir=tmpdir, rotate_daily=False)
        log_file = logger.start_session(host="test.com", user="tester")
        logger.write_output(b"Some content\n")
        time.sleep(0.05)
        logger.add_bookmark("test", "Test")
        logger.end_session()

        html_file = os.path.join(tmpdir, "test_copy.html")
        HTMLExporter.export(log_file, html_file)

        with open(html_file, "r", encoding="utf-8") as f:
            html = f.read()

        assert "copySnapshot" in html, "Should have copySnapshot function"
        assert "downloadSnapshot" in html, "Should have downloadSnapshot function"
        assert "getPlainText" in html, "Should have getPlainText method"
        assert "📋 复制快照" in html or "复制快照" in html, "Should have copy button"
        assert "💾 下载快照" in html or "下载快照" in html, "Should have download button"
        assert "navigator.clipboard" in html, "Should use clipboard API"
        assert "Blob" in html, "Should use Blob for download"

        print("  Copy/download buttons: PASSED")


def test_cli_help_no_crash():
    print("\n=== Test 12: CLI help for new subcommands works ===")
    parser = build_parser()

    old_stdout = sys.stdout
    old_stderr = sys.stderr
    captured = StringIO()
    sys.stdout = captured
    sys.stderr = captured
    try:
        try:
            parser.parse_args(["compare", "--help"])
        except SystemExit as e:
            assert e.code == 0, f"Help should exit with 0, got {e.code}"
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr

    output = captured.getvalue()
    assert "compare" in output, "Help should mention compare"
    assert "--bm1" in output or "--bookmark1" in output, "Help should mention bookmark args"

    captured2 = StringIO()
    sys.stdout = captured2
    sys.stderr = captured2
    try:
        try:
            parser.parse_args(["play", "--help"])
        except SystemExit as e:
            assert e.code == 0
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr

    output2 = captured2.getvalue()
    assert "--snapshot-text" in output2, "play help should mention --snapshot-text"
    assert "--snapshot-json" in output2, "play help should mention --snapshot-json"

    print("  CLI help: PASSED")


def test_vterminal_cursor_movement():
    print("\n=== Test 13: VirtualTerminal cursor movement ===")
    vt = VirtualTerminal()
    vt.feed("ABCDE")
    vt.feed("\x1b[3D")
    vt.feed("X")

    text = vt.get_plain_text()
    assert "ABXDE" in text, f"Expected ABXDE, got: {repr(text)}"

    vt2 = VirtualTerminal()
    vt2.feed("Line 1\n")
    vt2.feed("Line 2\n")
    vt2.feed("Line 3\n")
    vt2.feed("\x1b[2;3H")
    vt2.feed("X")

    lines2 = vt2.get_plain_text().split("\n")
    assert "LiXe 2" in lines2[1] or lines2[1].strip().startswith("LiXe"), \
        f"Line 2 should have X at col 3, got: {repr(lines2[1])}"

    print("  Cursor movement: PASSED")


def main():
    print("\n" + "=" * 55)
    print("Round 5 Enhancement Verification Tests")
    print("=" * 55 + "\n")
    try:
        test_vterminal_basic()
        test_vterminal_clear_screen()
        test_vterminal_colors_and_styles()
        test_vterminal_carriage_return_overwrite()
        test_snapshot_text_no_control_codes()
        test_snapshot_json()
        test_html_script_injection_safety()
        test_compare_same_log_two_bookmarks()
        test_compare_two_different_logs()
        test_compare_quiet_mode_and_errors()
        test_html_copy_download_buttons()
        test_cli_help_no_crash()
        test_vterminal_cursor_movement()
        print("\n" + "=" * 55)
        print("ALL ROUND 5 TESTS PASSED!")
        print("=" * 55)
        return 0
    except AssertionError as e:
        print(f"\nFAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
