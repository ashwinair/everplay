#!/usr/bin/env python3
"""
Wavely local server — replaces Piped API with yt-dlp.
Run: python3 server.py
Then open: http://localhost:8080
"""
import json
import subprocess
import sys
import os
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote

PORT = 8080
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def run_ytdlp(args):
    result = subprocess.run(
        ["yt-dlp"] + args,
        capture_output=True, text=True, timeout=30
    )
    return result


def get_streams(video_id):
    """Return stream info in Piped-compatible format."""
    result = run_ytdlp([
        "--dump-json",
        "--no-playlist",
        "-f", "bestaudio[ext=webm]/bestaudio[ext=m4a]/bestaudio",
        f"https://www.youtube.com/watch?v={video_id}",
    ])
    if result.returncode != 0:
        raise RuntimeError(result.stderr[:300])

    info = json.loads(result.stdout)

    # Build audio streams list (Piped format)
    audio_streams = []
    for fmt in info.get("formats", []):
        if fmt.get("vcodec") == "none" and fmt.get("url"):
            audio_streams.append({
                "url": fmt["url"],
                "mimeType": fmt.get("ext", "webm"),
                "quality": str(fmt.get("abr") or fmt.get("tbr") or 0),
                "codec": fmt.get("acodec", ""),
            })

    return {
        "title": info.get("title", "Unknown"),
        "uploader": info.get("uploader", info.get("channel", "")),
        "thumbnailUrl": info.get("thumbnail", f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg"),
        "audioStreams": audio_streams,
    }


def do_search(query):
    """Search YouTube, return Piped-compatible items list."""
    result = run_ytdlp([
        "--dump-json",
        "--no-playlist",
        "--flat-playlist",
        f"ytsearch15:{query}",
    ])
    if result.returncode != 0:
        return []

    items = []
    for line in result.stdout.strip().splitlines():
        try:
            entry = json.loads(line)
            vid = entry.get("id") or entry.get("url", "").split("?v=")[-1]
            if not vid:
                continue
            items.append({
                "type": "stream",
                "url": f"/watch?v={vid}",
                "title": entry.get("title", "Unknown"),
                "uploaderName": entry.get("uploader") or entry.get("channel") or "",
                "thumbnail": entry.get("thumbnail") or f"https://i.ytimg.com/vi/{vid}/default.jpg",
                "duration": entry.get("duration") or 0,
            })
        except Exception:
            continue
    return items


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BASE_DIR, **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        # ── API: streams ──────────────────────────────────────────────
        if path.startswith("/streams/"):
            video_id = path[len("/streams/"):].strip("/")
            self.send_cors()
            try:
                data = get_streams(video_id)
                self.send_json(data)
            except Exception as e:
                self.send_json({"error": str(e)}, status=500)
            return

        # ── API: search ───────────────────────────────────────────────
        if path == "/search":
            query = unquote(qs.get("q", [""])[0])
            self.send_cors()
            if not query:
                self.send_json({"items": []})
                return
            try:
                items = do_search(query)
                self.send_json({"items": items})
            except Exception as e:
                self.send_json({"error": str(e)}, status=500)
            return

        # ── Static files ──────────────────────────────────────────────
        super().do_GET()

    def send_cors(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")

    def send_json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        print(f"  {self.address_string()} {fmt % args}")


if __name__ == "__main__":
    # Check yt-dlp
    check = subprocess.run(["yt-dlp", "--version"], capture_output=True, text=True)
    if check.returncode != 0:
        print("ERROR: yt-dlp not found.")
        print("Install it with:  pip3 install yt-dlp")
        print("  or:             brew install yt-dlp")
        sys.exit(1)

    print(f"yt-dlp {check.stdout.strip()} ready")
    print(f"Wavely running at http://localhost:{PORT}")
    print("Press Ctrl+C to stop\n")
    HTTPServer(("", PORT), Handler).serve_forever()
