import os
import re
import json
from typing import List, Dict, Any, Optional
from datetime import datetime

from .storage import SessionReader, SessionLogEntry


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SSH Session Playback - {{ title }}</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #1a1a2e;
    color: #e0e0e0;
    padding: 20px;
    min-height: 100vh;
}
.container { max-width: 1200px; margin: 0 auto; }
h1 { font-size: 20px; margin-bottom: 15px; color: #8be9fd; }
.info {
    background: #16213e;
    padding: 12px 16px;
    border-radius: 6px;
    margin-bottom: 15px;
    font-size: 13px;
    display: flex;
    gap: 20px;
    flex-wrap: wrap;
}
.info span { color: #bd93f9; }
.info strong { color: #50fa7b; }
.controls {
    background: #16213e;
    padding: 12px 16px;
    border-radius: 6px;
    margin-bottom: 15px;
    display: flex;
    gap: 10px;
    align-items: center;
    flex-wrap: wrap;
}
button {
    background: #44475a;
    color: #f8f8f2;
    border: none;
    padding: 8px 16px;
    border-radius: 4px;
    cursor: pointer;
    font-size: 13px;
    transition: background 0.2s;
}
button:hover { background: #6272a4; }
button:disabled { background: #282a36; cursor: not-allowed; opacity: 0.5; }
.speed-group { display: flex; align-items: center; gap: 5px; }
.speed-btn { padding: 6px 10px; font-size: 12px; }
#speedVal { min-width: 45px; text-align: center; color: #ff79c6; }
.time-display {
    color: #f1fa8c;
    font-family: monospace;
    font-size: 14px;
    margin-left: auto;
}
.bookmarks {
    background: #16213e;
    padding: 10px 16px;
    border-radius: 6px;
    margin-bottom: 15px;
}
.bookmarks h3 { font-size: 13px; margin-bottom: 8px; color: #8be9fd; }
.bookmark-list { display: flex; gap: 8px; flex-wrap: wrap; }
.bookmark-tag {
    background: #44475a;
    padding: 4px 10px;
    border-radius: 12px;
    font-size: 12px;
    cursor: pointer;
    transition: background 0.2s;
}
.bookmark-tag:hover { background: #6272a4; }
.terminal-wrapper {
    background: #0d1117;
    border-radius: 8px;
    overflow: hidden;
    box-shadow: 0 4px 20px rgba(0,0,0,0.5);
}
.terminal-header {
    background: #161b22;
    padding: 8px 16px;
    display: flex;
    align-items: center;
    gap: 8px;
    border-bottom: 1px solid #30363d;
}
.terminal-dot {
    width: 12px;
    height: 12px;
    border-radius: 50%;
}
.dot-red { background: #ff5f56; }
.dot-yellow { background: #ffbd2e; }
.dot-green { background: #27c93f; }
.terminal-title {
    color: #8b949e;
    font-size: 12px;
    margin-left: 10px;
}
.terminal {
    background: #0d1117;
    padding: 16px;
    font-family: 'Courier New', 'Menlo', 'Monaco', monospace;
    font-size: 14px;
    line-height: 1.5;
    color: #c9d1d9;
    white-space: pre-wrap;
    word-break: break-all;
    overflow-y: auto;
    max-height: 70vh;
    min-height: 400px;
}
.terminal .fg-black { color: #484f58; }
.terminal .fg-red { color: #ff7b72; }
.terminal .fg-green { color: #3fb950; }
.terminal .fg-yellow { color: #d29922; }
.terminal .fg-blue { color: #58a6ff; }
.terminal .fg-magenta { color: #bc8cff; }
.terminal .fg-cyan { color: #39c5cf; }
.terminal .fg-white { color: #c9d1d9; }
.terminal .bg-black { background-color: #0d1117; }
.terminal .bg-red { background-color: #f85149; }
.terminal .bg-green { background-color: #3fb950; }
.terminal .bg-yellow { background-color: #d29922; }
.terminal .bg-blue { background-color: #1f6feb; }
.terminal .bg-magenta { background-color: #a371f7; }
.terminal .bg-cyan { background-color: #39c5cf; }
.terminal .bg-white { background-color: #c9d1d9; }
.terminal .bold { font-weight: bold; }
.terminal .underline { text-decoration: underline; }
.cursor {
    display: inline-block;
    width: 8px;
    height: 16px;
    background: #58a6ff;
    animation: blink 1s step-end infinite;
    vertical-align: text-bottom;
}
@keyframes blink {
    0%, 100% { opacity: 1; }
    50% { opacity: 0; }
}
.hidden { display: none; }
</style>
</head>
<body>
<div class="container">
    <h1>SSH 会话回放</h1>
    <div class="info">
        <span><strong>主机:</strong> {{ host }}</span>
        <span><strong>用户:</strong> {{ user }}</span>
        <span><strong>端口:</strong> {{ port }}</span>
        <span><strong>开始时间:</strong> {{ start_time }}</span>
        <span><strong>总时长:</strong> {{ duration }}</span>
    </div>
    <div class="controls">
        <button id="playBtn">▶ 播放</button>
        <button id="pauseBtn" class="hidden">⏸ 暂停</button>
        <button id="resetBtn">⟲ 重置</button>
        <div class="speed-group">
            <button class="speed-btn" onclick="changeSpeed(-0.5)">-</button>
            <span id="speedVal">1.0x</span>
            <button class="speed-btn" onclick="changeSpeed(0.5)">+</button>
        </div>
        <span class="time-display" id="timeDisplay">00:00 / 00:00</span>
    </div>
    {% if bookmarks %}
    <div class="bookmarks">
        <h3>📌 书签</h3>
        <div class="bookmark-list">
            {% for bm in bookmarks %}
            <span class="bookmark-tag" onclick="jumpToBookmark({{ loop.index0 }})" title="{{ bm.description }}">
                {{ bm.name }} ({{ bm.time_str }})
            </span>
            {% endfor %}
        </div>
    </div>
    {% endif %}
    <div class="terminal-wrapper">
        <div class="terminal-header">
            <span class="terminal-dot dot-red"></span>
            <span class="terminal-dot dot-yellow"></span>
            <span class="terminal-dot dot-green"></span>
            <span class="terminal-title">{{ user }}@{{ host }}</span>
        </div>
        <div class="terminal" id="terminal"></div>
    </div>
</div>
<script>
const events = {{ events_json }};
const bookmarks = {{ bookmarks_json }};
const totalDuration = {{ total_duration }};

let currentIdx = 0;
let isPlaying = false;
let speed = 1.0;
let timerId = null;
let currentElapsed = 0;

const terminal = document.getElementById('terminal');
const playBtn = document.getElementById('playBtn');
const pauseBtn = document.getElementById('pauseBtn');
const resetBtn = document.getElementById('resetBtn');
const speedVal = document.getElementById('speedVal');
const timeDisplay = document.getElementById('timeDisplay');

function formatTime(seconds) {
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return String(m).padStart(2, '0') + ':' + String(s).padStart(2, '0');
}

function updateTimeDisplay() {
    timeDisplay.textContent = formatTime(currentElapsed) + ' / ' + formatTime(totalDuration);
}

const ESC = '\x1b';
const sgrCodes = {
    '0': null, '1': 'bold', '4': 'underline',
    '30': 'fg-black', '31': 'fg-red', '32': 'fg-green', '33': 'fg-yellow',
    '34': 'fg-blue', '35': 'fg-magenta', '36': 'fg-cyan', '37': 'fg-white',
    '40': 'bg-black', '41': 'bg-red', '42': 'bg-green', '43': 'bg-yellow',
    '44': 'bg-blue', '45': 'bg-magenta', '46': 'bg-cyan', '47': 'bg-white',
    '90': 'fg-black', '91': 'fg-red', '92': 'fg-green', '93': 'fg-yellow',
    '94': 'fg-blue', '95': 'fg-magenta', '96': 'fg-cyan', '97': 'fg-white',
    '100': 'bg-black', '101': 'bg-red', '102': 'bg-green', '103': 'bg-yellow',
    '104': 'bg-blue', '105': 'bg-magenta', '106': 'bg-cyan', '107': 'bg-white',
};

function ansiToHtml(text) {
    let html = '';
    let openSpans = 0;

    text = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

    let i = 0;
    while (i < text.length) {
        if (text.charCodeAt(i) === 27 && text[i + 1] === '[') {
            let j = i + 2;
            while (j < text.length && !/[a-zA-Z]/.test(text[j])) j++;
            if (j < text.length) {
                const cmd = text[j];
                const params = text.substring(i + 2, j);
                if (cmd === 'm') {
                    const codes = params ? params.split(';') : ['0'];
                    for (const code of codes) {
                        if (code === '0' || code === '') {
                            while (openSpans > 0) {
                                html += '</span>';
                                openSpans--;
                            }
                        } else {
                            const cls = sgrCodes[code];
                            if (cls) {
                                html += '<span class="' + cls + '">';
                                openSpans++;
                            }
                        }
                    }
                } else if (cmd === 'H' || cmd === 'f' || cmd === 'A' || cmd === 'B' ||
                           cmd === 'C' || cmd === 'D' || cmd === 's' || cmd === 'u' ||
                           cmd === 'J' || cmd === 'K' || cmd === 'h' || cmd === 'l' ||
                           cmd === 'p' || cmd === 'P') {
                }
                i = j + 1;
                continue;
            }
        }
        if (text.charCodeAt(i) === 27) {
            let j = i + 1;
            while (j < text.length && text.charCodeAt(j) >= 0x40 && text.charCodeAt(j) <= 0x7e &&
                   text.charCodeAt(j) !== 0x5c && text.charCodeAt(j) !== 0x07) j++;
            if (j < text.length && (text[j] === '\x07' || text.substring(j - 1, j + 1) === ESC + '\\')) {
                i = (text[j] === '\x07') ? j + 1 : j + 2;
                continue;
            }
            i++;
            continue;
        }
        if (text[i] === '\n') {
            html += '\n';
        } else if (text[i] === '\r') {
        } else if (text[i] === '\t') {
            html += '    ';
        } else if (text[i] === '\b') {
            if (html.length > 0 && html[html.length - 1] !== '\n') {
                html = html.slice(0, -1);
            }
        } else if (text.charCodeAt(i) < 32 || text.charCodeAt(i) === 127) {
        } else {
            html += text[i];
        }
        i++;
    }
    while (openSpans > 0) {
        html += '</span>';
        openSpans--;
    }
    return html;
}

function appendEventToTerminal(event) {
    const text = event.data || '';
    terminal.innerHTML = ansiToHtml(terminal.textContent + text);
    terminal.scrollTop = terminal.scrollHeight;
}

function renderEventsTo(idx) {
    terminal.textContent = '';
    terminal.innerHTML = '';
    for (let i = 0; i < idx && i < events.length; i++) {
        terminal.textContent += (events[i].data || '');
    }
    terminal.innerHTML = ansiToHtml(terminal.textContent);
    terminal.scrollTop = terminal.scrollHeight;
}

function playNext() {
    if (!isPlaying || currentIdx >= events.length) {
        stop();
        return;
    }
    const event = events[currentIdx];
    appendEventToTerminal(event);
    currentElapsed += event.delay;
    updateTimeDisplay();
    currentIdx++;
    if (currentIdx < events.length) {
        const delay = events[currentIdx].delay * 1000 / speed;
        timerId = setTimeout(playNext, Math.max(1, delay));
    } else {
        stop();
    }
}

function play() {
    if (currentIdx >= events.length) reset();
    isPlaying = true;
    playBtn.classList.add('hidden');
    pauseBtn.classList.remove('hidden');
    if (currentIdx < events.length) {
        const delay = events[currentIdx].delay * 1000 / speed;
        timerId = setTimeout(playNext, Math.max(1, delay));
    }
}

function pause() {
    isPlaying = false;
    if (timerId) clearTimeout(timerId);
    playBtn.classList.remove('hidden');
    pauseBtn.classList.add('hidden');
}

function stop() {
    isPlaying = false;
    if (timerId) clearTimeout(timerId);
    playBtn.classList.remove('hidden');
    pauseBtn.classList.add('hidden');
}

function reset() {
    pause();
    currentIdx = 0;
    currentElapsed = 0;
    terminal.textContent = '';
    terminal.innerHTML = '';
    updateTimeDisplay();
}

function changeSpeed(delta) {
    speed = Math.max(0.1, Math.min(10, speed + delta));
    speedVal.textContent = speed.toFixed(1) + 'x';
}

function jumpTo(idx) {
    pause();
    idx = Math.max(0, Math.min(idx, events.length));
    let elapsed = 0;
    for (let i = 0; i < idx; i++) {
        elapsed += events[i].delay;
    }
    renderEventsTo(idx);
    currentIdx = idx;
    currentElapsed = elapsed;
    updateTimeDisplay();
}

function jumpToBookmark(bmIdx) {
    const bm = bookmarks[bmIdx];
    if (bm && bm.entry_index !== undefined) {
        jumpTo(bm.entry_index);
    }
}

playBtn.addEventListener('click', play);
pauseBtn.addEventListener('click', pause);
resetBtn.addEventListener('click', reset);

updateTimeDisplay();
</script>
</body>
</html>
"""


class HTMLExporter:
    @staticmethod
    def _format_time(seconds: float) -> str:
        m = int(seconds // 60)
        s = int(seconds % 60)
        return f"{m:02d}:{s:02d}"

    @staticmethod
    def export(
        log_file: str,
        output_file: str,
        title: Optional[str] = None,
    ) -> None:
        reader = SessionReader(log_file)
        entries = reader.get_all_entries()

        host = "unknown"
        user = "unknown"
        port = 22
        start_time_str = "unknown"
        total_duration = 0.0

        if reader.metadata:
            host = reader.metadata.host
            user = reader.metadata.user
            port = reader.metadata.port
            if reader.metadata.started_at:
                start_time_str = datetime.fromtimestamp(
                    reader.metadata.started_at
                ).strftime("%Y-%m-%d %H:%M:%S")

        events_data = []
        for entry in entries:
            total_duration += entry.delay
            try:
                data_str = entry.data.decode("utf-8", errors="replace")
            except Exception:
                data_str = ""
            events_data.append({
                "delay": entry.delay,
                "stream": entry.stream,
                "data": data_str,
            })

        duration_str = HTMLExporter._format_time(total_duration)

        bookmarks_data = []
        total_delay = 0.0
        entry_idx = 0
        for bm in reader.get_bookmarks():
            while entry_idx < len(entries) and entries[entry_idx].timestamp < bm["timestamp"]:
                total_delay += entries[entry_idx].delay
                entry_idx += 1
            bookmarks_data.append({
                "name": bm.get("name", ""),
                "description": bm.get("description", ""),
                "time_offset": total_delay,
                "time_str": HTMLExporter._format_time(total_delay),
                "entry_index": entry_idx,
            })

        events_json = json.dumps(events_data, ensure_ascii=False)
        bookmarks_json = json.dumps(bookmarks_data, ensure_ascii=False)

        from jinja2 import Template
        template = Template(HTML_TEMPLATE)
        html_content = template.render(
            title=title or os.path.basename(log_file),
            host=host,
            user=user,
            port=port,
            start_time=start_time_str,
            duration=duration_str,
            bookmarks=bookmarks_data,
            events_json=events_json,
            bookmarks_json=bookmarks_json,
            total_duration=total_duration,
        )

        os.makedirs(os.path.dirname(os.path.abspath(output_file)) or ".", exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(html_content)
