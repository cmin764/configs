#!/usr/bin/env bash
# Wraps ponytail's own statusline, then appends an RTK badge: green when
# the hook is wired up, red when the binary or the hook entry is missing.
set -uo pipefail

bash "$HOME/.claude/plugins/cache/ponytail/ponytail/4.8.4/hooks/ponytail-statusline.sh"

if ! command -v rtk >/dev/null 2>&1; then
    printf ' \033[38;5;196m[RTK:MISSING]\033[0m'
elif ! grep -q '"rtk hook claude"' "$HOME/.claude/settings.json" 2>/dev/null; then
    printf ' \033[38;5;196m[RTK:NO-HOOK]\033[0m'
else
    printf ' \033[38;5;108m[RTK]\033[0m'
fi
