"""Repairing what is already there.

Three jobs: recognise a request to fix something (Indonesian slang included: "benerin", "betulin", "kok error"), remember the last error that
is still open so a bare "benerin" or "coba lagi" knows what to repair, and tell the model how to repair it.

A fix request is work on files, so it is sorted as a task (never as a question without tools), and the model gets a short repair routine.
"""

import re

FIX_VERBS = (r"benerin|benerkan|betulin|betulkan|benarkan|perbaiki|perbaikin|memperbaiki|fix(?:ing|ed|es)?|debug(?:ging)?|"
             r"troubleshoot|repair|beresin|bereskan")
ERROR_WORDS = (r"error|errors|eror|erorr|bug|bugs|ngebug|bugnya|crash(?:ed|es)?|ngecrash|gagal|failed|failure|exception|traceback|stack ?trace|"
               r"rusak|macet|hang|freeze|frozen|layar hitam|black screen|blank screen|"
               r"(?:tidak|gak|ga|nggak|ngga|enggak|tak) (?:jalan|bisa jalan|muncul|berfungsi|kerja|mau jalan|tampil|keluar)|"
               r"not working|doesn'?t work|does not work|won'?t (?:run|start|load|open|work)|broken|stuck")
TRACE = (r"Traceback \(most recent call last\)|\b[A-Z]\w*(?:Error|Exception)\b:|is not defined|Cannot find module|MODULE_NOT_FOUND|"
         r"command not found|Segmentation fault|\[exit code [1-9]|ENOENT|EADDRINUSE")
KNOWLEDGE = (r"^\s*(?:apa (?:itu|arti|yang dimaksud)|apa bedanya|what(?:'s| is| are| does)|jelaskan|jelasin|explain|define|arti dari|"
             r"difference between|contoh|example of)\b")
OWN = (r"\b(?:ini|itu|tadi|saya|gw|gue|gua|aku|punya|my|mine|this|that|kode|code|file|script|skrip|game|app|aplikasi|web|website|"
       r"project|proyek|video|program)\b")

_FILE = re.compile(r"(?<![\w/])([\w.\-]+(?:/[\w.\-]+)*\.(?:py|js|mjs|ts|tsx|jsx|html|htm|css|json|sh|lua|luau|java|kt|md|txt|yml|yaml|toml))\b")
_RESULT_ERR = re.compile(r"^ERROR\b|^ISSUES: [1-9]\d* error|Traceback \(most recent call last\)|\[exit code [1-9]", re.M)


def is_fix_request(text):
    """True when the user asks to repair, check or explain a failure of THEIR work ("benerin", "kok error?", a pasted traceback)."""
    t = (text or "").strip()
    if not t:
        return False
    low = t.lower()
    if re.search(TRACE, t):
        return True
    m = re.match(KNOWLEDGE, low)
    if m and not re.search(OWN, low[m.end():]):
        return False                                           # "what is a syntax error?" asks about the world, not about a file
    return bool(re.search(r"\b(?:%s)\b" % FIX_VERBS, low) or re.search(r"\b(?:%s)\b" % ERROR_WORDS, low))


def _error_line(text):
    lines = [l.strip() for l in str(text).splitlines() if l.strip()]
    for l in reversed(lines):
        if re.search(r"\b\w*(?:Error|Exception)\b|error:|not defined|No module named|Cannot find|not found|failed", l, re.I):
            return l[:220]
    return (lines[0] if lines else "")[:220]


def _files_in(text):
    found = []
    for m in _FILE.finditer(str(text)):
        f = m.group(1)
        if f not in found and not f.lower().startswith(("http", "www.")):
            found.append(f)
    return found[:4]


def trouble(ctx):
    """The newest problem that is still open: {"tool", "line", "files"}, or None."""
    merged = dict(getattr(ctx, "carry_fail", None) or {})
    merged.update((getattr(ctx, "turn", None) or {}).get("pending_fail") or {})
    if merged:
        tool, line = list(merged.items())[-1]
        return {"tool": tool, "line": line, "files": _files_in(" ".join(merged.values()))}
    for m in reversed(list(getattr(ctx, "messages", None) or [])[-16:]):      # a restored conversation: read the newest results
        if m.get("role") != "tool":
            continue
        c = str(m.get("content") or "")
        if "[exit code 0" in c[-200:]:
            return None                                        # the newest run worked
        if _RESULT_ERR.search(c[:4000]):
            return {"tool": "", "line": _error_line(c[:4000]), "files": _files_in(c[:4000])}
    return None


def is_followup(ctx, text):
    """A short message right after an error ("coba lagi", "ok benerin") is about that error."""
    t = (text or "").strip()
    return bool(t) and len(t.split()) <= 8 and trouble(ctx) is not None


def block(ctx, text):
    """The FIX MODE section of the system prompt, or "" when the message is not about repairing something."""
    if not (is_fix_request(text) or is_followup(ctx, text)):
        return ""
    head = "## FIX MODE: the user wants something repaired\n"
    tr = trouble(ctx)
    if tr:
        files = (" Files named in it: %s." % ", ".join(tr["files"])) if tr["files"] else ""
        head += "The last open problem in this chat: %s%s.%s\n" % ((tr["tool"] + ": ") if tr["tool"] else "", tr["line"], files)
    return head + (
        "Do these in order and do not skip one:\n"
        "1. Reproduce it: run the file or command that failed, or take the error above; keep the full error text.\n"
        "2. Open the file the error points at (read_file around the line it names). Reading is allowed: the user asked for a fix. "
        "If you do not know the file, search_files for the error's name or the symbol.\n"
        "3. Find the real cause. A wrong name, option or value: look up the right one (video_api, the package docs, the file that defines it), "
        "never guess. Fix that cause with edit_file, and fix every other place with the same mistake in the same edit.\n"
        "4. Run it again and read the result. Repeat until it passes, with at most four different attempts.\n"
        "5. Report: what was wrong, what you changed, how you checked.\n"
        "Never skip or leave out the failing file, never answer that a file is not needed, and never delete or disable the feature that errors.")
