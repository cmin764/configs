# Aliases
alias brew-all="brew update && brew upgrade && brew cleanup && brew doctor"

# Line editing: Fn+Left/Right (Home/End) and Option+Left/Right (word jump).
# zsh's emacs keymap doesn't bind these out of the box -- iTerm2 sends the
# terminfo Home/End sequence for Fn+arrows (application-keypad \eOH/\eOF on
# this TERM, xterm-256color) and xterm's CSI modifier-arrow form for
# Option+arrows (\e[1;3D / \e[1;3C, modifier code 3 = Option), neither of
# which zsh's stock bindings recognize on their own.
bindkey "${terminfo[khome]:-\eOH}" beginning-of-line
bindkey "${terminfo[kend]:-\eOF}" end-of-line
bindkey "\e[H" beginning-of-line   # normal (non-application) cursor mode fallback
bindkey "\e[F" end-of-line
bindkey "\e[1;3D" backward-word    # Option+Left
bindkey "\e[1;3C" forward-word     # Option+Right

# Completions — full rebuild once a day, cached otherwise
[[ -d "$HOME/.docker/completions" ]] && fpath=("$HOME/.docker/completions" $fpath)
autoload -Uz compinit
if [[ -n ${ZDOTDIR:-$HOME}/.zcompdump(#qN.mh+24) ]]; then
    compinit
else
    compinit -C
fi
(( $+commands[register-python-argcomplete] )) && eval "$(register-python-argcomplete pipx)"
[ -s "$HOME/.bun/_bun" ] && source "$HOME/.bun/_bun"

# pyenv shell integration
(( $+commands[pyenv] )) && eval "$(pyenv init - zsh)"

# NVM
if (( $+commands[brew] )); then
    _nvm_prefix="$(brew --prefix nvm 2>/dev/null)"
    if [[ -n "$_nvm_prefix" && -s "$_nvm_prefix/nvm.sh" ]]; then
        source "$_nvm_prefix/nvm.sh"
        [[ -s "$_nvm_prefix/etc/bash_completion.d/nvm" ]] && source "$_nvm_prefix/etc/bash_completion.d/nvm"
    fi
    unset _nvm_prefix
fi

# Claude Code — disable auto-update; run `claude update` manually to upgrade
export DISABLE_AUTOUPDATER=1

# Claude Code — swap the whole config dir (and with it, the Keychain-backed
# login) per ~/Work/<org> dir. Falls back to the default ~/.claude login when
# no ~/.claude-<org> profile exists yet -- nothing to set up for personal
# repos or orgs that don't need a separate account.
# To add one: `mkdir -p ~/.claude-<org>`, then
# `CLAUDE_CONFIG_DIR=~/.claude-<org> claude auth login` (real browser OAuth,
# full feature access), then `sync.py --push` to link in shared skills/hooks.
_claude_config_dir_by_pwd() {
    case "$PWD" in
        "$HOME"/Work/*)
            local rest="${PWD#$HOME/Work/}"
            local org="${rest%%/*}"
            local dir="$HOME/.claude-${(L)org}"
            [ -d "$dir" ] && export CLAUDE_CONFIG_DIR="$dir" || unset CLAUDE_CONFIG_DIR
            ;;
        *)
            unset CLAUDE_CONFIG_DIR
            ;;
    esac
}
autoload -Uz add-zsh-hook
add-zsh-hook chpwd _claude_config_dir_by_pwd
_claude_config_dir_by_pwd
