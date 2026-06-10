import os
import sys
import json
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ssh_recorder.storage import SessionLogger, SessionReader, SessionLogEntry
from ssh_recorder.cleaner import LogCleaner
from ssh_recorder.searcher import LogSearcher
from ssh_recorder.exporter import HTMLExporter
from ssh_recorder.player import PlaybackController


_test_tmpdir = None


def get_test_tmpdir():
    global _test_tmpdir
    if _test_tmpdir is None:
        _test_tmpdir = tempfile.mkdtemp(prefix="ssh_recorder_test_")
    return _test_tmpdir


def test_storage():
    print("=== Testing Storage Module ===")
    tmpdir = get_test_tmpdir()
    logger = SessionLogger(log_dir=tmpdir, rotate_daily=False)
    log_file = logger.start_session(host="test.example.com", user="testuser", port=22)
    assert os.path.exists(log_file), "Log file should be created"
    assert os.path.exists(log_file + ".meta.json"), "Meta file should be created"

    logger.write_output(b"Welcome to Ubuntu 22.04 LTS\n")
    time.sleep(0.05)
    logger.write_input(b"ls -la\n")
    time.sleep(0.05)
    logger.write_output(b"\x1b[32mtotal 48\x1b[0m\ndrwxr-xr-x  5 user user 4096 Jun 11 10:00 .\n")
    logger.add_bookmark("file_list", "Listed files in home directory")
    logger.end_session()

    reader = SessionReader(log_file)
    assert reader.metadata is not None, "Metadata should be loaded"
    assert reader.metadata.host == "test.example.com"
    assert reader.metadata.user == "testuser"
    assert len(reader.metadata.bookmarks) == 1

    entries = reader.get_all_entries()
    assert len(entries) == 3, f"Expected 3 entries, got {len(entries)}"
    assert entries[0].stream == "o"
    assert entries[1].stream == "i"
    assert entries[2].stream == "o"

    output_text = reader.get_output_text()
    assert "Welcome to Ubuntu" in output_text
    assert "total 48" in output_text

    logs = SessionReader.find_logs(tmpdir)
    assert len(logs) >= 1

    print("  Storage: PASSED")
    return log_file


def test_cleaner(log_file):
    print("=== Testing Cleaner Module ===")
    tmpdir = get_test_tmpdir()
    output_file = os.path.join(tmpdir, "cleaned.txt")
    LogCleaner.clean_log_file(log_file, output_file)
    assert os.path.exists(output_file), "Cleaned file should be created"

    with open(output_file, "r", encoding="utf-8") as f:
        content = f.read()

    assert "\x1b" not in content, "ANSI codes should be removed"
    assert "Welcome to Ubuntu" in content
    assert "total 48" in content
    assert "testuser@test.example.com" in content or "testuser" in content

    raw_text = "Hello\x1b[31mWorld\x1b[0m\x08\x08\x08PLAIN"
    cleaned = LogCleaner.clean_output(raw_text)
    assert "\x1b" not in cleaned
    assert "HelloPLAIN" in cleaned or "Hello" in cleaned

    print("  Cleaner: PASSED")


def test_searcher(log_file):
    print("=== Testing Searcher Module ===")
    results = LogSearcher.search_in_file(
        log_file,
        query="total",
        context_lines=1,
    )
    assert len(results) >= 1, "Should find at least one match for 'total'"
    assert results[0].match_text is not None

    results = LogSearcher.search_in_file(
        log_file,
        query="ubuntu",
        case_sensitive=False,
    )
    assert len(results) >= 1, "Should find 'ubuntu' case-insensitively"

    results = LogSearcher.search_in_file(
        log_file,
        query="nonexistent_pattern_xyz",
    )
    assert len(results) == 0, "Should not find nonexistent pattern"

    formatted = LogSearcher.format_results({"test.log": results}, colored=False)
    assert "Found 0 matches" in formatted

    print("  Searcher: PASSED")


def test_exporter(log_file):
    print("=== Testing Exporter Module ===")
    tmpdir = get_test_tmpdir()
    output_file = os.path.join(tmpdir, "session.html")
    HTMLExporter.export(log_file, output_file, title="Test Session")
    assert os.path.exists(output_file), "HTML file should be created"

    with open(output_file, "r", encoding="utf-8") as f:
        content = f.read()

    assert "<!DOCTYPE html>" in content
    assert "Test Session" in content
    assert "test.example.com" in content
    assert "testuser" in content
    assert "terminal" in content.lower()
    assert "javascript" in content.lower() or "script" in content.lower()

    print("  Exporter: PASSED")


def test_player(log_file):
    print("=== Testing Player Module ===")
    controller = PlaybackController(log_file, speed=2.0, show_input=False)
    assert len(controller.entries) == 3
    assert controller.get_speed() == 2.0

    controller.set_speed(0.5)
    assert controller.get_speed() == 0.5

    controller.set_speed(200.0)
    assert controller.get_speed() == 100.0

    bookmarks = controller.list_bookmarks()
    assert len(bookmarks) == 1
    assert bookmarks[0]["name"] == "file_list"
    assert bookmarks[0]["description"] == "Listed files in home directory"

    controller.toggle_pause()
    assert controller.is_paused is True
    controller.toggle_pause()
    assert controller.is_paused is False

    print("  Player: PASSED")


def test_log_entry_serialization():
    print("=== Testing Log Entry Serialization ===")
    entry = SessionLogEntry(
        timestamp=1234567890.123,
        delay=0.5,
        stream="o",
        data=b"test data with \xc3\xa9 special char",
    )
    line = entry.to_line()
    parsed = SessionLogEntry.from_line(line)
    assert abs(parsed.timestamp - entry.timestamp) < 0.001
    assert abs(parsed.delay - entry.delay) < 0.001
    assert parsed.stream == entry.stream
    assert parsed.data == entry.data
    print("  Serialization: PASSED")


def main():
    print("\n" + "=" * 50)
    print("SSH Recorder - Functional Tests")
    print("=" * 50 + "\n")

    try:
        log_file = test_storage()
        test_log_entry_serialization()
        test_cleaner(log_file)
        test_searcher(log_file)
        test_exporter(log_file)
        test_player(log_file)

        print("\n" + "=" * 50)
        print("ALL TESTS PASSED!")
        print("=" * 50)
        return 0
    except AssertionError as e:
        print(f"\nTEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1
    except Exception as e:
        print(f"\nUNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
