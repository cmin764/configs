#!/usr/bin/env bash
# Wraps ponytail's own statusline, then appends RTK and claude-mem badges,
# checked against real state (rtk's own validator, the worker's /health
# endpoint) rather than just config flags -- a flag can say "on" while the
# hook, RTK.md import, or worker process is actually broken.
set -uo pipefail

ponytail_script=$(ls -d "$HOME"/.claude/plugins/cache/ponytail/ponytail/*/hooks/ponytail-statusline.sh 2>/dev/null | sort -V | tail -1)
[ -n "$ponytail_script" ] && bash "$ponytail_script"

rtk_ok_count=$(command -v rtk >/dev/null 2>&1 && rtk init --show 2>/dev/null | grep -cE '^\[ok\] (Hook|settings\.json):')
if ! command -v rtk >/dev/null 2>&1; then
    printf ' \033[38;5;196m[RTK:MISSING]\033[0m'
elif [ "${rtk_ok_count:-0}" -lt 2 ] || ! grep -q '@~/.claude/RTK.md' "$HOME/.claude/CLAUDE.md" 2>/dev/null; then
    printf ' \033[38;5;196m[RTK:NO-HOOK]\033[0m'
else
    printf ' \033[38;5;108m[RTK]\033[0m'
fi

if ! grep -q '"claude-mem@thedotmack": true' "$HOME/.claude/settings.json" 2>/dev/null; then
    printf ' \033[38;5;240m[MEM:OFF]\033[0m'
elif ! curl -s -m 1 http://localhost:37701/health 2>/dev/null | grep -q '"status":"ok"'; then
    printf ' \033[38;5;196m[MEM:DOWN]\033[0m'
else
    printf ' \033[38;5;108m[MEM]\033[0m'
fi
