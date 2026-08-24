#!/usr/bin/env python3
"""Deterministic PR checks for the configs repo.

Everything here is a mechanical pattern match: secret-shaped strings, files
that don't parse, hardcoded absolute home paths, single-arch assumptions,
and junk file patterns. Judging whether a file is genuinely hand-edited
config versus accumulated tool noise is NOT here -- that's a human call made
via config-sync's --pull, on purpose (see AGENTS.md). Keeping that judgment
out of CI is deliberate, not an oversight.

Exit code is 1 if there are any findings, 0 if clean, so CI fails loudly.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SELF = Path(__file__).resolve()

SECRET_PATTERNS = [
    (r"gh[pousr]_[A-Za-z0-9]{20,}", "GitHub token"),
    (r"sk-proj-[A-Za-z0-9_-]{20,}", "OpenAI project key"),
    (r"sk-ant-[A-Za-z0-9_-]{20,}", "Anthropic key"),
    (r"AIza[0-9A-Za-z_-]{35}", "Google API key"),
    (r"AKIA[0-9A-Z]{16}", "AWS access key"),
    (r"xox[baprs]-[0-9A-Za-z-]{10,}", "Slack token"),
    (r"tly-[A-Za-z0-9]{10,}", "Tally API key"),
    (r"cal_(live|test)_[A-Za-z0-9]{10,}", "Cal.com API key"),
    (r"-----BEGIN (RSA |EC |OPENSSH |)PRIVATE KEY-----", "private key"),
    (r"""(?i)(api[_-]?key|secret|password|access[_-]?token)\s*[:=]\s*["'][A-Za-z0-9_\-/+]{16,}["']""",
     "inline credential-shaped assignment"),
]

JUNK_NAMES = re.compile(
    r"(^|/)(\.DS_Store|__pycache__|.*\.pyc|.*\.bak|.*\.log|node_modules|"
    r"\.env(\..+)?|.*\.pid|Thumbs\.db|.*[_-]cache.*)$"
)

SHELL_FILENAMES = {".zprofile", ".zshrc"}  # shell dotfiles: no ".sh" suffix to key off


def is_shell_file(path):
    return path.suffix == ".sh" or path.name in SHELL_FILENAMES


def is_reference_asset(rel):
    return "reference/" in rel  # curated binary assets belong here (exempts check_binary only)


def tracked_files():
    # --others --exclude-standard: also catch a new file with a real secret
    # before it's ever `git add`ed, since AGENTS.md's own workflow expects
    # this to be run by hand ahead of a commit, not just by CI post-checkout.
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    return [REPO_ROOT / p for p in out.stdout.splitlines() if p]


def read_text(path):
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None


def check_secrets(files, findings):
    for path in files:
        if path == SELF:
            continue
        text = read_text(path)
        if text is None:
            continue
        for pattern, label in SECRET_PATTERNS:
            for m in re.finditer(pattern, text):
                line = text.count("\n", 0, m.start()) + 1
                findings.append(f"{path.relative_to(REPO_ROOT)}:{line}: possible {label}")


def strip_jsonc(text):
    """Strip // and /* */ comments and trailing commas, respecting string
    literals (so a "https://" URL in a value survives). Good enough for the
    JSONC-flavored config files in this repo; not a general-purpose parser."""
    out = []
    i, n = 0, len(text)
    in_string = False
    while i < n:
        c = text[i]
        if in_string:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if c == '"':
                in_string = False
            i += 1
            continue
        if c == '"':
            in_string = True
            out.append(c)
            i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue
        if c == ",":
            # Look past whitespace AND comments (a trailing comma can be
            # followed by "// ..." or "/* ... */" before the closing
            # bracket) to decide whether to drop it. The comments
            # themselves still get stripped normally on a later pass.
            j = i + 1
            while j < n:
                if text[j] in " \t\r\n":
                    j += 1
                elif text[j] == "/" and j + 1 < n and text[j + 1] == "/":
                    while j < n and text[j] != "\n":
                        j += 1
                elif text[j] == "/" and j + 1 < n and text[j + 1] == "*":
                    j += 2
                    while j + 1 < n and not (text[j] == "*" and text[j + 1] == "/"):
                        j += 1
                    j += 2
                else:
                    break
            if j < n and text[j] in "}]":
                i += 1  # drop trailing comma, outside any string
                continue
        out.append(c)
        i += 1
    return "".join(out)


def check_json(files, findings):
    for path in files:
        if path.suffix != ".json" and path.suffix != ".sublime-settings":
            continue
        text = read_text(path)
        if text is None:
            findings.append(f"{path.relative_to(REPO_ROOT)}: not valid UTF-8")
            continue
        try:
            json.loads(strip_jsonc(text))
        except json.JSONDecodeError as e:
            findings.append(f"{path.relative_to(REPO_ROOT)}: invalid JSON ({e})")


def check_shell_syntax(files, findings):
    for path in files:
        if not is_shell_file(path):
            continue
        # .zprofile/.zshrc are zsh dotfiles, not bash -- zsh has syntax
        # (e.g. glob qualifiers) that bash -n rejects as invalid.
        shell = "zsh" if path.name in SHELL_FILENAMES else "bash"
        result = subprocess.run([shell, "-n", str(path)], capture_output=True, text=True)
        if result.returncode != 0:
            findings.append(f"{path.relative_to(REPO_ROOT)}: shell syntax error: "
                             f"{result.stderr.strip()}")


def check_binary(files, findings):
    for path in files:
        rel = path.relative_to(REPO_ROOT).as_posix()
        if is_reference_asset(rel):
            continue
        if read_text(path) is None:
            findings.append(f"{rel}: not valid UTF-8 (looks like a committed binary)")


def check_machine_paths(files, findings):
    home_pattern = re.compile(r"/Users/[A-Za-z0-9_.-]+")
    for path in files:
        if path == SELF:
            continue
        text = read_text(path)
        if text is None:
            continue
        for m in home_pattern.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            findings.append(f"{path.relative_to(REPO_ROOT)}:{line}: hardcoded "
                             f"absolute home path ({m.group()}), use ~ or $HOME instead")


def check_single_arch_brew(files, findings):
    for path in files:
        if not is_shell_file(path):
            continue
        text = read_text(path)
        if text is None:
            continue
        has_arm = "/opt/homebrew" in text
        has_intel = "/usr/local/bin/brew" in text or "/usr/local/Homebrew" in text
        if has_arm and not has_intel:
            findings.append(f"{path.relative_to(REPO_ROOT)}: references /opt/homebrew "
                             f"(Apple Silicon) with no Intel (/usr/local) fallback")


def check_junk(files, findings):
    # Name-pattern matching only: a mechanical rule, not a judgment call.
    # Whether a large file is genuinely hand-edited vs. accumulated noise is
    # a human call made during config-sync's --pull, on purpose -- see
    # AGENTS.md's "CI vs. judgment" section. Don't grow this into a size
    # heuristic; that's exactly the judgment CI is not supposed to make.
    for path in files:
        rel = path.relative_to(REPO_ROOT).as_posix()
        if JUNK_NAMES.search(rel):
            findings.append(f"{rel}: looks like an accumulated/generated file, not "
                             f"hand-edited config")


def _selftest():
    src = '{\n  // comment with a url http://not-stripped-wrong\n  "a": "https://example.com", /* inline */ "b": 1,\n}'
    parsed = json.loads(strip_jsonc(src))
    assert parsed == {"a": "https://example.com", "b": 1}, parsed
    # a string value ending in ",}" must survive -- not be mistaken for a
    # trailing comma before the object's closing brace
    tricky = '{"a": "value,}", "b": 1,}'
    assert json.loads(strip_jsonc(tricky)) == {"a": "value,}", "b": 1}, strip_jsonc(tricky)
    # a trailing comma followed by a comment, then the closing bracket, must
    # still be recognized as trailing (not just comma-then-whitespace)
    commented_trailing = '{"a": 1, // trailing\n}'
    assert json.loads(strip_jsonc(commented_trailing)) == {"a": 1}, strip_jsonc(commented_trailing)
    print("selftest ok")


def main():
    if "--selftest" in sys.argv:
        _selftest()
        return 0
    files = tracked_files()
    findings = []
    check_secrets(files, findings)
    check_json(files, findings)
    check_shell_syntax(files, findings)
    check_binary(files, findings)
    check_machine_paths(files, findings)
    check_single_arch_brew(files, findings)
    check_junk(files, findings)

    if findings:
        print(f"{len(findings)} finding(s):\n")
        for f in findings:
            print(f"  - {f}")
        return 1
    print("clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
