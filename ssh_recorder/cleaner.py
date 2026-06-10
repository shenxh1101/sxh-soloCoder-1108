import re
import os
from typing import List


class LogCleaner:
    ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")
    CSI_RE = re.compile(r"\x1b\[[?0-9;]*[hlHfABCDsuJKmnpP]")
    OSC_RE = re.compile(r"\x1b\].*?\x07|\x1b\].*?\x1b\\")
    CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")

    @staticmethod
    def _apply_backspaces(text: str) -> str:
        result: List[str] = []
        i = 0
        while i < len(text):
            ch = text[i]
            if ch == "\x7f" or ch == "\x08":
                if result:
                    result.pop()
            elif ch == "\x15":
                while result and result[-1] != "\n":
                    result.pop()
            elif ch == "\x17":
                count = 0
                while result and result[-1] != "\n" and result[-1] != " ":
                    result.pop()
                    count += 1
                while result and result[-1] == " ":
                    result.pop()
            else:
                result.append(ch)
            i += 1
        return "".join(result)

    @staticmethod
    def _strip_ansi(text: str) -> str:
        text = LogCleaner.OSC_RE.sub("", text)
        text = LogCleaner.CSI_RE.sub("", text)
        text = LogCleaner.ANSI_ESCAPE_RE.sub("", text)
        text = text.replace("\x1b", "")
        return text

    @staticmethod
    def _strip_control_chars(text: str, keep_newlines: bool = True) -> str:
        if keep_newlines:
            result = []
            for ch in text:
                if ch == "\n" or ch == "\r" or ch == "\t":
                    result.append(ch)
                elif ord(ch) < 32 or ord(ch) == 127:
                    continue
                else:
                    result.append(ch)
            return "".join(result)
        return LogCleaner.CONTROL_CHARS_RE.sub("", text)

    @staticmethod
    def _normalize_line_endings(text: str) -> str:
        text = text.replace("\r\n", "\n")
        text = text.replace("\r", "\n")
        lines = text.split("\n")
        cleaned = []
        for line in lines:
            if "\x1b" in line:
                line = LogCleaner._strip_ansi(line)
            cleaned.append(line)
        return "\n".join(cleaned)

    @staticmethod
    def clean_output(
        text: str,
        remove_ansi: bool = True,
        apply_backspace: bool = True,
        remove_control: bool = True,
        keep_timestamps: bool = False,
    ) -> str:
        if apply_backspace:
            text = LogCleaner._apply_backspaces(text)
        if remove_ansi:
            text = LogCleaner._strip_ansi(text)
        if remove_control:
            text = LogCleaner._strip_control_chars(text, keep_newlines=True)
        text = LogCleaner._normalize_line_endings(text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        lines = text.split("\n")
        lines = [line.rstrip() for line in lines]
        text = "\n".join(lines)
        text = text.strip() + "\n"
        return text

    @staticmethod
    def clean_log_file(
        input_file: str,
        output_file: str,
        include_input: bool = False,
        **kwargs,
    ) -> None:
        from .storage import SessionReader

        reader = SessionReader(input_file)
        parts = []
        for entry in reader.iter_entries():
            if include_input or entry.stream == "o":
                parts.append(entry.data.decode("utf-8", errors="replace"))
        raw_text = "".join(parts)
        cleaned = LogCleaner.clean_output(raw_text, **kwargs)
        os.makedirs(os.path.dirname(os.path.abspath(output_file)) or ".", exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as f:
            if reader.metadata:
                f.write(f"# SSH Session Cleaned Log\n")
                f.write(f"# Session: {reader.metadata.user}@{reader.metadata.host}\n")
                f.write(f"# Started: {reader.metadata.started_at}\n")
                if reader.metadata.ended_at:
                    f.write(f"# Ended: {reader.metadata.ended_at}\n")
                f.write("\n")
            f.write(cleaned)
