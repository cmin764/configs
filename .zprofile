# Local binaries.
# ~/.local/bin exported last so it wins over /usr/local/sbin on name clashes
# (Homebrew's shellenv below still prepends ahead of both).
export PATH="/usr/local/sbin:$PATH"
export PATH="$HOME/.local/bin:$PATH"

# Homebrew (Apple Silicon /opt/homebrew or Intel /usr/local, whichever exists)
if [[ -x /opt/homebrew/bin/brew ]]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
elif [[ -x /usr/local/bin/brew ]]; then
    eval "$(/usr/local/bin/brew shellenv)"
fi

# Java
_java_prefix="$(brew --prefix openjdk 2>/dev/null)"
if [[ -n "$_java_prefix" ]]; then
    export JAVA_HOME="$_java_prefix/libexec/openjdk.jdk/Contents/Home"
    export PATH="$_java_prefix/bin:$PATH"
fi
unset _java_prefix

# Go
export PATH="$PATH:$HOME/go/bin"

# pyenv
export PYENV_ROOT="$HOME/.pyenv"
[[ -d $PYENV_ROOT/bin ]] && export PATH="$PYENV_ROOT/bin:$PATH"

# Bun
export BUN_INSTALL="$HOME/.bun"
export PATH="$BUN_INSTALL/bin:$PATH"

# NVM
export NVM_DIR="$HOME/.nvm"

# JetBrains Toolbox
path+=("$HOME/Library/Application Support/JetBrains/Toolbox/scripts")

# AI tools
export ENABLE_EXPERIMENTAL_MCP_CLI=true

# ── Tokens & secrets ─────────────────────────────────────────────
# Real values live in ~/.zprofile.local (chmod 600, never committed).
# Fill these in on a new machine:
#   export GITHUB_TOKEN=""        # gh CLI + Cursor github MCP
#   export OPENAI_API_KEY=""      # Change Agents
#   export GEMINI_API_KEY=""
#   export GOOGLE_MAPS_API_KEY=""
#   export TALLY_API_KEY=""
#   export CAL_API_KEY=""
# ponytail: a plaintext file is the floor. Move to `op run` / 1Password
# CLI if these ever get shared or start rotating on a schedule.
[ -f "$HOME/.zprofile.local" ] && source "$HOME/.zprofile.local"
