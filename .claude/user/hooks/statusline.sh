#!/usr/bin/env bash
# Wraps ponytail's own statusline, then appends RTK and claude-mem badges,
# checked against real state (rtk's own validator, the worker's /health
# endpoint) rather than just config flags -- a flag can say "on" while the
# hook, RTK.md import, or worker process is actually broken.
set -uo pipefail

input=$(cat)
config_dir="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"

# Model family, effort and context use come from the JSON Claude Code feeds the
# statusline on stdin; the family is parsed out of the ID so a version bump
# needs no edit. Context is green up to ~20% (the sweet spot), then yellow,
# amber from 50% and red from 80%, so degrading quality shows before it bites.
model_id=$(jq -r '.model.id // empty' <<<"$input" 2>/dev/null)
effort=$(jq -r '.effort.level // empty' <<<"$input" 2>/dev/null)
ctx=$(jq -r '.context_window.used_percentage // empty | floor' <<<"$input" 2>/dev/null)
family=$(sed -E 's/^claude-([a-z]+)-.*/\1/' <<<"$model_id")
head_out=""
if [ -n "$family" ] && [ "$family" != "$model_id" ]; then
    family="$(tr '[:lower:]' '[:upper:]' <<<"${family:0:1}")${family:1}"
    head_out=$(printf '\033[38;5;75m%s%s\033[0m' "$family" "${effort:+ ($effort)}")
fi
if [ -n "$ctx" ]; then
    if [ "$ctx" -ge 80 ]; then ctx_color=196
    elif [ "$ctx" -ge 50 ]; then ctx_color=208
    elif [ "$ctx" -gt 20 ]; then ctx_color=220
    else ctx_color=108; fi
    head_out+=$(printf '%s\033[38;5;%sm%s%%\033[0m' "${head_out:+ }" "$ctx_color" "$ctx")
fi
[ -n "$head_out" ] && printf '%s \033[38;5;240m·\033[0m ' "$head_out"

ponytail_script=$(ls -d "$config_dir"/plugins/cache/ponytail/ponytail/*/hooks/ponytail-statusline.sh 2>/dev/null | sort -V | tail -1)
[ -n "$ponytail_script" ] && bash "$ponytail_script" <<<"$input"

rtk_ok_count=$(command -v rtk >/dev/null 2>&1 && rtk init --show 2>/dev/null | grep -cE '^\[ok\] (Hook|settings\.json):')
if ! command -v rtk >/dev/null 2>&1; then
    printf ' \033[38;5;196m[RTK:MISSING]\033[0m'
elif [ "${rtk_ok_count:-0}" -lt 2 ] || ! grep -q '@~/.claude/RTK.md' "$config_dir/CLAUDE.md" "$config_dir/CLAUDE.base.md" 2>/dev/null; then
    printf ' \033[38;5;196m[RTK:NO-HOOK]\033[0m'
else
    printf ' \033[38;5;108m[RTK]\033[0m'
fi

mem_config_dir="$config_dir"
mem_data_dir="${CLAUDE_MEM_DATA_DIR:-$HOME/.claude-mem}"
mem_port=$(grep -o '"port":[[:space:]]*[0-9]*' "$mem_data_dir/worker.pid" 2>/dev/null | grep -o '[0-9]*')

if ! grep -q '"claude-mem@thedotmack": true' "$mem_config_dir/settings.json" 2>/dev/null; then
    printf ' \033[38;5;240m[MEM:OFF]\033[0m'
elif [ -z "$mem_port" ] || ! curl -s -m 1 "http://localhost:$mem_port/health" 2>/dev/null | grep -q '"status":"ok"'; then
    printf ' \033[38;5;196m[MEM:DOWN]\033[0m'
else
    printf ' \033[38;5;108m[MEM]\033[0m'
fi

# Where the session is now, and where it started when it has wandered off
# (a cd, a worktree), so a stray edit location shows before it bites.
cur_dir=$(jq -r '.workspace.current_dir // .cwd // empty' <<<"$input" 2>/dev/null)
start_dir=$(jq -r '.workspace.project_dir // empty' <<<"$input" 2>/dev/null)
if [ -n "$cur_dir" ]; then
    dir_out="${cur_dir/#$HOME/\~}"
    [ -n "$start_dir" ] && [ "$start_dir" != "$cur_dir" ] && dir_out+=" (from ${start_dir/#$HOME/\~})"
    printf ' \033[38;5;240m·\033[0m \033[38;5;245m%s\033[0m' "$dir_out"
fi
