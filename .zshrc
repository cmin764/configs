# Aliases
alias brew-all="brew update && brew upgrade && brew cleanup && brew doctor"

# Completions — full rebuild once a day, cached otherwise
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

# Claude Code — swap only the login per ~/Work/<org> dir, everything else
# (settings.json, plugins, hooks, skills) stays the shared ~/.claude config.
# Default is the keychain login (`claude auth login`) for everything,
# personal repos included. An org only deviates from that norm once its own
# CLAUDE_<ORG>_OAUTH_TOKEN (dashes -> underscores, uppercased) is set in
# ~/.zprofile.local (gitignored -- never put a real token in this file,
# it's a public repo). To add one: `claude setup-token`, save the result
# under that name, nothing else to edit here.
_claude_oauth_token_by_pwd() {
    case "$PWD" in
        "$HOME"/Work/*)
            local rest="${PWD#$HOME/Work/}"
            local org="${rest%%/*}"
            local varname="CLAUDE_${(U)org//-/_}_OAUTH_TOKEN"
            local token="${(P)varname}"
            [ -n "$token" ] && export CLAUDE_CODE_OAUTH_TOKEN="$token" || unset CLAUDE_CODE_OAUTH_TOKEN
            ;;
        *)
            unset CLAUDE_CODE_OAUTH_TOKEN
            ;;
    esac
}
autoload -Uz add-zsh-hook
add-zsh-hook chpwd _claude_oauth_token_by_pwd
_claude_oauth_token_by_pwd
