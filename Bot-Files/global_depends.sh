#!/usr/bin/env bash
#
# global_depends.sh
#
# System-wide (global) dependencies for Folda Tunez. Run this OUTSIDE the
# virtual environment, as a normal user with sudo rights. Run it first, then
# run dependencies.sh for the Python packages.
#
# Installs / checks:
#   - System packages: ffmpeg (with libopus encoder), libopus, libsodium,
#     libffi, Python venv/dev headers, build tools
#   - Deno (for yt-dlp's YouTube JS challenge solver)
#   - yt-dlp CLI config (~/.config/yt-dlp/config) with Deno + EJS enabled
#   - DISCORD_BOT_TOKEN in .env (prompts if missing and a terminal exists)
#
# Safe to re-run.
#
# Usage: chmod +x global_depends.sh && ./global_depends.sh

set -euo pipefail

# --- Configuration -----------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${PROJECT_DIR:-$SCRIPT_DIR}"
DENO_PATH_DEFAULT="$HOME/.deno/bin/deno"
YTDLP_CONFIG_DIR="$HOME/.config/yt-dlp"
YTDLP_CONFIG_FILE="$YTDLP_CONFIG_DIR/config"
# -----------------------------------------------------------------------------

# --- Logging -----------------------------------------------------------------
info()  { printf '\033[1;34m[INFO]\033[0m  %s\n' "$*"; }
warn()  { printf '\033[1;33m[WARN]\033[0m  %s\n' "$*"; }
error() { printf '\033[1;31m[ERROR]\033[0m %s\n' "$*" >&2; }
ok()    { printf '\033[1;32m[ OK ]\033[0m  %s\n' "$*"; }

# --- Guards ------------------------------------------------------------------
guard_not_in_venv() {
    if [[ -n "${VIRTUAL_ENV:-}" ]]; then
        error "A virtualenv is active (${VIRTUAL_ENV})."
        error "global_depends.sh must run outside the venv. Run 'deactivate' and retry."
        exit 1
    fi
}

guard_not_root() {
    if [[ "$(id -u)" -eq 0 ]]; then
        if [[ -n "${SUDO_USER:-}" ]]; then
            warn "Running via sudo: Deno and the yt-dlp config would land in /root."
            warn "Recommended: exit sudo and run ./global_depends.sh as your own user."
            if [[ -t 0 ]]; then
                read -r -p "Continue anyway? [y/N] " ans
                [[ "${ans,,}" == y* ]] || exit 1
            else
                error "Refusing to continue as root without a terminal."
                exit 1
            fi
        else
            warn "Running as root. \$HOME is ${HOME}; Deno and yt-dlp config go there."
        fi
    fi
}

run_as_root() {
    if [[ "$(id -u)" -eq 0 ]]; then
        "$@"
    elif command -v sudo >/dev/null 2>&1; then
        sudo "$@"
    else
        error "Root privileges required for: $*"
        error "Install sudo or run as root."
        exit 1
    fi
}

# --- Distro detection --------------------------------------------------------
detect_distro() {
    local DISTRO_ID="unknown" DISTRO_LIKE=""
    if [[ -f /etc/os-release ]]; then
        # shellcheck disable=SC1091
        . /etc/os-release
        DISTRO_ID="${ID:-unknown}"
        DISTRO_LIKE="${ID_LIKE:-}"
    fi

    case "$DISTRO_ID" in
        debian|ubuntu|raspbian|linuxmint|pop) PKG_MGR="apt" ;;
        fedora|rhel|centos|rocky|almalinux)   PKG_MGR="dnf" ;;
        arch|manjaro|endeavouros)             PKG_MGR="pacman" ;;
        opensuse*|suse|sles)                  PKG_MGR="zypper" ;;
        alpine)                               PKG_MGR="apk" ;;
        *)
            case "$DISTRO_LIKE" in
                *debian*|*ubuntu*) PKG_MGR="apt" ;;
                *fedora*|*rhel*)   PKG_MGR="dnf" ;;
                *arch*)            PKG_MGR="pacman" ;;
                *suse*)            PKG_MGR="zypper" ;;
                *)                 PKG_MGR="unknown" ;;
            esac ;;
    esac

    info "Distro: ${DISTRO_ID} (package manager: ${PKG_MGR})"
    if [[ "$PKG_MGR" == "unknown" ]]; then
        error "Unsupported distribution. Install these manually: ffmpeg (with libopus),"
        error "libopus, libsodium, libffi, python3 + venv + dev headers, curl, git, unzip."
        exit 1
    fi
}

# --- System packages ---------------------------------------------------------
install_system_packages() {
    info "Installing system packages..."
    case "$PKG_MGR" in
        apt)
            run_as_root apt-get update -qq
            run_as_root apt-get install -y \
                ffmpeg libopus0 libopus-dev \
                libsodium-dev libffi-dev \
                python3 python3-dev python3-venv python3-pip \
                curl ca-certificates git unzip xz-utils \
                build-essential pkg-config
            ;;
        dnf)
            run_as_root dnf install -y \
                opus opus-devel \
                libsodium-devel libffi-devel \
                python3 python3-devel python3-pip \
                curl ca-certificates git unzip xz \
                gcc gcc-c++ make pkgconfig
            # ffmpeg lives in RPM Fusion on RHEL-likes; Fedora ships ffmpeg-free
            if ! command -v ffmpeg >/dev/null 2>&1; then
                run_as_root dnf install -y ffmpeg \
                    || run_as_root dnf install -y ffmpeg-free \
                    || warn "Could not install ffmpeg. Enable RPM Fusion/EPEL and install it manually."
            fi
            ;;
        pacman)
            run_as_root pacman -Sy --noconfirm --needed \
                ffmpeg opus libsodium libffi \
                python python-pip \
                curl ca-certificates git unzip xz base-devel pkgconf
            ;;
        zypper)
            run_as_root zypper --non-interactive refresh
            run_as_root zypper --non-interactive install \
                ffmpeg libopus0 opus-devel \
                libsodium-devel libffi-devel \
                python3 python3-devel python3-pip \
                curl ca-certificates git unzip xz \
                gcc gcc-c++ make pkg-config
            ;;
        apk)
            run_as_root apk update
            run_as_root apk add \
                ffmpeg opus opus-dev \
                libsodium-dev libffi-dev \
                python3 python3-dev py3-pip \
                curl ca-certificates git unzip xz build-base
            ;;
    esac
    ok "System packages installed."
}

# --- ffmpeg / libopus verification ------------------------------------------
verify_ffmpeg() {
    info "Verifying ffmpeg..."
    if ! command -v ffmpeg >/dev/null 2>&1; then
        error "ffmpeg is not on PATH after installation."
        exit 1
    fi
    ok "ffmpeg: $(ffmpeg -version 2>/dev/null | head -n1)"

    # the bot encodes with libopus; a build without it plays silence
    local encoders
    encoders="$(ffmpeg -hide_banner -encoders 2>/dev/null || true)"
    if grep -q libopus <<<"$encoders"; then
        ok "ffmpeg has the libopus encoder."
    else
        error "This ffmpeg build has no libopus encoder - the bot would be silent."
        error "Install a full ffmpeg build (e.g. a static build from johnvansickle.com)"
        error "and set FFMPEG_PATH in .env if it is not first on PATH."
        exit 1
    fi
}

verify_libopus() {
    info "Verifying libopus shared library..."
    local found=""
    if ldconfig -p 2>/dev/null | grep -q "libopus\.so"; then
        found="ldconfig cache"
    elif command -v python3 >/dev/null 2>&1 \
         && python3 -c 'import ctypes.util,sys; sys.exit(0 if ctypes.util.find_library("opus") else 1)' 2>/dev/null; then
        found="python ctypes.util"
    else
        # musl / minimal systems have no ldconfig; glob the usual locations
        local f
        for f in /usr/lib/libopus.so* /usr/lib64/libopus.so* /lib/libopus.so* \
                 /usr/lib/*-linux-gnu/libopus.so* /usr/local/lib/libopus.so*; do
            if [[ -e "$f" ]]; then found="$f"; break; fi
        done
    fi

    if [[ -n "$found" ]]; then
        ok "libopus found (${found})."
    else
        warn "libopus not found by the system loader. The bot's main.py searches several"
        warn "paths at startup, but if voice is silent check: ldconfig -p | grep opus"
    fi
}

# --- Deno --------------------------------------------------------------------
install_deno() {
    info "Checking Deno..."
    if command -v deno >/dev/null 2>&1; then
        DENO_PATH="$(command -v deno)"
    elif [[ -x "$DENO_PATH_DEFAULT" ]]; then
        DENO_PATH="$DENO_PATH_DEFAULT"
    else
        info "Installing Deno via the official installer..."
        if ! curl -fsSL https://deno.land/install.sh | sh; then
            warn "Deno install failed. yt-dlp may be unable to solve YouTube JS challenges."
            warn "Install it manually: https://docs.deno.com/runtime/getting_started/installation/"
            DENO_PATH=""
            return
        fi
        DENO_PATH="$DENO_PATH_DEFAULT"
    fi

    if [[ -x "$DENO_PATH" ]]; then
        ok "Deno at ${DENO_PATH} ($("$DENO_PATH" --version 2>/dev/null | head -n1))"
    else
        warn "Deno binary not found at ${DENO_PATH}."
        DENO_PATH=""
    fi
}

# --- yt-dlp config (CLI only; the bot also passes these via its API options) --
setup_ytdlp_config() {
    if [[ -z "${DENO_PATH:-}" ]]; then
        warn "No Deno available - skipping yt-dlp config."
        return
    fi

    info "Writing yt-dlp config (Deno + EJS remote components)..."
    mkdir -p "$YTDLP_CONFIG_DIR"

    if [[ -f "$YTDLP_CONFIG_FILE" ]] && ! grep -q "Managed by Folda Tunez" "$YTDLP_CONFIG_FILE"; then
        cp "$YTDLP_CONFIG_FILE" "$YTDLP_CONFIG_FILE.bak"
        info "Backed up existing config to ${YTDLP_CONFIG_FILE}.bak"
    fi

    cat > "$YTDLP_CONFIG_FILE" <<EOF
# Managed by Folda Tunez global_depends.sh
--js-runtimes deno:${DENO_PATH}
--remote-components ejs:github
EOF
    ok "Wrote ${YTDLP_CONFIG_FILE}"

    if ! command -v deno >/dev/null 2>&1; then
        warn "Deno is not on \$PATH. The bot finds it at ~/.deno/bin/deno anyway, but for"
        warn "convenience add to ~/.bashrc:  export PATH=\"\$HOME/.deno/bin:\$PATH\""
    fi
}

# --- Discord token check / prompt --------------------------------------------
validate_token() {
    local t="$1"
    [[ -n "$t" ]] || return 1
    # 3 dot-separated parts, sane length
    [[ "$(awk -F. '{print NF}' <<<"$t")" -eq 3 ]] || return 1
    [[ "${#t}" -ge 50 ]] || return 1
}

clean_token() {
    local t="$1"
    t="${t//[$'\t\r\n ']/}"
    t="${t//\"/}"
    t="${t//\'/}"
    printf '%s' "$t"
}

ensure_discord_token() {
    local env_file="$PROJECT_DIR/.env"
    local token=""

    if [[ -f "$env_file" ]]; then
        token="$(grep -E '^DISCORD_BOT_TOKEN=' "$env_file" 2>/dev/null | tail -n1 | cut -d= -f2- || true)"
        token="$(clean_token "$token")"
    fi

    if validate_token "$token"; then
        ok "Discord token found in ${env_file} (length ${#token})"
        return
    fi

    warn "No valid Discord token in ${env_file}."
    info "Get one: https://discord.com/developers/applications -> your app -> Bot -> Reset Token"

    if [[ ! -t 0 ]]; then
        warn "No interactive terminal - cannot prompt. Add this line to ${env_file} manually:"
        warn "  DISCORD_BOT_TOKEN=<token>"
        return
    fi

    local input=""
    while true; do
        read -r -s -p "Paste Discord bot token (blank to skip): " input
        echo
        input="$(clean_token "$input")"
        if [[ -z "$input" ]]; then
            warn "Skipped. Add DISCORD_BOT_TOKEN to ${env_file} before starting the bot."
            return
        fi
        if validate_token "$input"; then
            token="$input"
            break
        fi
        warn "Not a valid bot token (expected 3 dot-separated parts, 50+ chars). Try again."
    done

    # never clobber other keys in an existing .env
    local tmp
    tmp="$(mktemp)"
    if [[ -f "$env_file" ]]; then
        grep -v '^DISCORD_BOT_TOKEN=' "$env_file" > "$tmp" || true
    else
        echo "# Folda Tunez environment" > "$tmp"
    fi
    printf 'DISCORD_BOT_TOKEN=%s\n' "$token" >> "$tmp"
    mv "$tmp" "$env_file"
    chmod 600 "$env_file"
    ok "Token written to ${env_file} (permissions 600)"
}

# --- Main --------------------------------------------------------------------
main() {
    echo
    info "Folda Tunez global dependency setup"
    info "Project dir: ${PROJECT_DIR}"
    echo

    guard_not_in_venv
    guard_not_root
    detect_distro
    install_system_packages
    verify_ffmpeg
    verify_libopus
    install_deno
    setup_ytdlp_config
    ensure_discord_token

    echo
    ok "Global setup complete."
    echo
    info "Next: install the Python packages (creates/uses a venv automatically):"
    echo "  ./dependencies.sh"
    echo
}

main "$@"
