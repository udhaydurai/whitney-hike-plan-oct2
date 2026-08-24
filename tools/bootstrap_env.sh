#!/usr/bin/env bash
# Make this container able to run tools/verify_site.py. SOURCE this, do not execute it —
# it has to export PATH and LD_LIBRARY_PATH into the calling shell. publish.sh sources it
# automatically, so the normal weekly path needs no separate step.
#
# ── Why this file exists
#
# publish.sh will not publish a site that fails verification, and verification drives a
# real Chromium through Playwright. Neither is present in a fresh session container, and
# the container has no root, so `sudo playwright install-deps` — the fix Playwright itself
# prints — cannot run. A session that met this wall had three options: skip verification,
# improvise an install, or give up before committing. All three are bad. The third is what
# actually happened, and because it stopped *before* publish.sh reached its commit step, it
# looked from the outside like the data had failed to check in. It had not; nothing had
# been written yet.
#
# The Aug 23 session improvised its way through in about five minutes. That is worse than
# it sounds: improvisation is exactly what this project does not want in the one path
# allowed to write objective metrics. Every step here should be scripted and identical
# each week, so the interesting part of the run is the data and never the toolchain.
#
# Everything below is user-scoped. Nothing needs root, nothing touches the system, and a
# container that already has what it needs exits in well under a second.

_bootstrap_note() { echo "   bootstrap: $*"; }

# Fresh pip --user installs land here and are not on PATH by default.
export PATH="$PATH:$HOME/.local/bin"

# Where we unpack .deb payloads we cannot install properly for want of root.
_DEPS="$HOME/.local/whitney-deps"
export LD_LIBRARY_PATH="$_DEPS/usr/lib/x86_64-linux-gnu:$_DEPS/usr/lib/aarch64-linux-gnu:${LD_LIBRARY_PATH:-}"

# ── 1. the Playwright python module
if ! python3 -c "import playwright" 2>/dev/null; then
  _bootstrap_note "installing playwright (absent in this container)"
  pip3 install --quiet --user playwright 2>&1 | tail -2 || {
    echo "   bootstrap FAILED: could not install playwright." >&2
    return 1 2>/dev/null || exit 1
  }
fi

# ── 2. the browser itself
#
# verify_site.py resolves $CHROME_PATH, then any chromium under ~/.cache/ms-playwright,
# before its historical /opt/pw-browsers fallback — so installing to the user cache is
# enough and no path needs to be passed anywhere.
if ! ls "$HOME"/.cache/ms-playwright/chromium-*/chrome-linux/chrome >/dev/null 2>&1; then
  _bootstrap_note "downloading chromium (~110 MB, once per container)"
  # This prints a host-validation warning about missing libs and exits non-zero on some
  # versions. The download still succeeds, and step 3 is what actually resolves the libs.
  python3 -m playwright install chromium >/dev/null 2>&1 || true
fi

_CHROME=$(ls -d "$HOME"/.cache/ms-playwright/chromium-*/chrome-linux/chrome 2>/dev/null | head -1)
if [[ -z "$_CHROME" ]]; then
  echo "   bootstrap FAILED: chromium did not install." >&2
  return 1 2>/dev/null || exit 1
fi

# ── 3. shared libraries Chromium needs and the image lacks
#
# `sudo playwright install-deps` is not available without root. apt-get *download* is,
# because it only writes to the cwd, so we fetch the .deb and unpack the payload into a
# user directory already on LD_LIBRARY_PATH above.
#
# On Aug 23 exactly one library was missing (libXdamage.so.1). The rest of the table is
# the remainder of Chromium's headless dependency set, listed so that a container which
# drifts further is still a scripted fix rather than another improvised one.
_libpkg() {
  case "$1" in
    libXdamage.so.1)   echo libxdamage1 ;;
    libXfixes.so.3)    echo libxfixes3 ;;
    libXrandr.so.2)    echo libxrandr2 ;;
    libXcomposite.so.1) echo libxcomposite1 ;;
    libXext.so.6)      echo libxext6 ;;
    libXi.so.6)        echo libxi6 ;;
    libXtst.so.6)      echo libxtst6 ;;
    libxkbcommon.so.0) echo libxkbcommon0 ;;
    libgbm.so.1)       echo libgbm1 ;;
    libdrm.so.2)       echo libdrm2 ;;
    libasound.so.2)    echo libasound2 ;;
    libatk-1.0.so.0)   echo libatk1.0-0 ;;
    libatk-bridge-2.0.so.0) echo libatk-bridge2.0-0 ;;
    libatspi.so.0)     echo libatspi2.0-0 ;;
    libcups.so.2)      echo libcups2 ;;
    libpango-1.0.so.0) echo libpango-1.0-0 ;;
    libcairo.so.2)     echo libcairo2 ;;
    libnss3.so)        echo libnss3 ;;
    libnspr4.so)       echo libnspr4 ;;
    *)                 echo "" ;;
  esac
}

_missing=$(ldd "$_CHROME" 2>/dev/null | awk '/not found/{print $1}' | sort -u)
if [[ -n "$_missing" ]]; then
  mkdir -p "$_DEPS" && _tmp=$(mktemp -d)
  for _lib in $_missing; do
    _pkg=$(_libpkg "$_lib")
    if [[ -z "$_pkg" ]]; then
      echo "   bootstrap: no package mapping for $_lib — add one to _libpkg()" >&2
      continue
    fi
    _bootstrap_note "fetching $_pkg for $_lib"
    ( cd "$_tmp" && apt-get download "$_pkg" >/dev/null 2>&1 \
        && dpkg-deb -x "$_pkg"*.deb "$_DEPS" ) \
      || echo "   bootstrap: could not fetch $_pkg" >&2
  done
  rm -rf "$_tmp"

  # Re-check rather than assume. A library that is still missing means verification is
  # about to fail on a launch error, and saying so here is clearer than the traceback.
  _still=$(ldd "$_CHROME" 2>/dev/null | awk '/not found/{print $1}' | sort -u)
  if [[ -n "$_still" ]]; then
    echo "   bootstrap FAILED: still missing: $(echo $_still)" >&2
    return 1 2>/dev/null || exit 1
  fi
  _bootstrap_note "shared libraries resolved"
fi

unset _bootstrap_note _libpkg _CHROME _missing _still _lib _pkg _tmp _DEPS
