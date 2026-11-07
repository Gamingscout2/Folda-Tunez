#!/usr/bin/env bash
#
# global_depnds.sh
#
# System-wide (global) dependencies for Folda Tunez v0.5.3.
#
# Installs:
#   - System packages: ffmpeg, libopus, libsodium, libffi, build tools
#   - Deno (for yt-dlp's YouTube JS challenge solver)
#   - yt-dlp config file (~/.config/yt-dlp/config) with EJS enabled
#   - Verifies libopus is loadable by discord.py (within `venv`)
#   - Checks/creates DISCORD_BOT_TOKEN in .env (prompts if missing)
#
# Uses the venv dir "venv" (no leading dot). Override with:
#   VENV_DIR=myvenv ./global_depnds.sh
#
# Safe to re-run. Run as a normal user (NOT as root) from Bot-Files/.

set -euo pipefail

# --- Configuration -----------------------------------------------------------
VENV_DIR="${VENV_DIR:-venv}"
PROJECT_DIR="${PROJECT_DIR:-$(pwd)}"
DENO_PATH_DEFAULT="$HOME/.deno/bin/deno"
YTDLP_CONFIG_DIR="$HOME/.config/yt-dlp"
YTDLP_CONFIG_FILE="$YTDLP_CONFIG_DIR/config"
# -----------------------------------------------------------------------------

# --- Logging -----------------------------------------------------------------
info()  { printf '\033[1;34m[INFO]\033[0m  %s\n' "$*"; }
warn()  { printf '\033[1;33m[WARN]\033[0m  %s\n' "$*"; }
error() { printf '\033[1;31m[ERROR]\033[0m %s\n' "$*" >&2; }
ok()    { printf '\033[1;32m[ OK ]\033[0m  %s\n' "$*"; }

# --- Root / sudo helper ------------------------------------------------------
run_as_root() {
    if [[ "$(id -u)" -eq 0 ]]; then
        "$@"
    elif command -v sudo >/dev/null 2>&1; then
        sudo "$@"
    else
        error "Root privileges required. Install sudo or run as root."
        exit 1
    fi
}

# --- Guard: don't run whole script as root ----------------------------------
guard_not_root() {
    if [[ "$(id -u)" -eq 0 ]]; then
        if [[ -n "${SUDO_USER:-}" ]]; then
            warn "You are running this script via sudo. Files like Deno and"
            warn "the yt-dlp config would go under /root, not your user home."
            warn "Recommended: exit sudo and run:  ./global_depnds.sh"
            echo
            read -r -p "Continue anyway? [y/N] " ans
            [[ "${ans,,}" == y* ]] || exit 1
        else
            warn "Running as root. \$HOME is /root - Deno and yt-dlp config"
            warn "will be installed there. Consider re-running as your user."
        fi
    fi
}

# --- Distro detection --------------------------------------------------------
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
        debian|ubuntu|raspbian|linuxmint|pop) PKG_MGR="apt" ;;
        fedora|rhel|centos|rocky|almalinux)   PKG_MGR="dnf" ;;
        arch|manjaro|endeavouros)             PKG_MGR="pacman" ;;
        opensuse*|suse)                       PKG_MGR="zypper" ;;
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

    info "Distro: $DISTRO_ID (package manager: $PKG_MGR)"
    if [[ "$PKG_MGR" == "unknown" ]]; then
        error "Unsupported distribution. Install packages manually."
        exit 1
    fi
}

# --- System packages ---------------------------------------------------------
install_system_packages() {
    info "Installing system packages (ffmpeg, libopus, libsodium, libffi, curl, git)..."
    case "$PKG_MGR" in
        apt)
            run_as_root apt-get update -qq
            run_as_root apt-get install -y \
                ffmpeg libopus0 libopus-dev \
                libsodium-dev libffi-dev \
                curl ca-certificates git unzip xz-utils \
                build-essential pkg-config
            ;;
        dnf)
            run_as_root dnf install -y \
                ffmpeg opus opus-devel \
                libsodium-devel libffi-devel \
                curl ca-certificates git unzip xz \
                gcc gcc-c++ make pkgconfig
            ;;
        pacman)
            run_as_root pacman -Sy --noconfirm --needed \
                ffmpeg opus libsodium libffi \
                curl ca-certificates git unzip xz base-devel
            ;;
        zypper)
            run_as_root zypper --non-interactive refresh
            run_as_root zypper --non-interactive install \
                ffmpeg libopus0 opus-devel \
                libsodium-devel libffi-devel \
                curl ca-certificates git unzip xz \
                gcc gcc-c++ make pkg-config
            ;;
        apk)
            run_as_root apk update
            run_as_root apk add \
                ffmpeg opus opus-dev \
                libsodium-dev libffi-dev \
                curl ca-certificates git unzip xz build-base
            ;;
    esac
    ok "System packages installed."
}

# --- libopus presence --------------------------------------------------------
verify_libopus() {
    info "Verifying libopus..."
    if ldconfig -p 2>/dev/null | grep -q "libopus.so"; then
        ok "libopus visible in ldconfig cache."
    else
        warn "libopus not in ldconfig - will retry via python check."
    fi
}

# --- Deno --------------------------------------------------------------------
install_deno() {
    info "Checking Deno..."
    if [[ -x "$DENO_PATH_DEFAULT" ]]; then
        ok "Deno at $DENO_PATH_DEFAULT ($("$DENO_PATH_DEFAULT" --version 2>/dev/null | head -n1))"
        DENO_PATH="$DENO_PATH_DEFAULT"
        return
    fi
    if command -v deno >/dev/null 2>&1; then
        DENO_PATH="$(command -v deno)"
        ok "Deno on PATH at $DENO_PATH ($("$DENO_PATH" --version 2>/dev/null | head -n1))"
        return
    fi

    info "Installing Deno via official installer..."
    curl -fsSL https://deno.land/install.sh | sh
    if [[ -x "$DENO_PATH_DEFAULT" ]]; then
        DENO_PATH="$DENO_PATH_DEFAULT"
        ok "Deno installed at $DENO_PATH"
    else
        error "Deno installer ran but binary not found at $DENO_PATH_DEFAULT"
        exit 1
    fi
}

# --- yt-dlp config -----------------------------------------------------------
setup_ytdlp_config() {
    info "Writing yt-dlp config (Deno + EJS remote components)..."
    mkdir -p "$YTDLP_CONFIG_DIR"

    if [[ -f "$YTDLP_CONFIG_FILE" ]]; then
        cp "$YTDLP_CONFIG_FILE" "$YTDLP_CONFIG_FILE.bak"
        info "Backed up existing config to $YTDLP_CONFIG_FILE.bak"
    fi

    cat > "$YTDLP_CONFIG_FILE" <<EOF
# Managed by Folda Tunez global_depnds.sh
--js-runtimes deno:$DENO_PATH
--remote-components ejs:github
EOF

    ok "Wrote $YTDLP_CONFIG_FILE"
    if ! command -v deno >/dev/null 2>&1; then
        warn "Deno is not on \$PATH. yt-dlp still works (config uses full path),"
        warn "but for convenience add this to ~/.bashrc:"
        warn "  export PATH=\"\$HOME/.deno/bin:\$PATH\""
    fi
}

# --- Venv package check ------------------------------------------------------
verify_venv_packages() {
    local py="$PROJECT_DIR/$VENV_DIR/bin/python3.14"
    [[ ! -x "$py" ]] && py="$PROJECT_DIR/$VENV_DIR/bin/python3"
    if [[ ! -x "$py" ]]; then
        warn "Venv '$PROJECT_DIR/$VENV_DIR' not found - skipping package check."
        warn "Run install_requirements.sh first if you haven't."
        return
    fi

    info "Checking Python packages in $VENV_DIR..."
    if "$py" - <<'PY'
import sys
mods = {"discord": "discord.py", "yt_dlp": "yt-dlp", "dotenv": "python-dotenv",
        "audioop": "audioop-lts", "nacl": "PyNaCl"}
missing = []
for m, pkg in mods.items():
    try: __import__(m)
    except ImportError: missing.append(pkg)
if missing:
    print("MISSING:" + ",".join(missing))
    sys.exit(1)
PY
    then
        ok "All venv packages present."
    else
        warn "Some packages missing. Run:"
        warn "  source $VENV_DIR/bin/activate && pip install -U 'discord.py[voice]' yt-dlp python-dotenv audioop-lts"
    fi
}

# --- libopus / discord.opus check (inside venv) ------------------------------
verify_discord_opus() {
    local py="$PROJECT_DIR/$VENV_DIR/bin/python3.14"
    [[ ! -x "$py" ]] && py="$PROJECT_DIR/$VENV_DIR/bin/python3"
    if [[ ! -x "$py" ]]; then
        warn "Venv not found - skipping discord.opus check."
        return
    fi

    info "Checking discord.opus.is_loaded() in $VENV_DIR..."
    local result
    result="$("$py" - <<'PY' 2>&1 || true
try:
    import discord
    print("LOADED" if discord.opus.is_loaded() else "NOT_LOADED")
except Exception as e:
    print(f"ERROR:{e}")
PY
)"

    case "$result" in
        LOADED)
            ok "discord.opus is loaded - voice playback should work." ;;
        NOT_LOADED)
            warn "discord.opus is NOT loaded - bot will join but stay silent."
            echo
            warn "Fix: add this near the TOP of main.py (after 'import discord'):"
            warn "    if not discord.opus.is_loaded():"
            warn "        discord.opus.load_opus('libopus.so.0')"
            echo
            warn "Then restart the bot." ;;
        ERROR:*)
            warn "Could not run discord.opus check: ${result#ERROR:}" ;;
        *)
            warn "Unexpected check output: $result" ;;
    esac
}

# --- Discord token check / prompt --------------------------------------------
validate_token() {
    local t="$1"
    [[ -z "$t" ]] && return 1
    # 3 dot-separated parts, each non-empty, total length sane
    local parts
    parts="$(awk -F. '{print NF}' <<<"$t")"
    [[ "$parts" -eq 3 ]] || return 1
    [[ "${#t}" -ge 50 ]] || return 1
    return 0
}

ensure_discord_token() {
    local env_file="$PROJECT_DIR/.env"
    local token=""

    if [[ -f "$env_file" ]]; then
        token="$(grep -E '^DISCORD_BOT_TOKEN=' "$env_file" 2>/dev/null \
                 | tail -n1 | cut -d= -f2-)"
        # trim whitespace and quotes
        token="${token//[$'\t\r\n ']/}"
        token="${token//\"/}"
        token="${token//\'/}"
    fi

    # reject obvious placeholders
    if [[ "$token" == "your_token_here" ]] || ! validate_token "$token"; then
        token=""
    fi

    if [[ -n "$token" ]]; then
        ok "Discord token found in $env_file"
        return
    fi

    warn "No valid Discord token in $env_file."
    info "Get one: https://discord.com/developers/applications -> your app -> Bot -> Reset Token"
    echo

    if [[ ! -t 0 ]]; then
        error "No interactive terminal - cannot prompt for token."
        error "Create $env_file manually with: DISCORD_BOT_TOKEN=<token>"
        exit 1
    fi

    local input=""
    while true; do
        read -r -s -p "Paste Discord bot token: " input
        echo
        input="${input//[$'\t\r\n ']/}"
        input="${input//\"/}"
        input="${input//\'/}"

        if validate_token "$input"; then
            token="$input"
            break
        fi
        warn "That doesn't look like a valid Discord bot token (expected 3 dot-separated parts, 50+ chars). Try again."
    done

    if [[ -f "$env_file" ]]; then
        local tmp
        tmp="$(mktemp)"
        grep -v '^DISCORD_BOT_TOKEN=' "$env_file" > "$tmp" || true
        printf 'DISCORD_BOT_TOKEN=%s\n' "$token" >> "$tmp"
        mv "$tmp" "$env_file"
    else
        umask 077
        {
            echo "# Folda Tunez environment"
            printf 'DISCORD_BOT_TOKEN=%s\n' "$token"
        } > "$env_file"
    fi
    chmod 600 "$env_file"
    ok "Token written to $env_file (permissions 600)"
}

# --- Main --------------------------------------------------------------------
main() {
    echo
    info "Folda Tunez global dependency setup"
    info "Project dir: $PROJECT_DIR"
    info "Venv dir:    $VENV_DIR"
    echo

    guard_not_root
    detect_distro
    install_system_packages
    verify_libopus
    install_deno
    setup_ytdlp_config
    verify_venv_packages
    verify_discord_opus
    ensure_discord_token

    echo
    ok "Global setup complete."
    echo
    info "Next:"
    echo "  source $VENV_DIR/bin/activate"
    echo "  python3.14 main.py"
    echo
    warn "After starting the bot, run '!stop' to clear any broken downloads"
    warn "from before the yt-dlp fix, then '!stream <url>' to re-download."
    echo
}

main "$@"
