# Local binaries (takes priority over brew and everything else)
export PATH="$HOME/.local/bin:$PATH"

# Homebrew
if [[ -x /opt/homebrew/bin/brew ]]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
fi

# Java
export JAVA_HOME="/opt/homebrew/opt/openjdk/libexec/openjdk.jdk/Contents/Home"
export PATH="/opt/homebrew/opt/openjdk/bin:$PATH"

# Go
export PATH="$PATH:/Users/cmin/go/bin"

# pyenv
export PYENV_ROOT="$HOME/.pyenv"
[[ -d $PYENV_ROOT/bin ]] && export PATH="$PYENV_ROOT/bin:$PATH"

# Bun
export BUN_INSTALL="$HOME/.bun"
export PATH="$BUN_INSTALL/bin:$PATH"

# NVM
export NVM_DIR="$HOME/.nvm"

# JetBrains Toolbox
export PATH="$PATH:/Users/cmin/Library/Application Support/JetBrains/Toolbox/scripts"

# AI tools
export ENABLE_EXPERIMENTAL_MCP_CLI=true

# ── Tokens & secrets ─────────────────────────────────────────────
# Add API keys and tokens below. Keep this section at the bottom
# so it's easy to find and audit. Never commit these values.
# export GITHUB_TOKEN=""
# export ANTHROPIC_API_KEY=""
