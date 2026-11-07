#!/usr/bin/env bash
#
# install_requirements.sh
#
# Robust dependency installer for Folda Tunez v0.5.3 (Linux).
#
# Installs system-level libraries (FFmpeg, libsodium, libffi, libopus,
# Python dev headers) via the detected package manager, then creates a
# virtual environment and installs the Python dependencies.
#
# Supports: Debian/Ubuntu, Fedora/RHEL/CentOS, Arch, openSUSE, Alpine.
#
# Usage:   chmod +x install_requirements.sh && ./install_requirements.sh
#
set -euo pipefail

# --- Configuration -----------------------------------------------------------
VENV_DIR="${VENV_DIR:-.venv}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
MIN_PY_MAJOR=3
MIN_PY_MINOR=10   # discord.py 2.x requires 3.10+
# -----------------------------------------------------------------------------

# --- Pretty logging ----------------------------------------------------------
info()  { printf '\033[1;34m[INFO]\033[0m  %s\n' "$*"; }
warn()  { printf '\033[1;33m[WARN]\033[0m  %s\n' "$*"; }
error() { printf '\033[1;31m[ERROR]\033[0m %s\n' "$*" >&2; }
ok()    { printf '\033[1;32m[ OK ]\033[0m  %s\n' "$*"; }

# --- Distro / package-manager detection -------------------------------------
detect_distro() {
    if [[ -f /etc/os-release ]]; then
        . /etc/os-release
        DISTRO_ID="${ID:-unknown}"
        DISTRO_LIKE="${ID_LIKE:-}"
    else
        DISTRO_ID="unknown"
        DISTRO_LIKE=""
    fi

    case "$DISTRO_ID" in
        debian|ubuntu|raspbian|linuxmint|pop)
            PKG_MGR="apt" ;;
        fedora|rhel|centos|rocky|almalinux)
            PKG_MGR="dnf" ;;
        arch|manjaro|endeavouros)
            PKG_MGR="pacman" ;;
        opensuse*|suse)
            PKG_MGR="zypper" ;;
        alpine)
            PKG_MGR="apk" ;;
        *)
            # Fall back to ID_LIKE
            case "$DISTRO_LIKE" in
                *debian*|*ubuntu*) PKG_MGR="apt" ;;
                *fedora*|*rhel*)   PKG_MGR="dnf" ;;
                *arch*)            PKG_MGR="pacman" ;;
                *suse*)            PKG_MGR="zypper" ;;
                *)                 PKG_MGR="unknown" ;;
            esac
            ;;
    esac

    info "Detected distro: ${DISTRO_ID} (package manager: ${PKG_MGR})"
    if [[ "$PKG_MGR" == "unknown" ]]; then
        error "Unsupported distribution. Please install dependencies manually."
        exit 1
    fi
}

# --- Root / sudo handling ----------------------------------------------------
run_as_root() {
    if [[ "$(id -u)" -eq 0 ]]; then
        "$@"
    elif command -v sudo >/dev/null 2>&1; then
        sudo "$@"
    else
        error "This script needs root privileges. Run as root or install sudo."
        exit 1
    fi
}

# --- System dependency installation -----------------------------------------
install_system_deps() {
    info "Installing system dependencies (FFmpeg, libsodium, libffi, libopus, Python dev headers)..."
    curl -fsSL https://deno.land/install.sh | sh
    export PATH="$HOME/.deno/bin:$PATH"
    case "$PKG_MGR" in
        apt)
            run_as_root apt-get update -qq
            run_as_root apt-get install -y \
                ffmpeg \
                libsodium-dev \
                libffi-dev \
                libopus0 \
                libopus-dev \
                python3-dev \
                python3-venv \
                python3-pip \
                build-essential \
                pkg-config \
                git
            ;;
        dnf)
            # ffmpeg may require EPEL or RPM Fusion on RHEL-derived systems
            run_as_root dnf install -y \
                ffmpeg \
                libsodium-devel \
                libffi-devel \
                opus \
                opus-devel \
                python3-devel \
                python3-pip \
                gcc \
                pkgconfig \
                git || {
                    warn "Some packages failed. Trying with EPEL..."
                    run_as_root dnf install -y epel-release || true
                    run_as_root dnf install -y ffmpeg libsodium-devel libffi-devel \
                        opus opus-devel python3-devel python3-pip gcc pkgconfig git
                }
            ;;
        pacman)
            run_as_root pacman -Sy --noconfirm --needed \
                ffmpeg \
                libsodium \
                libffi \
                opus \
                python \
                python-pip \
                base-devel \
                pkgconf \
                git
            ;;
        zypper)
            run_as_root zypper --non-interactive refresh
            run_as_root zypper --non-interactive install \
                ffmpeg \
                libsodium-devel \
                libffi-devel \
                libopus0 \
                opus-devel \
                python3-devel \
                python3-pip \
                gcc \
                pkg-config \
                git
            ;;
        apk)
            run_as_root apk update
            run_as_root apk add \
                ffmpeg \
                libsodium-dev \
                libffi-dev \
                opus-dev \
                python3-dev \
                py3-pip \
                build-base \
                pkgconfig \
                git
            ;;
    esac

    ok "System dependencies installed."
}

# --- Python version check ----------------------------------------------------
check_python() {
    if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
        error "Python 3 not found. Please install Python 3.10 or newer."
        exit 1
    fi

    local py_major py_minor
    py_major=$("$PYTHON_BIN" -c 'import sys; print(sys.version_info.major)')
    py_minor=$("$PYTHON_BIN" -c 'import sys; print(sys.version_info.minor)')

    if (( py_major < MIN_PY_MAJOR || (py_major == MIN_PY_MAJOR && py_minor < MIN_PY_MINOR) )); then
        error "Python ${MIN_PY_MAJOR}.${MIN_PY_MINOR}+ required; found ${py_major}.${py_minor}."
        exit 1
    fi
    ok "Python ${py_major}.${py_minor} detected."
}

# --- Virtual environment & pip installs --------------------------------------
setup_venv_and_pip() {
    info "Creating virtual environment in '${VENV_DIR}'..."
    "$PYTHON_BIN" -m venv "$VENV_DIR"

    # shellcheck disable=SC1091
    source "${VENV_DIR}/bin/activate"

    info "Upgrading pip, setuptools, wheel..."
    pip install --upgrade pip setuptools wheel

    # audioop-lts is required on Python 3.13+ where the stdlib audioop was removed.
    # It is harmless on older versions, so we install it unconditionally.
    info "Installing Python packages (discord.py[voice], yt-dlp, python-dotenv, audioop-lts)..."
    pip install --upgrade \
        "discord.py[voice]" \
        yt-dlp \
        python-dotenv \
        audioop-lts

    ok "Python packages installed."
}

# --- Verification ------------------------------------------------------------
verify_install() {
    info "Verifying installation..."

    # shellcheck disable=SC1091
    source "${VENV_DIR}/bin/activate"

    # FFmpeg
    if command -v ffmpeg >/dev/null 2>&1; then
        ok "FFmpeg: $(ffmpeg -version 2>/dev/null | head -n1)"
    else
        error "FFmpeg not found on PATH."
        exit 1
    fi

    # Python imports
    python - <<'PY'
import sys
try:
    import discord
    import nacl
    import yt_dlp
    import dotenv
    import audioop  # noqa: F401  (audioop-lts shim on 3.13+)
except ImportError as e:
    print(f"[ERROR] Missing import: {e}")
    sys.exit(1)

print(f"[ OK ]  discord.py {discord.__version__}")
print(f"[ OK ]  PyNaCl {nacl.__version__}")
print(f"[ OK ]  yt-dlp {yt_dlp.version.__version__}")
print("[ OK ]  python-dotenv loaded")
print("[ OK ]  audioop available")
PY

    # libsodium / libopus presence via ldconfig (best effort)
    for lib in libsodium libopus; do
        if ldconfig -p 2>/dev/null | grep -q "$lib"; then
            ok "${lib} found."
        else
            warn "${lib} not found via ldconfig (it may still be linked dynamically)."
        fi
    done
}

# --- .env scaffolding --------------------------------------------------------
maybe_create_env() {
    if [[ ! -f .env ]]; then
        warn ".env not found. Creating a template .env file."
        cat > .env <<'EOF'
# Folda Tunez environment
DISCORD_BOT_TOKEN=your_token_here
# Optional overrides:
# FFMPEG_PATH=/usr/bin/ffmpeg
# MAX_CONCURRENT_DOWNLOADS=8
# DOWNLOADS_DIR=downloads
# PLAYLISTS_DIR=playlists
EOF
        info "Edit .env and set DISCORD_BOT_TOKEN before running the bot."
    else
        ok ".env already exists; leaving it untouched."
    fi
}

# --- Main --------------------------------------------------------------------
main() {
    echo
    info "Folda Tunez v0.5.3 -- Linux dependency installer"
    echo

    detect_distro
    check_python
    install_system_deps
    setup_venv_and_pip
    verify_install
    maybe_create_env

    echo
    ok "All dependencies installed."
    echo
    info "Next steps:"
    echo "  1. Edit .env and set DISCORD_BOT_TOKEN"
    echo "  2. Activate the environment:  source ${VENV_DIR}/bin/activate"
    echo "  3. Run the bot:              python main.py"
    echo
}

main "$@"
