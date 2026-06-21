"""
VideoMate Crew 3.0 — Android Edition
- All formats/qualities (video+audio, video-only, audio-only)
- Watermark burned via bundled ffmpeg-android
- Multi-file queue download
- Progress per item
"""

import os, threading, subprocess, shutil
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.spinner import Spinner
from kivy.uix.progressbar import ProgressBar
from kivy.uix.switch import Switch
from kivy.uix.popup import Popup
from kivy.clock import Clock
from kivy.utils import get_color_from_hex
from kivy.metrics import dp

# ── Palette ──────────────────────────────────────────────────────────────────
BG      = get_color_from_hex("#0D0D0D")
SURF    = get_color_from_hex("#1A1A2E")
CARD    = get_color_from_hex("#16213E")
ACCENT  = get_color_from_hex("#BB86FC")
TEAL    = get_color_from_hex("#03DAC6")
TEXT    = get_color_from_hex("#E1E1E1")
DIM     = get_color_from_hex("#777788")
ERR     = get_color_from_hex("#CF6679")
WARN    = get_color_from_hex("#FFB300")
OK      = get_color_from_hex("#03DAC6")

# ── Paths ─────────────────────────────────────────────────────────────────────
def _get_paths():
    try:
        from android.storage import primary_external_storage_path
        ext = primary_external_storage_path()
        dl_dir = os.path.join(ext, "Download", "VideoMate")
        tmp_dir = os.path.join(ext, ".videomate_tmp")
    except Exception:
        home = os.path.expanduser("~")
        dl_dir  = os.path.join(home, "Downloads", "VideoMate")
        tmp_dir = os.path.join(home, ".videomate_tmp")
    os.makedirs(dl_dir,  exist_ok=True)
    os.makedirs(tmp_dir, exist_ok=True)
    return dl_dir, tmp_dir

DL_DIR, TMP_DIR = _get_paths()

# ── ffmpeg: bundled Android binary or system fallback ─────────────────────────
def _find_ffmpeg():
    """Locate ffmpeg: bundled arm64 binary shipped with the APK, else PATH."""
    # Buildozer copies assets/ffmpeg -> app private dir
    try:
        from android.runnable import run_on_ui_thread        # noqa
        import android                                        # noqa
        ctx = android.mActivity
        files_dir = ctx.getFilesDir().getAbsolutePath()
        bundled = os.path.join(files_dir, "ffmpeg")
        if os.path.isfile(bundled):
            os.chmod(bundled, 0o755)
            return bundled
    except Exception:
        pass
    return shutil.which("ffmpeg") or ""

FFMPEG = _find_ffmpeg()

# ── Watermark helpers ─────────────────────────────────────────────────────────
LOGO_TXT1 = "VideoMate Crew"
LOGO_TXT2 = "videomatecrew.app"

def apply_watermark(src, dst, ffmpeg_bin):
    """Burn text watermark into video using ffmpeg. Returns (ok, err)."""
    if not ffmpeg_bin or not os.path.isfile(ffmpeg_bin):
        # No ffmpeg → just copy as-is
        shutil.copy2(src, dst)
        return True, "ffmpeg not available – watermark skipped"

    def esc(t):
        return t.replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:")

    t1 = esc(LOGO_TXT1)
    t2 = esc(LOGO_TXT2)

    vf = (
        f"drawtext=text='{t1}':fontcolor=white@0.7:fontsize=24"
        f":x=w-tw-10:y=10:shadowcolor=black:shadowx=1:shadowy=1,"
        f"drawtext=text='{t2}':fontcolor=white@0.5:fontsize=14"
        f":x=w-tw-10:y=44:shadowcolor=black:shadowx=1:shadowy=1"
    )

    cmd = [
        ffmpeg_bin, "-y",
        "-i", src,
        "-vf", vf,
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        dst
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=600)
        if r.returncode != 0:
            return False, r.stderr.decode(errors="replace")[-300:]
        return True, ""
    except Exception as e:
        return False, str(e)

# ── yt-dlp helpers ────────────────────────────────────────────────────────────
def fetch_formats(url):
    """Return list of dicts with id/label/height/ext/type, sorted best-first."""
    import yt_dlp
    opts = {"quiet": True, "no_warnings": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)

    title = info.get("title", "video")
    fmts  = info.get("formats", [])
    result = []

    for f in fmts:
        fid    = f.get("format_id", "")
        vcodec = f.get("vcodec", "none") or "none"
        acodec = f.get("acodec", "none") or "none"
        height = f.get("height") or 0
        ext    = f.get("ext", "mp4")
        tbr    = f.get("tbr") or 0
        abr    = f.get("abr") or 0

        has_v = vcodec != "none"
        has_a = acodec != "none"

        if has_v and has_a:
            ftype = "video+audio"
            label = f"▶ {height}p [{ext.upper()}] (video+audio)"
        elif has_v:
            ftype = "video-only"
            label = f"🎬 {height}p [{ext.upper()}] (video only)"
        elif has_a:
            ftype = "audio-only"
            brate = f"{int(abr)}kbps" if abr else ""
            label = f"🎵 Audio [{ext.upper()}] {brate}"
        else:
            continue

        result.append({
            "id": fid, "label": label, "height": height,
            "ext": ext, "type": ftype, "tbr": tbr, "title": title
        })

    # Add best-combined option at top
    result.insert(0, {
        "id": "bestvideo+bestaudio/best",
        "label": "⭐ Best Quality (auto-merge)",
        "height": 9999, "ext": "mp4",
        "type": "video+audio", "tbr": 0, "title": title
    })
    # Sort: combined first, then by height desc, then audio
    def sort_key(x):
        order = {"video+audio": 0, "video-only": 1, "audio-only": 2}
        return (order[x["type"]], -x["height"], -x["tbr"])
    result.sort(key=sort_key)
    return result, title


def download_item(url, fmt_id, ext, out_dir, tmp_dir,
                  watermark_on, ffmpeg_bin,
                  progress_cb, status_cb, done_cb):
    """Download one item, optionally apply watermark, call callbacks."""
    import yt_dlp

    def hook(d):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 1
            pct   = min(d.get("downloaded_bytes", 0) / total * 80, 80)
            Clock.schedule_once(lambda dt: progress_cb(pct), 0)

    out_tpl = os.path.join(tmp_dir, "%(title)s.%(ext)s")
    opts = {
        "outtmpl":  out_tpl,
        "format":   fmt_id,
        "quiet":    True,
        "no_warnings": True,
        "progress_hooks": [hook],
        "merge_output_format": "mp4",
        "postprocessors": [],
        "concurrent_fragment_downloads": 4,
        "retries": 5,
        "fragment_retries": 5,
    }

    try:
        Clock.schedule_once(lambda dt: status_cb("Downloading…", ACCENT), 0)
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            # Find the downloaded file
            filename = ydl.prepare_filename(info)
            # Handle merge → .mp4 extension
            for candidate in [filename,
                               os.path.splitext(filename)[0] + ".mp4",
                               os.path.splitext(filename)[0] + ".mkv"]:
                if os.path.isfile(candidate):
                    filename = candidate
                    break

        Clock.schedule_once(lambda dt: progress_cb(82), 0)

        # Final output path
        base = os.path.splitext(os.path.basename(filename))[0]
        safe = "".join(c for c in base if c.isalnum() or c in " _-")[:80]
        final_ext = "mp4" if watermark_on else os.path.splitext(filename)[1].lstrip(".")
        final = os.path.join(out_dir, f"{safe}.{final_ext}")

        if watermark_on and ffmpeg_bin:
            Clock.schedule_once(lambda dt: status_cb("Burning watermark…", WARN), 0)
            ok, err = apply_watermark(filename, final, ffmpeg_bin)
            os.remove(filename)
            if not ok:
                Clock.schedule_once(lambda dt: done_cb(False, f"Watermark error: {err}"), 0)
                return
        else:
            shutil.move(filename, final)

        Clock.schedule_once(lambda dt: progress_cb(100), 0)
        Clock.schedule_once(lambda dt: done_cb(True, f"Saved → {final}"), 0)

    except Exception as e:
        Clock.schedule_once(lambda dt: done_cb(False, str(e)[:200]), 0)


# ── UI helpers ────────────────────────────────────────────────────────────────
def mk_btn(text, color=ACCENT, **kw):
    b = Button(text=text, background_normal="", background_color=color,
               color=TEXT, font_size=dp(13), bold=True,
               size_hint_y=None, height=dp(42), **kw)
    return b

def mk_lbl(text, color=TEXT, size=13, **kw):
    return Label(text=text, color=color, font_size=dp(size),
                 halign="left", text_size=(None, None), **kw)

def card(h):
    b = BoxLayout(size_hint_y=None, height=dp(h), padding=dp(4), spacing=dp(6))
    return b


# ── Main Layout ───────────────────────────────────────────────────────────────
class VMCLayout(BoxLayout):

    def __init__(self, **kw):
        super().__init__(orientation="vertical", padding=dp(10),
                         spacing=dp(6), **kw)
        self._formats  = []
        self._sel_fmt  = None
        self._video_title = ""
        self._queue    = []   # list of (url, fmt, title)
        self._busy     = False
        self._ffmpeg   = FFMPEG
        self._build()

    # ── Build ─────────────────────────────────────────────────────────────────
    def _build(self):
        # Header
        hdr = card(44)
        hdr.add_widget(Label(
            text="[b][color=#BB86FC]Video[/color][color=#03DAC6]Mate[/color] Crew 3.0[/b]",
            markup=True, font_size=dp(19), color=TEXT, size_hint_x=0.65))
        self._ffmpeg_lbl = mk_lbl(
            "✅ ffmpeg" if self._ffmpeg else "⚠ no ffmpeg",
            color=OK if self._ffmpeg else WARN, size=11, size_hint_x=0.35)
        hdr.add_widget(self._ffmpeg_lbl)
        self.add_widget(hdr)

        # URL input
        url_row = card(44)
        self.url_in = TextInput(
            hint_text="Paste URL (YouTube, TikTok, Instagram, …)",
            multiline=False, background_color=SURF, foreground_color=TEXT,
            hint_text_color=DIM, font_size=dp(13), size_hint_x=0.72)
        url_row.add_widget(self.url_in)
        fb = mk_btn("Fetch", color=ACCENT, size_hint_x=0.28)
        fb.bind(on_press=self._on_fetch)
        url_row.add_widget(fb)
        self.add_widget(url_row)

        # Status
        self.status = mk_lbl("Paste a URL then tap Fetch", color=DIM,
                              size_hint_y=None, height=dp(26))
        self.add_widget(self.status)

        # Format spinner  (full width)
        self.spinner = Spinner(
            text="── Select Quality / Format ──",
            values=[], background_normal="",
            background_color=SURF, color=TEXT,
            font_size=dp(12), size_hint_y=None, height=dp(42))
        self.spinner.bind(text=self._on_fmt_select)
        self.add_widget(self.spinner)

        # Watermark toggle
        wm_row = card(36)
        wm_row.add_widget(mk_lbl("🎨 Burn Watermark", size=13, size_hint_x=0.65))
        self.wm_switch = Switch(active=True, size_hint_x=0.35)
        wm_row.add_widget(self.wm_switch)
        self.add_widget(wm_row)

        # Progress
        self.prog = ProgressBar(max=100, value=0,
                                size_hint_y=None, height=dp(12))
        self.add_widget(self.prog)
        self.prog_lbl = mk_lbl("", color=DIM, size=11,
                                size_hint_y=None, height=dp(18))
        self.add_widget(self.prog_lbl)

        # Action buttons
        btn_row = card(44)
        dl_now = mk_btn("⬇  Download Now", color=TEAL, size_hint_x=0.55)
        dl_now.bind(on_press=self._on_download_now)
        btn_row.add_widget(dl_now)
        add_q = mk_btn("+ Queue", color=SURF, size_hint_x=0.25)
        add_q.color = ACCENT
        add_q.bind(on_press=self._on_add_queue)
        btn_row.add_widget(add_q)
        clr = mk_btn("✖", color=SURF, size_hint_x=0.20)
        clr.color = ERR
        clr.bind(on_press=self._on_clear_queue)
        btn_row.add_widget(clr)
        self.add_widget(btn_row)

        # Queue list
        self.add_widget(mk_lbl("Queue", color=ACCENT, size=12,
                                size_hint_y=None, height=dp(22)))
        sv = ScrollView(size_hint_y=0.25)
        self.queue_lbl = Label(
            text="Empty", color=DIM, font_size=dp(11),
            size_hint_y=None, halign="left", valign="top",
            text_size=(None, None))
        self.queue_lbl.bind(texture_size=self.queue_lbl.setter("size"))
        sv.add_widget(self.queue_lbl)
        self.add_widget(sv)

        start_q = mk_btn("▶  Start Queue", color=ACCENT)
        start_q.bind(on_press=self._on_start_queue)
        self.add_widget(start_q)

        # Save path
        path_row = card(24)
        path_row.add_widget(mk_lbl(f"💾 {DL_DIR}", color=DIM, size=10))
        self.add_widget(path_row)

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _st(self, msg, color=DIM):
        self.status.text  = msg
        self.status.color = color

    def _pct(self, v, msg=""):
        self.prog.value   = v
        self.prog_lbl.text = msg

    # ── Fetch formats ─────────────────────────────────────────────────────────
    def _on_fetch(self, *_):
        url = self.url_in.text.strip()
        if not url:
            self._st("⚠ Paste a URL first", WARN); return
        self._st("Fetching formats…", ACCENT)
        self.spinner.values = []
        self.spinner.text   = "── fetching… ──"
        self._formats = []
        threading.Thread(target=self._fetch_worker, args=(url,), daemon=True).start()

    def _fetch_worker(self, url):
        try:
            fmts, title = fetch_formats(url)
            Clock.schedule_once(lambda dt: self._fetch_done(fmts, title), 0)
        except Exception as e:
            Clock.schedule_once(lambda dt: self._st(f"Error: {e}", ERR), 0)

    def _fetch_done(self, fmts, title):
        self._formats      = fmts
        self._video_title  = title
        labels = [f["label"] for f in fmts]
        self.spinner.values = labels
        self.spinner.text   = labels[0] if labels else "No formats found"
        self._sel_fmt = fmts[0] if fmts else None
        short = title[:45] + "…" if len(title) > 45 else title
        self._st(f"✅ {len(fmts)} formats  |  {short}", OK)

    def _on_fmt_select(self, spinner, text):
        for f in self._formats:
            if f["label"] == text:
                self._sel_fmt = f; break

    # ── Download Now ──────────────────────────────────────────────────────────
    def _on_download_now(self, *_):
        if self._busy:
            self._st("⚠ Already downloading", WARN); return
        url = self.url_in.text.strip()
        if not url or not self._sel_fmt:
            self._st("⚠ Fetch formats first, then select quality", WARN); return
        self._busy = True
        self._pct(0, "Starting…")
        wm = self.wm_switch.active
        f  = self._sel_fmt
        threading.Thread(
            target=download_item,
            args=(url, f["id"], f["ext"], DL_DIR, TMP_DIR,
                  wm, self._ffmpeg,
                  lambda p: Clock.schedule_once(lambda dt: self._pct(p), 0),
                  lambda m, c: Clock.schedule_once(lambda dt: self._st(m, c), 0),
                  self._dl_done),
            daemon=True).start()

    def _dl_done(self, ok, msg):
        self._busy = False
        self._st(msg, OK if ok else ERR)
        if not ok:
            self._pct(0)

    # ── Queue ─────────────────────────────────────────────────────────────────
    def _on_add_queue(self, *_):
        url = self.url_in.text.strip()
        if not url or not self._sel_fmt:
            self._st("⚠ Fetch first", WARN); return
        self._queue.append((url, dict(self._sel_fmt), self._video_title))
        self._refresh_q()
        self._st(f"Added ({len(self._queue)} in queue)", OK)

    def _on_clear_queue(self, *_):
        self._queue.clear(); self._refresh_q()

    def _refresh_q(self):
        if not self._queue:
            self.queue_lbl.text = "Empty"; return
        lines = []
        for i, (u, f, t) in enumerate(self._queue, 1):
            short = t[:38] + "…" if len(t) > 38 else t
            lines.append(f"{i}. {short}  [{f['label'][:28]}]")
        self.queue_lbl.text = "\n".join(lines)

    def _on_start_queue(self, *_):
        if self._busy:
            self._st("⚠ Already downloading", WARN); return
        if not self._queue:
            self._st("Queue is empty", WARN); return
        self._busy = True
        items = list(self._queue)
        self._queue.clear(); self._refresh_q()
        self._st(f"Queue started ({len(items)} items)…", ACCENT)
        threading.Thread(target=self._queue_worker,
                         args=(items,), daemon=True).start()

    def _queue_worker(self, items):
        total = len(items)
        wm    = self.wm_switch.active
        for idx, (url, f, title) in enumerate(items, 1):

            def upd_pct(p, i=idx, t=total):
                overall = ((i - 1) * 100 + p) / t
                Clock.schedule_once(
                    lambda dt, v=overall, i=i, t=t:
                        self._pct(v, f"Item {i}/{t} — {v:.0f}%"), 0)

            done_evt = threading.Event()
            res = [True, ""]

            def on_done(ok, msg):
                res[0], res[1] = ok, msg; done_evt.set()

            Clock.schedule_once(
                lambda dt, i=idx, t=total, ti=title:
                    self._st(f"[{i}/{t}] {ti[:30]}…", ACCENT), 0)

            threading.Thread(
                target=download_item,
                args=(url, f["id"], f["ext"], DL_DIR, TMP_DIR,
                      wm, self._ffmpeg, upd_pct,
                      lambda m, c: Clock.schedule_once(lambda dt: self._st(m, c), 0),
                      on_done),
                daemon=True).start()
            done_evt.wait()

            if not res[0]:
                Clock.schedule_once(
                    lambda dt, msg=res[1]: self._st(f"Error: {msg}", ERR), 0)

        Clock.schedule_once(lambda dt: self._st("✅ Queue complete!", OK), 0)
        Clock.schedule_once(lambda dt: self._pct(100, "Done"), 0)
        self._busy = False


# ── App ───────────────────────────────────────────────────────────────────────
class VideoMateApp(App):
    title = "VideoMate Crew 3.0"

    def build(self):
        from kivy.core.window import Window
        Window.clearcolor = BG
        return VMCLayout()

    def on_pause(self):   return True   # keep alive on home-button
    def on_resume(self):  pass


if __name__ == "__main__":
    VideoMateApp().run()
