import os
import re
from typing import List, Dict, Any, Optional
from datetime import datetime

from .storage import SessionReader


class SearchResult:
    def __init__(
        self,
        log_file: str,
        line_number: int,
        match_text: str,
        context_before: str = "",
        context_after: str = "",
        timestamp: Optional[float] = None,
        entry_index: int = 0,
    ):
        self.log_file = log_file
        self.line_number = line_number
        self.match_text = match_text
        self.context_before = context_before
        self.context_after = context_after
        self.timestamp = timestamp
        self.entry_index = entry_index

    def format(self, with_context: bool = True, colored: bool = True) -> str:
        lines = []
        file_label = self.log_file
        if self.timestamp:
            ts = datetime.fromtimestamp(self.timestamp).strftime("%Y-%m-%d %H:%M:%S")
            file_label += f" [{ts}]"

        if colored:
            lines.append(f"\x1b[1m\x1b[35m{file_label}:{self.line_number}\x1b[0m")
            if with_context and self.context_before:
                lines.append(f"\x1b[2m{self.context_before}\x1b[0m")
            highlighted = re.sub(
                r"\x1b\[[0-9;]*m", "", self.match_text
            )
            lines.append(f"  \x1b[31m\x1b[1m{highlighted}\x1b[0m")
            if with_context and self.context_after:
                lines.append(f"\x1b[2m{self.context_after}\x1b[0m")
        else:
            lines.append(f"{file_label}:{self.line_number}")
            if with_context and self.context_before:
                lines.append(self.context_before)
            lines.append(f"  {self.match_text}")
            if with_context and self.context_after:
                lines.append(self.context_after)
        return "\n".join(lines)


class LogSearcher:
    @staticmethod
    def _strip_ansi(text: str) -> str:
        return re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", text)

    @staticmethod
    def _get_visible_lines(text: str) -> List[str]:
        text = LogSearcher._strip_ansi(text)
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        return [line for line in text.split("\n")]

    @staticmethod
    def search_in_file(
        log_file: str,
        query: str,
        case_sensitive: bool = False,
        regex: bool = False,
        context_lines: int = 2,
        max_results: int = 100,
    ) -> List[SearchResult]:
        results: List[SearchResult] = []
        reader = SessionReader(log_file)

        flags = 0 if case_sensitive else re.IGNORECASE
        if regex:
            try:
                pattern = re.compile(query, flags)
            except re.error:
                pattern = re.compile(re.escape(query), flags)
        else:
            pattern = re.compile(re.escape(query), flags)

        output_text = reader.get_output_text()
        visible_lines = LogSearcher._get_visible_lines(output_text)

        entries = reader.get_all_entries()
        line_entry_map = LogSearcher._build_line_entry_map(entries, visible_lines)

        for line_num, line in enumerate(visible_lines, 1):
            if len(results) >= max_results:
                break
            match = pattern.search(line)
            if match:
                start = max(0, line_num - 1 - context_lines)
                end = min(len(visible_lines), line_num + context_lines)

                ctx_before = "\n".join(visible_lines[start:line_num - 1]) if start < line_num - 1 else ""
                ctx_after = "\n".join(visible_lines[line_num:end]) if line_num < end else ""

                entry_idx = line_entry_map.get(line_num, 0)
                timestamp = entries[entry_idx].timestamp if entry_idx < len(entries) else None

                results.append(SearchResult(
                    log_file=log_file,
                    line_number=line_num,
                    match_text=line,
                    context_before=ctx_before,
                    context_after=ctx_after,
                    timestamp=timestamp,
                    entry_index=entry_idx,
                ))

        return results

    @staticmethod
    def _build_line_entry_map(entries, visible_lines):
        mapping = {}
        line_count = 0
        for i, entry in enumerate(entries):
            if entry.stream != "o":
                continue
            text = LogSearcher._strip_ansi(entry.data.decode("utf-8", errors="replace"))
            text = text.replace("\r\n", "\n").replace("\r", "\n")
            new_lines = text.count("\n")
            for _ in range(new_lines):
                line_count += 1
                mapping[line_count] = i
            if not text.endswith("\n") and line_count < len(visible_lines):
                mapping[line_count + 1] = i
        return mapping

    @staticmethod
    def search(
        path: str,
        query: str,
        recursive: bool = True,
        **kwargs,
    ) -> Dict[str, List[SearchResult]]:
        all_results: Dict[str, List[SearchResult]] = {}

        if os.path.isfile(path):
            log_files = [path]
        elif os.path.isdir(path):
            log_files = SessionReader.find_logs(path)
            if not recursive:
                log_files = [f for f in log_files if os.path.dirname(f) == os.path.abspath(path)]
        else:
            return all_results

        for log_file in log_files:
            results = LogSearcher.search_in_file(log_file, query, **kwargs)
            if results:
                all_results[log_file] = results

        return all_results

    @staticmethod
    def format_results(
        results: Dict[str, List[SearchResult]],
        with_context: bool = True,
        colored: bool = True,
    ) -> str:
        output_parts = []
        total = sum(len(r) for r in results.values())
        output_parts.append(f"Found {total} matches in {len(results)} file(s)")
        output_parts.append("")

        for log_file, matches in results.items():
            output_parts.append(f"=== {log_file} ({len(matches)} matches) ===")
            for match in matches:
                output_parts.append(match.format(with_context=with_context, colored=colored))
                output_parts.append("")

        return "\n".join(output_parts)
