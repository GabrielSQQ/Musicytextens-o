"""Real, authorized local media -> yt-dlp -> FFmpeg -> published file.

The resolver is dependency injection into Runner, never exposed in Native Messaging.
All media is synthesized by this test; the production YouTube allowlist stays strict.
"""
from __future__ import annotations

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "native-app"))
from downloader import Runner, Tools


class QuietHTTP(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class RealMediaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tools = Tools()
        if not all(cls.tools.paths.get(k) for k in ("yt-dlp", "ffmpeg", "ffprobe")):
            raise unittest.SkipTest("yt-dlp, FFmpeg and FFprobe are required for real media tests")
        cls.temp = tempfile.TemporaryDirectory(prefix="omd-media-")
        cls.base = Path(cls.temp.name)
        cls.source = cls.base / "source"
        cls.source.mkdir()
        ffmpeg = cls.tools.paths["ffmpeg"]
        subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=1.2", "-c:a", "pcm_s16le", str(cls.source / "Tom autorizado.wav")], check=True, timeout=30)
        # Three actual HLS renditions catch both ignored quality caps and an
        # implementation which silently always chooses the lowest resolution.
        master = ["#EXTM3U"]
        for width, height in ((640, 360), (1280, 720), (1920, 1080)):
            filename = f"rendition-{height}.m3u8"
            subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c=0xff3158:s={width}x{height}:r=12:d=1.2", "-f", "lavfi", "-i", "sine=frequency=440:duration=1.2", "-c:v", "libx264", "-threads", "2", "-preset", "ultrafast", "-c:a", "aac", "-shortest", "-f", "hls", "-hls_time", "1", "-hls_list_size", "0", str(cls.source / filename)], check=True, timeout=30)
            master.extend([f'#EXT-X-STREAM-INF:BANDWIDTH={height * 2000},RESOLUTION={width}x{height},CODECS="avc1.42c028,mp4a.40.2"', filename])
        (cls.source / "master.m3u8").write_text("\n".join(master) + "\n", encoding="utf-8")
        for label, height in (("low", 360), ("high", 720)):
            width = 640 if height == 360 else 1280
            (cls.source / f"master-{label}.m3u8").write_text(f'#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH={height * 2000},RESOLUTION={width}x{height},CODECS="avc1.42c028,mp4a.40.2"\nrendition-{height}.m3u8\n', encoding="utf-8")
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHTTP, directory=str(cls.source)))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.origin = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        cls.temp.cleanup()

    def run_media(self, fmt, quality, source="Tom%20autorizado.wav"):
        folder = self.base / f"out-{fmt}-{quality}"
        folder.mkdir(exist_ok=True)
        updates = []
        runner = Runner(self.tools, updates.append, threading.Event(), source_resolver=lambda _: self.origin + "/" + source)
        job = {"url": "https://www.youtube.com/watch?v=abcdefghijk", "format": fmt, "quality": quality, "title": "Mídia sintética autorizada"}
        path = runner.download(job, folder)
        self.assertTrue(path.is_file())
        self.assertGreater(path.stat().st_size, 500)
        self.assertEqual(path.suffix, "." + fmt)
        probe = subprocess.run([self.tools.paths["ffprobe"], "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)], check=True, capture_output=True, text=True, timeout=30)
        data = json.loads(probe.stdout)
        self.assertTrue(any(s["codec_type"] == "audio" for s in data["streams"]))
        self.assertGreater(float(data["format"]["duration"]), 0.5)
        self.assertTrue(any(u.get("status") == "downloading" for u in updates))
        self.assertTrue(any(u.get("status") == "converting" for u in updates))
        if fmt == "mp4":
            actual = next(s["height"] for s in data["streams"] if s["codec_type"] == "video")
            self.assertEqual(next(u["actualHeight"] for u in updates if "actualHeight" in u), actual)
            self.assertIn(f"{actual}p", next(u["resultNote"] for u in updates if "resultNote" in u))
        self.last_updates = updates
        return path, data

    def test_mp3_all_bitrates_and_metadata(self):
        for bitrate in (128, 192, 320):
            with self.subTest(bitrate=bitrate):
                _, data = self.run_media("mp3", bitrate)
                audio = next(s for s in data["streams"] if s["codec_type"] == "audio")
                self.assertEqual(audio["codec_name"], "mp3")
                self.assertEqual(int(audio["bit_rate"]), bitrate * 1000)
                self.assertIn("title", data["format"].get("tags", {}))

    def test_m4a_and_opus(self):
        for fmt, codec in (("m4a", "aac"), ("opus", "opus")):
            with self.subTest(fmt=fmt):
                _, data = self.run_media(fmt, 192)
                self.assertEqual(next(s for s in data["streams"] if s["codec_type"] == "audio")["codec_name"], codec)

    def test_mp4_limits_and_playable_codecs(self):
        for height in (360, 720, 1080):
            with self.subTest(height=height):
                _, data = self.run_media("mp4", height, "master.m3u8")
                video = next(s for s in data["streams"] if s["codec_type"] == "video")
                self.assertEqual(video["codec_name"], "h264")
                self.assertEqual(video["pix_fmt"], "yuv420p")
                self.assertEqual(video["height"], height)
                self.assertEqual(next(s for s in data["streams"] if s["codec_type"] == "audio")["codec_name"], "aac")

    def test_mp4_missing_quality_reports_lower_available_resolution(self):
        _, data = self.run_media("mp4", 1080, "master-low.m3u8")
        self.assertEqual(next(s["height"] for s in data["streams"] if s["codec_type"] == "video"), 360)
        self.assertIn("1080p não estava disponível", next(u["resultNote"] for u in self.last_updates if "resultNote" in u))

    def test_mp4_only_higher_resolution_is_scaled_to_cap_and_reported(self):
        _, data = self.run_media("mp4", 360, "master-high.m3u8")
        self.assertEqual(next(s["height"] for s in data["streams"] if s["codec_type"] == "video"), 360)
        self.assertIn("resolução ajustada", next(u["resultNote"] for u in self.last_updates if "resultNote" in u))


if __name__ == "__main__":
    unittest.main()
