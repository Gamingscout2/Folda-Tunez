#!/usr/bin/env bash
#
# dependencies.sh
#
# Python dependencies for Folda Tunez, installed into a virtual environment:
#   - if a venv is already active, that one is used
#   - otherwise an existing ./venv or ./.venv is activated, or ./venv is created
#
# Packages come from requirements.txt (pinned: see the davey note there) and
# are FORCE-REINSTALLED every run so stale or wrong versions can't survive.
# The script then runs a real audio self-test (ffmpeg -> discord.py -> libopus).
#
# System packages (ffmpeg, libopus, Deno, ...) are NOT handled here; run
# global_depends.sh first, outside the venv.
#
# Usage: ./dependencies.sh [--recreate] [--no-force]
#   --recreate   delete the venv and build a fresh one (use this if audio is
#                still silent after a normal run)
#   --no-force   plain 'pip install -U' instead of --force-reinstall
#   VENV_DIR=myvenv PYTHON_BIN=python3.14 ./dependencies.sh

set -euo pipefail

# --- Configuration -----------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${PROJECT_DIR:-$SCRIPT_DIR}"
REQ_FILE="${REQ_FILE:-$SCRIPT_DIR/requirements.txt}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
MIN_PY_MAJOR=3
MIN_PY_MINOR=10   # discord.py 2.x requires 3.10+
RECREATE=0
FORCE=1
# -----------------------------------------------------------------------------

info()  { printf '\033[1;34m[INFO]\033[0m  %s\n' "$*"; }
warn()  { printf '\033[1;33m[WARN]\033[0m  %s\n' "$*"; }
error() { printf '\033[1;31m[ERROR]\033[0m %s\n' "$*" >&2; }
ok()    { printf '\033[1;32m[ OK ]\033[0m  %s\n' "$*"; }

parse_args() {
    local a
    for a in "$@"; do
        case "$a" in
            --recreate) RECREATE=1 ;;
            --no-force) FORCE=0 ;;
            -h|--help)  sed -n '2,24p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
            *) error "Unknown option: $a (try --help)"; exit 1 ;;
        esac
    done
}

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

check_requirements_file() {
    if [[ ! -f "$REQ_FILE" ]]; then
        error "Missing ${REQ_FILE}. It ships with the bot; run 'git pull' or restore it."
        exit 1
    fi
}

# --- Venv: use the active one, else find/create one --------------------------
activate_venv() {
    if [[ -n "${VIRTUAL_ENV:-}" ]]; then
        if (( RECREATE )); then
            error "--recreate cannot rebuild the active venv (${VIRTUAL_ENV}). Run 'deactivate' first."
            exit 1
        fi
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

    # only ever delete a directory that looks like a venv
    if (( RECREATE )) && [[ -e "$dir" ]]; then
        if [[ -f "$dir/pyvenv.cfg" ]]; then
            warn "Removing existing virtualenv ${dir}"
            rm -rf -- "$dir"
        else
            error "${dir} exists but has no pyvenv.cfg; refusing to delete it."
            exit 1
        fi
    fi

    if [[ ! -f "$dir/bin/activate" ]]; then
        info "Creating virtual environment in ${dir}..."
        if ! "$PYTHON_BIN" -m venv "$dir"; then
            rm -rf -- "$dir"
            error "venv creation failed. Run ./global_depends.sh (installs python3-venv/devel)."
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

    local flags=(--upgrade)
    if (( FORCE )); then
        flags+=(--force-reinstall --no-cache-dir)
        info "Force-reinstalling every package from ${REQ_FILE}..."
    else
        info "Installing packages from ${REQ_FILE}..."
    fi
    python -m pip install "${flags[@]}" -r "$REQ_FILE"

    info "Checking dependency consistency (pip check)..."
    if python -m pip check; then
        ok "pip check: no broken requirements."
    else
        warn "pip check reported conflicts (see above). Re-run with --recreate if audio is silent."
    fi

    info "Installed versions:"
    python -m pip list 2>/dev/null | grep -Ei '^(discord|davey|pynacl|yt-dlp|python-dotenv|audioop|aiohttp) ' || true
    ok "Python packages installed."
}

# --- Verification (runs inside the venv) -------------------------------------
verify_install() {
    info "Verifying installation and running the audio self-test..."

    if ! FFMPEG_BIN="${FFMPEG_PATH:-ffmpeg}" python - <<'PY'
import ctypes.util
import os
import shutil
import subprocess
import sys

failed = False


def check(label, fn):
    global failed
    try:
        res = fn()
        print(f"[ OK ]  {label}{': ' + str(res) if res else ''}")
    except Exception as e:
        failed = True
        print(f"[ERROR] {label}: {type(e).__name__}: {e}")


def ver(name):
    from importlib.metadata import version
    return version(name)


def discord_ok():
    import discord
    if discord.version_info < (2, 7, 1):
        raise RuntimeError(f"discord.py {discord.__version__} too old, need >= 2.7.1")
    return discord.__version__


def davey_ok():
    v = ver("davey")
    parts = tuple(int(p) for p in v.split(".")[:3] if p.isdigit())
    if parts >= (0, 2, 0):
        raise RuntimeError(
            f"davey {v} breaks voice with discord.py 2.7 (bot would be SILENT). "
            "Run ./dependencies.sh --recreate to install davey<0.2."
        )
    import davey
    # real object construction + key package exercises the native module
    s = davey.DaveSession(davey.DAVE_PROTOCOL_VERSION, 1, 2)
    if not s.get_serialized_key_package():
        raise RuntimeError("DAVE session produced no key package")
    return v


def nacl_ok():
    import nacl.secret
    nacl.secret.Aead(b"\0" * 32)
    return ver("PyNaCl")


def other():
    import dotenv  # noqa: F401
    import yt_dlp
    try:
        import audioop  # noqa: F401
    except ImportError:
        import audioop_lts  # noqa: F401
    return f"yt-dlp {yt_dlp.version.__version__}"


def opus_ok():
    import discord
    if not discord.opus.is_loaded():
        names = [ctypes.util.find_library("opus"), "libopus.so.0", "libopus.so"]
        for n in filter(None, names):
            try:
                discord.opus.load_opus(n)
                break
            except Exception:
                continue
    if not discord.opus.is_loaded():
        raise RuntimeError("libopus could not be loaded. Run ./global_depends.sh to install it.")
    enc = discord.opus.Encoder()
    out = enc.encode(b"\0" * enc.FRAME_SIZE, enc.SAMPLES_PER_FRAME)
    if not out:
        raise RuntimeError("libopus encoder returned nothing")
    return "loaded, encoder works"


def pipeline_ok():
    """ffmpeg -> PCM -> discord.py -> libopus, the exact path used for playback."""
    import discord
    exe = os.environ.get("FFMPEG_BIN", "ffmpeg")
    if not shutil.which(exe):
        raise RuntimeError(f"ffmpeg not found ('{exe}'). Run ./global_depends.sh.")
    src = discord.FFmpegPCMAudio(
        "sine=frequency=440:duration=1", executable=exe,
        before_options="-f lavfi", options="-loglevel error",
    )
    enc = discord.opus.Encoder()
    frames = total = 0
    try:
        while True:
            pcm = src.read()
            if not pcm:
                break
            frames += 1
            total += len(enc.encode(pcm, enc.SAMPLES_PER_FRAME))
    finally:
        src.cleanup()
    if frames < 40 or total == 0:
        raise RuntimeError(f"only {frames} frames / {total} opus bytes from 1s of audio")
    return f"{frames} frames -> {total} opus bytes"


check("discord.py", discord_ok)
check("davey (DAVE voice E2EE, must be <0.2)", davey_ok)
check("PyNaCl", nacl_ok)
check("yt-dlp / dotenv / audioop", other)
check("libopus", opus_ok)
check("audio pipeline", pipeline_ok)
sys.exit(1 if failed else 0)
PY
    then
        error "Verification FAILED. Fix the [ERROR] lines above; the bot will be silent until they pass."
        exit 1
    fi

    if [[ ! -f "$PROJECT_DIR/.env" ]]; then
        warn ".env not found. Run ./global_depends.sh to set DISCORD_BOT_TOKEN, or create it manually."
    fi
}

main() {
    parse_args "$@"
    echo
    info "Folda Tunez Python dependency installer"
    info "Project dir: ${PROJECT_DIR}"
    echo

    check_python
    check_requirements_file
    activate_venv
    install_python_packages
    verify_install

    echo
    ok "All Python dependencies installed and the audio self-test passed."
    echo
    info "Next steps:"
    echo "  1. source ${VIRTUAL_ENV}/bin/activate"
    echo "  2. cd ${PROJECT_DIR} && python main.py"
    echo "  3. On startup, check bot.log for 'Voice stack OK'"
    echo
}

main "$@"
