import re
from typing import List, Dict, Any, Optional


class Cell:
    __slots__ = ("ch", "fg", "bg", "bold", "underline")

    def __init__(self, ch: str = " ", fg: str = "37", bg: str = "40",
                 bold: bool = False, underline: bool = False):
        self.ch = ch
        self.fg = fg
        self.bg = bg
        self.bold = bold
        self.underline = underline

    def clone(self) -> "Cell":
        return Cell(self.ch, self.fg, self.bg, self.bold, self.underline)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ch": self.ch,
            "fg": self.fg,
            "bg": self.bg,
            "bold": self.bold,
            "underline": self.underline,
        }


class VirtualTerminal:
    """
    A minimal VT100 virtual terminal that tracks per-cell content and style.

    Supports:
    - Cursor movement (CSI A/B/C/D, H/f, G, d)
    - Clear screen / line (CSI J, K)
    - SGR attributes (colors, bold, underline, reset)
    - Carriage return, newline, backspace, tab
    - Insert/delete characters and lines (CSI @, P, L, M, X)
    - OSC sequences are ignored
    """

    def __init__(self, width: Optional[int] = None, height: Optional[int] = None):
        self.lines: List[List[Cell]] = [[]]
        self.cursor_row = 0
        self.cursor_col = 0
        self.fg = "37"
        self.bg = "40"
        self.bold = False
        self.underline = False
        self.width = width
        self.height = height

    def _mk_cell(self, ch: str = " ") -> Cell:
        return Cell(ch, self.fg, self.bg, self.bold, self.underline)

    def _ensure_row(self, row: int) -> None:
        while len(self.lines) <= row:
            self.lines.append([])

    def _pad_line(self, line: List[Cell], to_len: int) -> None:
        while len(line) < to_len:
            line.append(self._mk_cell(" "))

    def _set_char(self, row: int, col: int, ch: str) -> None:
        self._ensure_row(row)
        line = self.lines[row]
        if col >= len(line):
            self._pad_line(line, col + 1)
        line[col] = self._mk_cell(ch)

    def _clear_line(self, row: int, mode: int = 0) -> None:
        self._ensure_row(row)
        line = self.lines[row]
        if mode == 0:
            for c in range(self.cursor_col, len(line)):
                line[c] = self._mk_cell(" ")
        elif mode == 1:
            for c in range(0, min(self.cursor_col + 1, len(line))):
                line[c] = self._mk_cell(" ")
        elif mode == 2:
            self.lines[row] = []

    def _clear_screen(self, mode: int = 0) -> None:
        if mode == 0:
            for r in range(self.cursor_row, len(self.lines)):
                if r == self.cursor_row:
                    self._clear_line(r, 0)
                else:
                    self.lines[r] = []
        elif mode == 1:
            for r in range(0, self.cursor_row + 1):
                if r == self.cursor_row:
                    self._clear_line(r, 1)
                else:
                    self.lines[r] = []
        elif mode == 2:
            self.lines = [[]]
            self.cursor_row = 0
            self.cursor_col = 0

    def _handle_sgr(self, parts: List[str]) -> None:
        for code in parts:
            code = code or "0"
            if code == "0":
                self.fg = "37"
                self.bg = "40"
                self.bold = False
                self.underline = False
            elif code == "1":
                self.bold = True
            elif code == "4":
                self.underline = True
            elif code == "22":
                self.bold = False
            elif code == "24":
                self.underline = False
            elif code.isdigit():
                n = int(code)
                if 30 <= n <= 37:
                    self.fg = code
                elif 40 <= n <= 47:
                    self.bg = code
                elif 90 <= n <= 97:
                    self.fg = code
                elif 100 <= n <= 107:
                    self.bg = code
                elif n == 39:
                    self.fg = "37"
                elif n == 49:
                    self.bg = "40"

    def feed(self, data: str) -> None:
        i = 0
        n = len(data)
        while i < n:
            if ord(data[i]) == 27 and i + 1 < n and data[i + 1] == "[":
                j = i + 2
                while j < n and not re.match(r"[a-zA-Z]", data[j]):
                    j += 1
                if j < n:
                    cmd = data[j]
                    params_str = data[i + 2:j]
                    parts = params_str.split(";") if params_str else []
                    p0 = int(parts[0]) if parts and parts[0] else 0
                    p1 = int(parts[1]) if len(parts) > 1 and parts[1] else 0
                    if cmd in ("H", "f"):
                        self.cursor_row = max(0, (p0 or 1) - 1)
                        self.cursor_col = max(0, (p1 or 1) - 1)
                    elif cmd == "A":
                        self.cursor_row = max(0, self.cursor_row - (p0 or 1))
                    elif cmd == "B":
                        self.cursor_row += (p0 or 1)
                    elif cmd == "C":
                        self.cursor_col += (p0 or 1)
                    elif cmd == "D":
                        self.cursor_col = max(0, self.cursor_col - (p0 or 1))
                    elif cmd == "J":
                        self._clear_screen(p0 or 0)
                    elif cmd == "K":
                        self._clear_line(self.cursor_row, p0 or 0)
                    elif cmd == "m":
                        self._handle_sgr(parts)
                    elif cmd == "G":
                        self.cursor_col = max(0, (p0 or 1) - 1)
                    elif cmd == "d":
                        self.cursor_row = max(0, (p0 or 1) - 1)
                    elif cmd == "P":
                        cnt = p0 or 1
                        self._ensure_row(self.cursor_row)
                        ln = self.lines[self.cursor_row]
                        if self.cursor_col < len(ln):
                            end = min(self.cursor_col + cnt, len(ln))
                            del ln[self.cursor_col:end]
                    elif cmd == "@":
                        cnt = p0 or 1
                        self._ensure_row(self.cursor_row)
                        self._pad_line(self.lines[self.cursor_row], self.cursor_col)
                        for _ in range(cnt):
                            self.lines[self.cursor_row].insert(self.cursor_col, self._mk_cell(" "))
                    elif cmd == "M":
                        cnt = p0 or 1
                        self._ensure_row(self.cursor_row)
                        del self.lines[self.cursor_row:self.cursor_row + cnt]
                        if not self.lines:
                            self.lines = [[]]
                    elif cmd == "L":
                        cnt = p0 or 1
                        self._ensure_row(self.cursor_row)
                        for _ in range(cnt):
                            self.lines.insert(self.cursor_row, [])
                    elif cmd == "X":
                        cnt = p0 or 1
                        self._ensure_row(self.cursor_row)
                        self._pad_line(self.lines[self.cursor_row], self.cursor_col + cnt)
                        for c in range(self.cursor_col, self.cursor_col + cnt):
                            if c < len(self.lines[self.cursor_row]):
                                self.lines[self.cursor_row][c] = self._mk_cell(" ")
                    i = j + 1
                    continue
            if ord(data[i]) == 27 and i + 1 < n and data[i + 1] == "]":
                j = i + 2
                while j < n and ord(data[j]) != 7 and not (ord(data[j]) == 27 and j + 1 < n and data[j + 1] == "\\"):
                    j += 1
                if j < n:
                    i = (j + 1) if ord(data[j]) == 7 else (j + 2)
                    continue
            if ord(data[i]) == 27:
                i += 1
                if i < n and 0x40 <= ord(data[i]) <= 0x5f:
                    i += 1
                continue

            ch = data[i]
            if ch == "\n":
                self.cursor_row += 1
                self.cursor_col = 0
                self._ensure_row(self.cursor_row)
            elif ch == "\r":
                self.cursor_col = 0
            elif ch == "\t":
                sp = 8 - (self.cursor_col % 8)
                for _ in range(sp):
                    self._set_char(self.cursor_row, self.cursor_col, " ")
                    self.cursor_col += 1
            elif ch == "\b":
                self.cursor_col = max(0, self.cursor_col - 1)
            elif ord(ch) >= 32 and ord(ch) != 127:
                self._set_char(self.cursor_row, self.cursor_col, ch)
                self.cursor_col += 1
            i += 1

    def feed_bytes(self, data: bytes) -> None:
        self.feed(data.decode("utf-8", errors="replace"))

    def get_plain_text(self) -> str:
        lines = []
        for row in self.lines:
            if not row:
                lines.append("")
                continue
            chars = [cell.ch for cell in row]
            line = "".join(chars).rstrip()
            lines.append(line)
        return "\n".join(lines)

    def get_lines(self) -> List[List[Cell]]:
        return [line[:] for line in self.lines]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "lines": [
                [cell.to_dict() for cell in row]
                for row in self.lines
            ],
            "cursor_row": self.cursor_row,
            "cursor_col": self.cursor_col,
            "fg": self.fg,
            "bg": self.bg,
            "bold": self.bold,
            "underline": self.underline,
        }

    @staticmethod
    def replay_entries(entries, stop_index: Optional[int] = None,
                       show_input: bool = False) -> "VirtualTerminal":
        vt = VirtualTerminal()
        for i, entry in enumerate(entries):
            if stop_index is not None and i >= stop_index:
                break
            if show_input or entry.stream == "o":
                vt.feed_bytes(entry.data)
        return vt
