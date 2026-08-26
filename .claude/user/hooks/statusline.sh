#!/usr/bin/env bash
# Wraps ponytail's own statusline, then appends RTK and claude-mem badges:
# green when on/wired up, red when RTK is broken, dim when claude-mem is off.
set -uo pipefail

ponytail_script=$(ls -d "$HOME"/.claude/plugins/cache/ponytail/ponytail/*/hooks/ponytail-statusline.sh 2>/dev/null | sort -V | tail -1)
[ -n "$ponytail_script" ] && bash "$ponytail_script"

if ! command -v rtk >/dev/null 2>&1; then
    printf ' \033[38;5;196m[RTK:MISSING]\033[0m'
elif ! grep -q '"rtk hook claude"' "$HOME/.claude/settings.json" 2>/dev/null; then
    printf ' \033[38;5;196m[RTK:NO-HOOK]\033[0m'
else
    printf ' \033[38;5;108m[RTK]\033[0m'
fi

if grep -q '"claude-mem@thedotmack": true' "$HOME/.claude/settings.json" 2>/dev/null; then
    printf ' \033[38;5;108m[MEM]\033[0m'
else
    printf ' \033[38;5;240m[MEM:OFF]\033[0m'
fi
