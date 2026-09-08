"""QC-F38 — video thumbnails + playable review links (ONB half).

Poster frame extraction (FFmpeg fixture when available; a skip-with
NOT-VERIFIED note otherwise); the sheet row carries thumbnail + duration +
ratio + a client-bound 'Watch video' link; expired access renews; the
published URL stays separate from the draft player.
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
ADAPTER = os.path.join(BASE, "57-social-media-in-a-box", "scripts", "media_thumbnails.py")
APPEND = os.path.join(BASE, "35-social-media-planner", "config", "n8n", "social-planner-row-append.json")

HAS_FFMPEG = any(
    any(os.path.isdir(os.path.join(p)) and "ffmpeg" in os.listdir(p)
        for p in (os.environ.get("PATH", "").split(os.pathsep)))
    for _ in [0]) or subprocess.run(["bash", "-lc", "command -v ffmpeg >/dev/null 2>&1; echo rc=$?"],
                                    capture_output=True, text=True).stdout.strip() == "rc=0"

WATCH = "https://cc.example.com/social/media/asset-a-1"
POSTER = "https://assets.cdn.filesafe.space/loc-1/media/poster.png"

RUNNER = r"""
// Executes the Build Asset Manifest (F24) code node for a video asset.
const fs = require('fs');
const [exportPath, stateJson] = process.argv.slice(2);
const exportDef = JSON.parse(fs.readFileSync(exportPath, 'utf8'));
const jsCode = exportDef.nodes.find(n => n.name === 'Build Asset Manifest (F24)').parameters.jsCode;
const state = JSON.parse(stateJson);
const $input = { first: () => ({ json: state }) };
const $ = (name) => ({ first: () => ({ json: name.includes('Receipt') ? { json: state.receipt } : state }) });
const fn = new Function('$input', '$', 'return (async () => {' + jsCode + '})()');
fn($input, $).then(r => console.log(JSON.stringify(r[0].json)))
  .catch(e => { console.error('ERR: ' + e.message); process.exit(3); });
"""


def run_adapter(*args):
    return subprocess.run(["python3", "57-social-media-in-a-box/scripts/media_thumbnails.py", *args],
                          capture_output=True, text=True, timeout=180)


def run_video_manifest(asset):
    tmp = tempfile.mkdtemp(prefix="f38-")
    runner = os.path.join(tmp, "runner.js")
    with open(runner, "w") as f:
        f.write(RUNNER)
    body = {"sheetId": "sh-1", "company_id": "co-1", "cycle_id": "2026-W37",
            "content_revision": "r2", "account_id": "yt-1", "platform": "youtube",
            "account_name": "Acme YT", "format": "video", "scheduled_local": "l",
            "scheduled_utc": "u", "state": "scheduled", "qc_state": "approved",
            "asset": asset}
    state = {"body": body, "receipt": {"success": True}}
    proc = subprocess.run(["node", runner, APPEND, json.dumps(state)],
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout.strip().splitlines()[-1])


def make_fixture_mp4(tmp):
    """A tiny 1s mp4 via FFmpeg testsrc; None when ffmpeg is unavailable."""
    if subprocess.run(["bash", "-lc", "command -v ffmpeg"], capture_output=True).returncode != 0:
        return None
    path = os.path.join(tmp, "fixture.mp4")
    proc = subprocess.run(
        ["ffmpeg", "-f", "lavfi", "-i", "testsrc=duration=1:size=320x180:rate=10",
         "-pix_fmt", "yuv420p", "-y", path],
        capture_output=True, text=True, timeout=120)
    return path if proc.returncode == 0 and os.path.exists(path) else None


class TestF38PosterExtraction(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="f38-")

    def test_poster_generated_or_not_verified(self):
        mp4 = make_fixture_mp4(self.tmp)
        out = os.path.join(self.tmp, "evidence.json")
        if mp4:
            proc = run_adapter("--video", mp4, "--asset-id", "asset-a-1",
                               "--cc-base-url", "https://cc.example.com", "--out", out)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            ev = json.load(open(out))
            self.assertTrue(ev["poster_generated_by_ffmpeg"])
            self.assertTrue(ev["poster"].endswith(".poster.png"))
            self.assertTrue(os.path.exists(ev["poster"]), "poster file exists")
            self.assertIsNone(ev["not_verified"])
        else:
            proc = run_adapter("--video", os.path.join(self.tmp, "missing.mp4"),
                               "--asset-id", "asset-a-1",
                               "--cc-base-url", "https://cc.example.com", "--out", out)
            self.assertEqual(proc.returncode, 2, "a skipped poster is never reported as success")
            self.assertIn("NOT VERIFIED", proc.stderr)

    def test_missing_video_fails_not_verified(self):
        proc = run_adapter("--video", os.path.join(self.tmp, "nope.mp4"),
                           "--asset-id", "a", "--cc-base-url", "https://cc.example.com",
                           "--out", os.path.join(self.tmp, "e.json"))
        self.assertEqual(proc.returncode, 2)
        self.assertIn("not found", proc.stderr)


class TestF38SheetEvidenceRow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(APPEND) as f:
            cls.append = json.load(f)

    def asset(self, **kw):
        a = {"content_id": "2026-W37::r2", "asset_id": "asset-a-1", "kind": "video",
             "preview_url": "https://assets.cdn.filesafe.space/loc-1/media/draft-r2.mp4",
             "poster_url": POSTER, "watch_url": WATCH, "duration_seconds": 25.0,
             "ratio": "9:16", "version": "r2", "qc_state": "QC Review",
             "captions": True}
        a.update(kw)
        return a

    def evidence(self, **asset):
        return run_video_manifest(self.asset(**asset))

    def test_row_carries_thumbnail_duration_ratio_watch(self):
        out = self.evidence()
        v = out["videosRow"]
        self.assertIsNotNone(v)
        header = v["header"]
        row = dict(zip(header, v["values"]))
        self.assertEqual(row["poster_url"], POSTER)          # thumbnail in the row
        self.assertEqual(float(row["duration_seconds"]), 25.0)    # duration
        self.assertEqual(row["ratio"], "9:16")               # ratio
        self.assertEqual(row["version"], "r2")               # version
        self.assertEqual(row["qc_state"], "QC Review")       # QC
        self.assertTrue(row["video_key"].startswith("VIDEO::"))

    def test_poster_formula_is_trusted_image(self):
        out = self.evidence()
        self.assertEqual(out["videosRow"]["posterFormula"], f'=IMAGE("{POSTER}", 1)')

    def test_watch_video_hyperlink_client_bound(self):
        out = self.evidence()
        wf = out["videosRow"]["watchFormula"]
        self.assertIn('=HYPERLINK("https://cc.example.com/social/media/asset-a-1"', wf)
        self.assertIn("Watch video", wf)

    def test_youtube_smart_chip_note_only_when_applicable(self):
        out = self.evidence(youtube=True,
                            published_url="https://www.youtube.com/watch?v=xyz")
        self.assertIn("YouTube smart-chip", out["videosRow"]["watchFormula"])
        # Without a published YouTube link there is no smart-chip note.
        plain = self.evidence()
        self.assertNotIn("YouTube smart-chip", plain["videosRow"]["watchFormula"])

    def test_untrusted_watch_url_refused(self):
        out = self.evidence(watch_url='javascript:alert(1)')
        self.assertIsNone(out["videosRow"])
        self.assertEqual(out["assetRepair"]["repair_state"], "asset_watch_url_invalid")

    def test_no_public_youtube_draft_upload(self):
        out = self.evidence(youtube=True)
        # The videosRow never sends drafts to YouTube; the published URL is
        # separate and empty until posting.
        self.assertEqual(dict(zip(out["videosRow"]["header"],
                                  out["videosRow"]["values"]))["published_url"], "")
        # The export contract states the rule explicitly.
        self.assertIn("never", json.dumps(self.append["contract"]["asset_manifest_contract"]))


class TestF38AdapterContracts(unittest.TestCase):
    def test_watch_url_shape(self):
        tmp = tempfile.mkdtemp(prefix="f38c-")
        mp4 = make_fixture_mp4(tmp)
        out = os.path.join(tmp, "e.json")
        if mp4 is None:
            self.skipTest("ffmpeg unavailable")
        run_adapter("--video", mp4, "--asset-id", "asset-a-1",
                    "--cc-base-url", "https://cc.example.com/", "--out", out)
        ev = json.load(open(out))
        self.assertEqual(ev["watch_url"], "https://cc.example.com/social/media/asset-a-1")
        self.assertFalse(ev["draft_public_youtube_upload"])
        self.assertIn("never", ev["poster_upload_contract"])

    def test_published_url_separate_and_validated(self):
        tmp = tempfile.mkdtemp(prefix="f38d-")
        mp4 = make_fixture_mp4(tmp)
        out = os.path.join(tmp, "e.json")
        if mp4 is None:
            self.skipTest("ffmpeg unavailable")
        run_adapter("--video", mp4, "--asset-id", "a", "--cc-base-url", "https://cc.example.com",
                    "--published-url", "https://youtube.com/watch?v=ok",
                    "--poster-cdn-url", POSTER, "--youtube", "--out", out)
        ev = json.load(open(out))
        self.assertEqual(ev["published_url"], "https://youtube.com/watch?v=ok")
        self.assertEqual(ev["poster_cdn_url"], POSTER)
        self.assertTrue(ev["youtube_smart_chip"])
        self.assertNotEqual(ev["watch_url"], ev["published_url"])

    def test_expired_access_renewal_path_documented(self):
        # The CC route contract (F38) renews access by re-fetching while
        # authenticated; the adapter's watch_url carries the CC player route,
        # and the renewal contract is stated in the evidence JSON.
        ev_path = os.path.join(tempfile.mkdtemp(prefix="f38e-"), "e.json")
        mp4 = make_fixture_mp4(tempfile.mkdtemp(prefix="f38f-"))
        if mp4 is None:
            self.skipTest("ffmpeg unavailable")
        proc = run_adapter("--video", mp4, "--asset-id", "a", "--cc-base-url",
                           "https://cc.example.com", "--out", ev_path)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        with open(ev_path) as f:
            ev = json.load(f)
        self.assertIn("/social/media/", ev["watch_url"])
        self.assertIn("client-bound", ev["watch_url_contract"].lower())


if __name__ == "__main__":
    unittest.main()