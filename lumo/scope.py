"""Scope: whether to open, list or search the user's files is the MODEL's decision, not a keyword list's.

An earlier version answered every reading tool with "SKIPPED: not needed" unless the message contained a file name or a word such as "fix". That
was a keyword guess, and it was wrong whenever the user said it another way ("benerin", "kok error?", "coba lagi"): the broken file was never
opened. Now the system prompt tells the model when files are worth opening (the request is about existing work, a file was named, an error is
open) and when they are not (greetings, questions, research, a brand-new build), and the tools simply work. What stays here:

  * greetings and pings are answered without any tool (tools are switched off for them),
  * the long history files (thousands of lines) can only be read in small pieces, twice per task,
  * installing packages follows the install guard below,
  * `note_request` still sorts the message so that the planning phase knows when to hand over the workspace overview.
"""

import os
import re

from lumo import fixmode
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
    r"^\s*(hai|halo|hello|hi|hey|hei|oi|p|pagi|siang|sore|malam|selamat\s+\w+|terima kasih|makasih|thanks?|thank you|mantap|bagus|keren|"
    r"siapa (?:kamu|anda)|kamu siapa|who are you|apa kabar|how are you|bisa apa|kamu bisa apa|what can you do)\b[\s\S]{0,40}$", re.I)

_NO_FILES = re.compile(r"\b(tanpa|jangan|don'?t|do not|no need to)\b.{0,24}\b(baca|read|buka|open|lihat|cek|file|folder|scan)\b", re.I)


# A ping, an interjection, a laugh, a bare "ok": nothing to act on. (Typed with doubled letters: "woii", "haloo", "yooo".)
_PING = re.compile(
    r"^\s*(?:w+o+i+|w+o+y+|w+o+e+|w+e+i+|w+e+h+|o+i+|o+y+|y+o+|h+o+i+|h+e+y+|h+e+i+|h+a+l+o+|h+a+i+|h+i+|h+e+l+l+o+|p+|t+e+s+t*|ping|bro|bang|sis|kak|min|bot|ai|lumo|lu|"
    r"assalamu\W?alaikum|permisi|misi|h+m+|nah|nih|wk(?:wk)*\w*|ha(?:ha)+\w*|he(?:he)+\w*|lol|anj\w*|njir|wah|waduh|aduh|loh|lho|lah|kok|hah|e+h+|ha|gimana|gmn|apa|kenapa|napa)"
    r"(?:\s+(?:lumo|lu|bro|bang|kak|min|bot|ai))?[\s!?.,~]*$", re.I)


def is_vague(text):
    """A greeting, a ping or just punctuation: nothing to act on. The answer is one friendly line and a question; no tools, and no going back to old work."""
    t = (text or "").strip()
    if not t:
        return True
    if not re.search(r"[^\W_]", t, re.U):                       # only punctuation or emoji
        return True
    return bool(_PING.match(t)) or is_smalltalk(t)


# Package managers: installing, searching or updating software is never done on the model's own initiative.
_PKG = re.compile(
    r"(?:^|[;&|(]\s*|\bsudo\s+|\bxargs\s+)(?:pkg|apt(?:-get)?|apt-cache|dpkg|pip3?|pipx|npm|npx|yarn|pnpm|cargo|gem|brew|conda|poetry|composer|go\s+(?:get|install))\s+"
    r"(?:-{1,2}\S+\s+)*(?:install|i|add|search|update|upgrade|full-upgrade|remove|uninstall|download|build|reinstall|autoremove)\b|\bpython3?\s+-m\s+pip\b", re.I)
_INSTALL_WORDS = re.compile(r"instal|pasang|unduh|download|setup|set up|siapkan|upgrade|update|perbarui|uninstall|remove|hapus paket|purge|\\bpkg\\b|\\bpip\\b|\\bnpm\\b|\\bapt\\b", re.I)
_HEAVY = re.compile(r"\b(upgrade|full-upgrade|dist-upgrade|autoremove|remove|uninstall|purge|reinstall)\b", re.I)    # changes the whole system, not just what the task needs
_MISSING = re.compile(r"ModuleNotFoundError|No module named|ImportError: cannot import|Cannot find module|MODULE_NOT_FOUND|command not found|: not found\b|is not installed", re.I)


def install_guard(ctx, name, args):
    """None when the call may go ahead; otherwise the tool result that replaces it.

    While Lumo is working on a task (a request to build, fix, run or do something) a missing package or tool is installed right away: ffmpeg for a video, Pillow for
    an image, a Node module. Package managers do NOT run when nothing is being worked on: a greeting, a question that only needs an answer. System-wide upgrades and
    removals always need the user to ask."""
    if name not in ("run_shell", "run_python"):
        return None
    code = str(args.get("command") or args.get("code") or args.get("script") or "")
    if not _PKG.search(code) and not (name == "run_python" and re.search(r"\bpip\s+install\b|-m\s+pip\b", code)):
        return None
    if getattr(ctx, "ma_depth", 0):
        return None
    working = not getattr(ctx, "vague", False) and getattr(ctx, "intent", "task") in ("build", "task")
    asked = bool(_INSTALL_WORDS.search(getattr(ctx, "scope_text", "") or ""))
    if working and (not _HEAVY.search(code) or asked):
        return None
    ctx.turn["scope_blocked"] = ctx.turn.get("scope_blocked", 0) + 1
    if working:
        return ("SKIPPED: upgrading or removing packages changes the whole system and nobody asked for it. Install only what the task needs "
                "(pkg install -y <name> on Termux), and carry on.")
    return ("SKIPPED: nothing is being built or run in this message (it is a greeting or a question), so do not install or search for packages. "
            "Answer the message. If the user wants something installed they will say so.")


def note_result(ctx, result):
    """Remember that a tool result in this turn reported a missing module or command (the only other reason to install)."""
    if result and _MISSING.search(result[:4000]):
        ctx.turn["missing_dep"] = True


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
    if fixmode.is_fix_request(t):
        return "fix"                                           # "benerin", "kok error?": repairing is work on the user's files
    if fixmode.is_followup(ctx, t):
        return "follow-up"                                     # "coba lagi" right after an error
    if intent == "chat":
        return "hint" if _WORKSPACE.search(t) else ""          # a question: only when it talks about the user's own files
    if _WORKSPACE.search(t) or (intent != "build" and _MODIFY.search(t)):
        return "hint"
    if intent == "build" and re.search(r"\b(ubah|edit|modify|update|perbarui|perbaiki|fix|tambah|tambahkan|add|lanjut|lanjutkan|continue)\b", t, re.I):
        return "hint"
    return ""


def note_request(ctx, text, intent, continuation):
    """Called once at the start of every turn."""
    ctx.vague = is_vague(text) and not continuation
    ctx.scope_reason = "" if ctx.vague else explore_reason(ctx, text, intent, continuation)
    ctx.scope_text = (text or "")


_HISTORY_FILE = re.compile(r"(^|/)history/(transcript\.md|archive/|events\.|state\.json)", re.I)
HISTORY_READ_LINES = 150


def guard(ctx, name, args):
    """None when the tool call may go ahead; otherwise the tool result that replaces it.

    Greetings, pings and thanks have nothing to open, so they get no tools. Whether a real request needs the user's own files is up to the model;
    only the history files are limited."""
    if name in EXPLORE_TOOLS and getattr(ctx, "vague", False) and not getattr(ctx, "ma_depth", 0):
        ctx.turn["scope_blocked"] = ctx.turn.get("scope_blocked", 0) + 1
        return ("SKIPPED: not needed. The message is a greeting, a ping or thanks, so there is nothing to open, list or search. "
                "Answer it in one short sentence.")
    if name == "read_file" and _HISTORY_FILE.search(str(args.get("path") or "").replace("\\", "/")):
        # The transcript is thousands of lines. Reading it in chunks burns requests and context: search it, or read a small piece, twice at most.
        first, last = int(args.get("start_line") or 1), args.get("end_line")
        span = (int(last) - first + 1) if last else 400
        if span > HISTORY_READ_LINES or ctx.turn.get("hist_reads", 0) >= 2:
            ctx.turn["scope_blocked"] = ctx.turn.get("scope_blocked", 0) + 1
            return ("SKIPPED: history files are long (the transcript has thousands of lines). Search them with search_files or recall using a keyword, or read at most "
                    "%d lines at a time, twice per task. If the user asked to continue, the last conversation is already in this chat." % HISTORY_READ_LINES)
        ctx.turn["hist_reads"] = ctx.turn.get("hist_reads", 0) + 1
    return None
