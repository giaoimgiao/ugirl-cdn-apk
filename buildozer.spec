[app]
title = UGIRL CDN
package.name = ugirlcdn
package.domain = org.ugirl

source.dir = .
source.include_exts = py
source.include_patterns = ugirl_cdn_app.py, main.py
version = 2.0.0

requirements = python3,kivy

orientation = portrait
fullscreen = 0

android.permissions = INTERNET
android.api = 33
android.minapi = 21
android.ndk = 25b
android.archs = arm64-v8a

[buildozer]
log_level = 2
warn_on_root = 1