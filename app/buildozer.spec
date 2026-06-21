[app]
title           = VideoMate Crew
package.name    = videomatecrew
package.domain  = com.videomate
source.dir      = .
source.include_exts = py,png,jpg,kv,atlas,so,bin
version         = 3.0

# ── Requirements ──────────────────────────────────────────────────────────────
# ffpyplayer pulls in ffmpeg native libs for Android automatically
requirements = python3,kivy,yt-dlp,ffpyplayer,certifi,requests

# ── Android ───────────────────────────────────────────────────────────────────
android.permissions = \
    INTERNET,\
    WRITE_EXTERNAL_STORAGE,\
    READ_EXTERNAL_STORAGE,\
    MANAGE_EXTERNAL_STORAGE

android.api       = 33
android.minapi    = 24
android.ndk       = 25b
android.ndk_api   = 21
android.archs     = arm64-v8a

# Keep APK lean - single ABI
android.release_artifact = apk
android.accept_sdk_license = True

# Entrypoint
android.entrypoint = org.kivy.android.PythonActivity
android.apptheme   = @android:style/Theme.NoTitleBar

# ── Orientation ───────────────────────────────────────────────────────────────
orientation = portrait
fullscreen  = 0

# ── Icon & splash (optional, add your own) ───────────────────────────────────
# icon.filename    = %(source.dir)s/icon.png
# presplash.colour = #0D0D0D

[buildozer]
log_level    = 2
warn_on_root = 1
