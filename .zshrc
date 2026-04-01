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
