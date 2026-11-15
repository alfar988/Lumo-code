"""Scope guard: Lumo does not open, list or search files and folders that the user did not ask about.

A conversational request ("explain recursion", "what is the weather like for hiking", "hi") never needs the workspace. Before this guard a model
could still start every turn by listing the folder or reading old files, because its instructions said "look before you change". Now every request is
sorted once at the start of the turn:

  * the user pointed at the workspace (a file, a folder, a path, @file, "project", "fix", "continue" ...)  -> reading tools work as usual
  * otherwise                                                                                          -> reading tools answer "not needed" and the
                                                                                                          model goes on with the request itself

Files that Lumo created in this very turn, a file or folder the user named, and everything after the user said "continue" always stay readable.
"""

import os
import re

from lumo.config import HISTORY_DIRNAME

# Reading tools that look into the user's workspace. (read_notes / recall / use_skill read Lumo's own memory and stay available.)
EXPLORE_TOOLS = {"list_dir", "read_file", "search_files", "find_files", "project_overview"}

# Words that mean "work on what is already there" (Indonesian and English) ...
_MODIFY = re.compile(
    r"\b(baca|read|buka|open|lihat|cek|periksa|check|inspect|review|analisis|analy[sz]e|scan|telusuri|grep|perbaiki|fix|debug|ubah|edit|modify|update|"
    r"perbarui|ganti|replace|refactor|rapikan|optimi[sz]e|hapus|delete|remove|rename|pindah|move|salin|copy|ekstrak|extract|unzip|zip|arsip|archive|"
    r"install|jalankan|run|test|tes|uji|compile|deploy|error|bug|crash|gagal|failed|tambah|tambahkan|add|lanjut|lanjutkan|continue|resume|"
    r"sebelumnya|tadi|earlier|previous)\b", re.I)

# ... and words that name the user's own files and folders.
_WORKSPACE = re.compile(r"\b(file|files|berkas|folder|direktori|directory|dir|path|workspace|repo|repository|project|projek|proyek|kode|code|source|"
                        r"script|skrip|log|struktur|structure|isi file)\b", re.I)

_PATHLIKE = re.compile(r"(?<!\w)(?:~|\.{1,2})?/[\w.\-]+|[\w\-]+\.(?:py|js|ts|tsx|jsx|html|css|json|md|txt|yml|yaml|toml|java|kt|c|cpp|h|go|rs|sh|zip|tar|gz|mp4|png|jpg|csv|sql|php|rb)\b|@[\w./\-]+")

_SMALLTALK = re.compile(
    r"^\s*(hai|halo|hello|hi|hey|hei|oi|p|pagi|siang|sore|malam|selamat\s+\w+|terima kasih|makasih|thanks?|thank you|ok(?:e|ay)?|sip|mantap|bagus|keren|"
    r"siapa (?:kamu|anda)|kamu siapa|who are you|apa kabar|how are you|bisa apa|kamu bisa apa|what can you do)\b[\s\S]{0,40}$", re.I)

_NO_FILES = re.compile(r"\b(tanpa|jangan|don'?t|do not|no need to)\b.{0,24}\b(baca|read|buka|open|lihat|cek|file|folder|scan)\b", re.I)


def is_smalltalk(text):
    t = (text or "").strip()
    return bool(t) and len(t) <= 60 and bool(_SMALLTALK.match(t))


def _top_names(ctx):
    """Names of the top-level entries of the workspace (names only; nothing is read or shown)."""
    try:
        return {n.lower() for n in os.listdir(str(ctx.ws)) if n != HISTORY_DIRNAME and not n.startswith(".")}
    except OSError:
        return set()


def explore_reason(ctx, text, intent, continuation):
    """Why reading the workspace is allowed in this turn ('' = it is not)."""
    t = (text or "").strip()
    if not t or is_smalltalk(t):
        return ""
    if _NO_FILES.search(t):
        return ""
    if continuation:
        return "continuation"
    if _PATHLIKE.search(t):
        return "path"
    words = set(re.findall(r"[\w.\-]+", t.lower()))
    if words & _top_names(ctx):
        return "name"
    if intent == "chat":
        return "hint" if _WORKSPACE.search(t) else ""          # a question: only when it talks about the user's own files
    if _WORKSPACE.search(t) or (intent != "build" and _MODIFY.search(t)):
        return "hint"
    if intent == "build" and re.search(r"\b(ubah|edit|modify|update|perbarui|perbaiki|fix|tambah|tambahkan|add|lanjut|lanjutkan|continue)\b", t, re.I):
        return "hint"
    return ""


def note_request(ctx, text, intent, continuation):
    """Called once at the start of every turn."""
    ctx.scope_reason = explore_reason(ctx, text, intent, continuation)
    ctx.scope_text = (text or "")


def guard(ctx, name, args):
    """None when the tool call may go ahead; otherwise the tool result that replaces it."""
    if name not in EXPLORE_TOOLS or getattr(ctx, "ma_depth", 0):
        return None
    if getattr(ctx, "scope_reason", "x"):
        return None
    if ctx.changes:                                            # Lumo wrote files in this turn: reading them back is part of the job
        return None
    path = str(args.get("path") or args.get("pattern") or "")
    text = getattr(ctx, "scope_text", "")
    if path and path not in (".", "./") and os.path.basename(path.rstrip("/")) and os.path.basename(path.rstrip("/")).lower() in text.lower():
        return None                                            # the user named this file or folder
    ctx.turn["scope_blocked"] = ctx.turn.get("scope_blocked", 0) + 1
    return ("SKIPPED: not needed. The user's message does not ask about files or folders, so do not open, list or search the workspace. "
            "Answer or act from the request itself. If you really need a file the user named, call this tool again with that exact path.")
