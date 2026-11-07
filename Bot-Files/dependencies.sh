#!/usr/bin/env bash
#
# dependencies.sh
#
# Python dependencies for Folda Tunez. Installs into a virtual environment:
#   - if a venv is already active, that one is used
#   - otherwise an existing ./venv or ./.venv is activated, or ./venv is created
#
# System packages (ffmpeg, libopus, Deno, ...) are NOT handled here; run
# global_depends.sh first, outside the venv.
#
# Safe to re-run.
#
# Usage: chmod +x dependencies.sh && ./dependencies.sh
#        VENV_DIR=myvenv PYTHON_BIN=python3.12 ./dependencies.sh

set -euo pipefail

# --- Configuration -----------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${PROJECT_DIR:-$SCRIPT_DIR}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
MIN_PY_MAJOR=3
MIN_PY_MINOR=10   # discord.py 2.x requires 3.10+

# Discord enforces DAVE (E2EE) on voice; discord.py 2.7+ ships it via the
# 'davey' package in the [voice] extra. Older versions join but stay silent.
PIP_PACKAGES=(
    "discord.py[voice]>=2.7"
    "PyNaCl>=1.5"
    "davey"
    "yt-dlp"
    "yt-dlp-ejs"
    "python-dotenv"
    "audioop-lts; python_version >= '3.13'"
)
# -----------------------------------------------------------------------------

info()  { printf '\033[1;34m[INFO]\033[0m  %s\n' "$*"; }
warn()  { printf '\033[1;33m[WARN]\033[0m  %s\n' "$*"; }
error() { printf '\033[1;31m[ERROR]\033[0m %s\n' "$*" >&2; }
ok()    { printf '\033[1;32m[ OK ]\033[0m  %s\n' "$*"; }

# --- Python check (system interpreter, used only to build the venv) ----------
check_python() {
    if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
        error "'${PYTHON_BIN}' not found. Run ./global_depends.sh first, or set PYTHON_BIN."
        exit 1
    fi
    if ! "$PYTHON_BIN" -c "import sys; sys.exit(0 if sys.version_info >= (${MIN_PY_MAJOR}, ${MIN_PY_MINOR}) else 1)"; then
        error "Python ${MIN_PY_MAJOR}.${MIN_PY_MINOR}+ required; found $("$PYTHON_BIN" -c 'import sys; print("%d.%d" % sys.version_info[:2])')."
        exit 1
    fi
    ok "Python $("$PYTHON_BIN" -c 'import sys; print("%d.%d" % sys.version_info[:2])') detected."
}

# --- Venv: use the active one, else find/create one --------------------------
activate_venv() {
    if [[ -n "${VIRTUAL_ENV:-}" ]]; then
        ok "Using active virtualenv: ${VIRTUAL_ENV}"
        return
    fi

    local dir="${VENV_DIR:-}"
    if [[ -z "$dir" ]]; then
        if   [[ -f "$PROJECT_DIR/venv/bin/activate"  ]]; then dir="$PROJECT_DIR/venv"
        elif [[ -f "$PROJECT_DIR/.venv/bin/activate" ]]; then dir="$PROJECT_DIR/.venv"
        else dir="$PROJECT_DIR/venv"
        fi
    fi
    [[ "$dir" = /* ]] || dir="$PROJECT_DIR/$dir"

    if [[ ! -f "$dir/bin/activate" ]]; then
        info "Creating virtual environment in ${dir}..."
        if ! "$PYTHON_BIN" -m venv "$dir"; then
            rm -rf "$dir"
            error "venv creation failed. On Debian/Ubuntu install python3-venv (global_depends.sh does this)."
            exit 1
        fi
    else
        info "Using existing virtual environment in ${dir}"
    fi

    # activate scripts reference unset variables
    set +u
    # shellcheck disable=SC1091
    source "$dir/bin/activate"
    set -u
    ok "Activated ${VIRTUAL_ENV}"
}

# --- pip installs ------------------------------------------------------------
install_python_packages() {
    info "Upgrading pip, setuptools, wheel..."
    python -m pip install --upgrade pip setuptools wheel

    info "Installing Python packages..."
    python -m pip install --upgrade "${PIP_PACKAGES[@]}"
    ok "Python packages installed."
}

# --- Verification (runs inside the venv) -------------------------------------
verify_install() {
    info "Verifying installation..."

    if ! python - <<'PY'
import ctypes.util
import sys

failed = False

def need(label, fn):
    global failed
    try:
        print(f"[ OK ]  {label} {fn()}")
    except Exception as e:
        failed = True
        print(f"[ERROR] {label} unavailable: {e}")

def dpy():
    import discord
    if discord.version_info < (2, 7):
        raise RuntimeError(f"discord.py {discord.__version__} predates DAVE voice support, need >= 2.7")
    return discord.__version__

def nacl_v():
    import nacl
    return nacl.__version__

def davey_v():
    import davey
    return getattr(davey, "__version__", "")

def ytdlp():
    import yt_dlp
    return yt_dlp.version.__version__

def dotenv_v():
    import dotenv  # noqa: F401
    return "loaded"

def audioop_v():
    try:
        import audioop  # noqa: F401
    except ImportError:
        import audioop_lts  # noqa: F401
    return "available"

need("discord.py", dpy)
need("PyNaCl", nacl_v)
need("davey (DAVE voice E2EE)", davey_v)
need("yt-dlp", ytdlp)
need("python-dotenv", dotenv_v)
need("audioop", audioop_v)

opus = ctypes.util.find_library("opus")
if opus:
    print(f"[ OK ]  libopus: {opus}")
else:
    print("[WARN]  libopus not found by ctypes (main.py also probes common paths at startup)")

sys.exit(1 if failed else 0)
PY
    then
        error "Python package verification failed. See messages above."
        exit 1
    fi

    if command -v ffmpeg >/dev/null 2>&1; then
        ok "ffmpeg: $(ffmpeg -version 2>/dev/null | head -n1)"
        local encoders
        encoders="$(ffmpeg -hide_banner -encoders 2>/dev/null || true)"
        if ! grep -q libopus <<<"$encoders"; then
            warn "ffmpeg has no libopus encoder - the bot would be silent. Run ./global_depends.sh."
        fi
    else
        warn "ffmpeg not on PATH. Run ./global_depends.sh (outside the venv) to install it."
    fi

    if [[ ! -f "$PROJECT_DIR/.env" ]]; then
        warn ".env not found. Run ./global_depends.sh to set DISCORD_BOT_TOKEN, or create it manually."
    fi
}

main() {
    echo
    info "Folda Tunez Python dependency installer"
    info "Project dir: ${PROJECT_DIR}"
    echo

    check_python
    activate_venv
    install_python_packages
    verify_install

    echo
    ok "All Python dependencies installed."
    echo
    info "Next steps:"
    echo "  1. source ${VIRTUAL_ENV}/bin/activate"
    echo "  2. cd ${PROJECT_DIR} && python main.py"
    echo "  3. On startup, check bot.log for 'Voice stack OK'"
    echo
}

main "$@"
