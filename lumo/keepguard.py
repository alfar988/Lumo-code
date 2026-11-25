"""Notice when a change throws away working code.

A model that hits an error sometimes deletes the feature that raised it (the sound, the camera, a function) instead of fixing the
call. After a write or an edit of an existing code file this module lists the functions and classes that are gone, so the tool
result can tell the model to put them back and repair the cause.
"""

import ast
import re

from lumo.ui import out, warn

KINDS = {".py": "py", ".js": "js", ".mjs": "js", ".jsx": "js", ".ts": "js", ".tsx": "js", ".html": "js", ".htm": "js",
         ".lua": "lua", ".luau": "lua"}

_JS = [
    re.compile(r"(?m)^[ \t]*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*([A-Za-z_$][\w$]*)\s*\("),
    re.compile(r"(?m)^[ \t]*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:function\b|\([^)]*\)\s*=>|[A-Za-z_$][\w$]*\s*=>)"),
    re.compile(r"(?m)^[ \t]*(?:export\s+)?(?:default\s+)?class\s+([A-Za-z_$][\w$]*)"),
]
_LUA = [re.compile(r"(?m)^[ \t]*(?:local\s+)?function\s+([A-Za-z_][\w.:]*)\s*\(")]

MIN_LINES = 12          # smaller files are rewritten freely
SHOW = 8                # names listed in a note


def py_defs(text):
    """Functions and classes (and the methods of classes) of a Python file; None when it does not parse."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return None
    names = set()

    def walk(node, prefix):
        for ch in ast.iter_child_nodes(node):
            if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef)):
                names.add(prefix + ch.name)                          # helpers nested inside a function are not features
            elif isinstance(ch, ast.ClassDef):
                names.add(prefix + ch.name)
                walk(ch, prefix + ch.name + ".")
            elif isinstance(ch, (ast.If, ast.Try, ast.With)):
                walk(ch, prefix)

    walk(tree, "")
    return names


def rx_defs(text, patterns):
    found = set()
    for rx in patterns:
        found.update(m.group(1) for m in rx.finditer(text))
    return found


def lost_defs(old, new, suffix):
    """Names defined in the old text and no longer defined in the new one (sorted)."""
    kind = KINDS.get((suffix or "").lower())
    if not kind:
        return []
    if kind == "py":
        a, b = py_defs(old), py_defs(new)
        if a is None or b is None:
            return []                                                # a file that does not parse is the verifier's business
    else:
        pats = _JS if kind == "js" else _LUA
        a, b = rx_defs(old, pats), rx_defs(new, pats)
    return sorted(a - b)


def note(path_name, suffix, old, new, open_failure=False):
    """The text for the tool result, or "" when nothing worth saying was lost."""
    old_lines, new_lines = len(old.splitlines()), len(new.splitlines())
    if old_lines < MIN_LINES or (suffix or "").lower() not in KINDS:
        return ""
    gone = lost_defs(old, new, suffix)
    lead = "An error is still open in this turn. " if open_failure else ""
    fix = ("If you removed them to get rid of an error, put them back and fix the cause instead: read the error, look up the right "
           "name or call, correct it and run it again. Deleting a feature is not a fix. Ignore this note only if you renamed, moved "
           "or replaced them on purpose.")
    if gone:
        shown = ", ".join(gone[:SHOW]) + (" (+%d more)" % (len(gone) - SHOW) if len(gone) > SHOW else "")
        return "\nNOTE: %s%d %s no longer exist in %s: %s. %s" % (lead, len(gone), "function or class" if len(gone) == 1 else "functions or classes",
                                                                   path_name, shown, fix)
    if old_lines >= 40 and new_lines * 2 <= old_lines:
        return ("\nNOTE: %s%s went from %d to %d lines. If parts were cut to get past an error, restore them and fix the cause instead. "
                "Ignore this note if the cut was meant." % (lead, path_name, old_lines, new_lines))
    return ""


def report(ctx, path, old, new):
    """Called by the file tools after a change of an existing file. Returns the note (may be empty) and tells the user in one line."""
    from lumo.util import rel
    try:
        name = rel(ctx, path)
        pending = bool((getattr(ctx, "turn", None) or {}).get("pending_fail"))
        text = note(name, path.suffix, old, new, pending)
        if text:
            gone = lost_defs(old, new, path.suffix)
            if gone:
                out("    " + warn("removed: " + ", ".join(gone[:4]) + (" …" if len(gone) > 4 else "")))
            turn = getattr(ctx, "turn", None)
            if isinstance(turn, dict):
                turn.setdefault("removed_code", []).extend(gone)
        return text
    except Exception:
        return ""
