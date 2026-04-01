# Local binaries (takes priority over brew and everything else)
export PATH="$HOME/.local/bin:$PATH"

# Homebrew
if [[ -x /opt/homebrew/bin/brew ]]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
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
# Add API keys and tokens below. Keep this section at the bottom
# so it's easy to find and audit. Never commit these values.
# export GITHUB_TOKEN=""
# export ANTHROPIC_API_KEY=""
