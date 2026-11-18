"""Multi-agent mode: a smart model and a light worker model.

    smart model   the one chosen with /model. Plans, writes code, answers the user and repairs errors.
    light model   a small, fast model. Does the bulk work that needs little intelligence: unpacking and reading
                  files, running tests, condensing long error output.

Switch it on with /multiagent (off again with /multiagent off). Two links connect the two models:

  1. openrouter:subagent   OpenRouter's server tool. One entry in the `tools` array of the request, with the worker
                           model in `parameters`:
                               {"type": "openrouter:subagent", "parameters": {"model": "<light model>"}}
                           OpenRouter runs the worker and hands its result back to the smart model. OpenRouter only,
                           and the worker sees only the task text (it cannot reach your files).
  2. delegate              a local tool, any provider. The worker runs in Lumo with a small, read-only toolset
                           (extract: unpack and read files, test: run checks), so it can work on your workspace.

If OpenRouter refuses the server tool for a model, Lumo drops it for the session and keeps going with delegate.
"""

import json
import os
import re
import shutil
import time

from lumo import providers
from lumo.config import HISTORY_DIRNAME, ROUTER_MODEL
from lumo.state import ApiError, bump_req, is_free_model, NoToolsError, req_today, save_config, ToolError
from lumo.ui import acc, bold, clip, dim, err, faint, ok, out, short_model, Spinner, tw, warn
from lumo.util import cap


SERVER_TOOL_TYPE = "openrouter:subagent"

# The request budget. Every worker request counts toward the daily limit of a free model, so the worker is used sparingly:
DIGEST_MIN_CHARS = 3500        # a failing check is condensed only when its output is really long (shorter output is already easy to read)
DIGEST_MIN_LINES = 30
DIGESTS_PER_TURN = 2
JOBS_PER_TURN = 3              # delegate jobs per task
WORKER_REQS_PER_TURN = 8       # worker requests (all jobs and digests together) per task
LOW_QUOTA = 10                 # free requests left today at which the worker pauses and the smart model works alone
WORKER_MAX_STEPS = 6
WORKER_OUT_TOKENS = 4000

SERVER_INSTRUCTIONS = (
    "You are the light worker of Lumo Code. Do exactly the task you are given, using only the text inside the task. "
    "Extract or condense; add no opinions, advice or new code. Copy names, numbers, paths and error messages exactly. "
    "If something the task asks for is not in the text, write 'not in the text'. Keep the answer short and structured."
)

ENV_LINE = ("Workspace: %s. Answer in the language of the task. Keep the final report short. Every model turn costs a request: call all the tools you need in ONE response when "
            "they do not depend on each other, and give your final report within %d model turns.")

ROLES = {
    "extract": {
        "label": "unpack and read files",
        "tools": ("extract_archive", "list_dir", "read_file", "find_files", "search_files"),
        "steps": 6,
        "system": (
            "You are the light worker of Lumo Code. A smarter model gave you ONE bounded job on files: unpack an archive, find files, "
            "read them, and report what is in them. You never write code and never answer the user's questions; you collect facts.\n"
            "Rules:\n- Do exactly the task. Open only what the task names or clearly implies. Never change or delete anything.\n"
            "- Read in parts for big files (read_file with start_line / end_line). Never guess; if something is missing write NOT FOUND.\n"
            "- Copy names, paths, numbers and short code excerpts exactly, with line numbers.\n"
            "Final report (at most 30 lines, no chit-chat): what you did, the paths involved, the structure (tree to depth 2 when you "
            "unpacked something), and the exact content the task asked for."),
    },
    "test": {
        "label": "run checks and report errors",
        "tools": ("run_shell", "run_python", "verify_files", "read_file", "list_dir", "find_files", "search_files"),
        "steps": 6,
        "system": (
            "You are the light worker of Lumo Code. A smarter model asked you to TEST something and report errors. You run the check "
            "or test command named in the task (if none is named, the obvious one for the project: python -m unittest / pytest, npm test, "
            "node file.js, python file.py --selftest), read the output, and report. You never edit files and never install anything.\n"
            "Rules:\n- Run only checks and read-only commands (ls, cat, head, grep, find).\n"
            "- Read the failing line in the source with read_file when the output points at one.\n"
            "- Never invent a file name, line number or message that is not in the output.\n"
            "Final report (at most 25 lines): line 1 = PASS or FAIL with counts. Then for each distinct failure (max 8): "
            "file:line | error type | one-line cause | the exact message. Last line: the exact command you ran."),
    },
}

DIGEST_SYSTEM = (
    "You condense the output of a failing command for a programmer. Reply with at most 10 short lines:\n"
    "1. what failed (the command and exit code if shown)\n2. each distinct error as `file:line  ErrorType: message` (copy the text exactly)\n"
    "3. the most likely cause in one line.\nNever invent a file name, line number or message that is not in the output. No advice beyond the cause."
)

# Commands the test worker may run: checks and read-only probes. Everything that writes, installs or reaches the network is refused.
_SHELL_DENY = re.compile(r"(^|[;&|(]\s*)(rm|rmdir|mv|cp|chmod|chown|dd|mkfs|kill|pkill|sudo|su|curl|wget|apt(-get)?|pkg|git\s+(push|reset|clean|checkout))\b"
                         r"|\b(pip3?|npm|yarn|pnpm|cargo|gem)\s+(install|i|add|remove|uninstall|publish)\b|(?<![0-9&])>>?\s*[^&\s>]|\bsed\s+-i\b|\btee\b|\bdel\s", re.I)


# ---------------------------------------------------------------------------
#  state
# ---------------------------------------------------------------------------
def enabled(ctx):
    return bool(ctx.cfg.get("multiagent", False))


def provider_id(ctx):
    return providers.active(ctx.cfg)["id"]


def smart_model(ctx):
    return ctx.cur_model()


def budget(ctx):
    c = ctx.cfg
    return {"jobs": int(c.get("ma_max_jobs", JOBS_PER_TURN)), "reqs": int(c.get("ma_max_worker_reqs", WORKER_REQS_PER_TURN)),
            "digest_min": int(c.get("ma_digest_min", DIGEST_MIN_CHARS)), "digests": int(c.get("ma_max_digests", DIGESTS_PER_TURN))}


def quota_left(ctx):
    """Free requests left today when the smart model is a free model (None when it is not, so there is no daily limit to protect)."""
    if not is_free_model(ctx.cfg.get("model") or ""):
        return None
    return max(0, int(ctx.cfg.get("free_daily") or 50) - req_today(ctx))


def paused_reason(ctx):
    """'' while the worker may run; otherwise why it is paused (the daily free quota is almost used up)."""
    left = quota_left(ctx)
    if left is not None and left <= int(ctx.cfg.get("ma_low_quota", LOW_QUOTA)):
        return "only %d free request%s left today" % (left, "" if left == 1 else "s")
    return ""


LIGHT_NAME = re.compile(r"nano|mini|lite|small|haiku|flash|a[0-9]b|\b(?:3|4|7|8|9|12|14|20|24|27|30|32)b\b|oss-20b|instant", re.I)


def _score(ctx, m):
    from lumo.models import model_rel, model_score
    return model_score(m)


def light_candidates(ctx, n=8):
    """Models that make sense as the worker, best first: enough context, not junk, not the smart model. Models that are light by name
    (nano, mini, flash, 30b-a3b ...) come first, then models clearly lighter than the smart one, then the rest. Returns [(model dict, score, light_by_name)]."""
    from lumo.models import clean_id, ensure_models, model_rel, model_score
    pool = list(ensure_models(ctx) or [])
    smart = ctx.cfg.get("model") or ""
    smart_m = (ctx.models_by_id or {}).get(smart) or {"id": smart}
    top = model_score(smart_m) if smart else 99.0
    rows = []
    for m in pool:
        mid = m.get("id") or ""
        if not mid or mid == smart or mid == ROUTER_MODEL:
            continue
        if int(m.get("context_length") or 0) < 32000:
            continue
        sc = model_score(m)
        if sc < 12:
            continue                                                     # junk: too small or too odd to read code or logs reliably
        light = bool(LIGHT_NAME.search(clean_id(mid)))
        rows.append((m, sc + model_rel(ctx, mid), light, sc <= top - 6))
    rows.sort(key=lambda r: (r[2], r[3], r[1]), reverse=True)
    return [(m, sc, light) for m, sc, light, _lighter in rows[:n]]


def auto_light_model(ctx):
    key = (provider_id(ctx), ctx.cfg.get("model") or "")
    cached = getattr(ctx, "ma_auto", None)
    if cached and cached[0] == key:
        return cached[1]
    try:
        cands = light_candidates(ctx, 1)
    except Exception:
        cands = []
    if not cands:
        return ctx.cfg.get("model") or ""                                # no list yet or nothing suitable: the smart model itself, and look again next time
    pick = cands[0][0]["id"]
    ctx.ma_auto = (key, pick)
    return pick


def light_model(ctx):
    chosen = (ctx.cfg.get("light_by_provider") or {}).get(provider_id(ctx))
    return chosen or auto_light_model(ctx)


def set_light_model(ctx, mid):
    per = ctx.cfg.setdefault("light_by_provider", {})
    if mid:
        per[provider_id(ctx)] = mid
    else:
        per.pop(provider_id(ctx), None)
    ctx.ma_auto = None
    save_config(ctx.cfg)


CODER_NAME = re.compile(r"coder|codestral|devstral|deepseek|qwen-?3|glm|kimi|gpt-oss|nemotron-3-(?:ultra|super)|claude|gpt-5|gemini.*pro|llama-4|minimax|mistral-large", re.I)


def coding_rank(ctx, m):
    """How good a model is as the one that writes the code: general strength, reliability in this session, and a bonus for known code models."""
    from lumo.models import clean_id, model_rel, model_score
    return model_score(m) + model_rel(ctx, m.get("id") or "") + (4.0 if CODER_NAME.search(clean_id(m.get("id") or "")) else 0.0)


def coder_candidates(ctx, n=6):
    """The best models to write code with, best first: [(model dict, rank)]. Never the random router, never a tiny context."""
    from lumo.models import ensure_models
    rows = []
    for m in list(ensure_models(ctx) or []):
        if not m.get("id") or m["id"] == ROUTER_MODEL or int(m.get("context_length") or 0) < 32000:
            continue
        rows.append((m, coding_rank(ctx, m)))
    rows.sort(key=lambda r: -r[1])
    return rows[:n]


def smart_problem(ctx):
    """'' when the smart model is fine for coding; otherwise why it is not."""
    smart = ctx.cfg.get("model") or ""
    if not smart or smart == ROUTER_MODEL:
        return "the random router changes the model on every request"
    chosen = (ctx.cfg.get("light_by_provider") or {}).get(provider_id(ctx))
    if chosen and chosen != smart:
        from lumo.models import model_score
        by = ctx.models_by_id or {}
        if model_score(by.get(chosen) or {"id": chosen}) > model_score(by.get(smart) or {"id": smart}) + 2:
            return "the worker (%s) is a stronger model than the smart one" % short_model(chosen)
    return ""


def ensure_smart(ctx, say=True):
    """Multi-agent only works well when the model that writes the code is a strong one. If the smart model is the random router (or weaker than the worker),
    switch to the best coding model available. A model the user chose on purpose is never replaced unless the worker outranks it."""
    problem = smart_problem(ctx)
    if not problem:
        return False
    best = coder_candidates(ctx, 1)
    if not best:
        if say:
            out("  " + warn("! ") + dim("smart model: " + problem + ". Choose one with /models."))
        return False
    pick = best[0][0]["id"]
    if pick == ctx.cfg.get("model"):
        return False
    ctx.cfg["model"] = pick
    ctx.override = None
    ctx.ma_auto = None
    save_config(ctx.cfg)
    if say:
        out("  " + dim("smart model set to ") + pick + dim(" (%s)." % problem))
    return True


def worker_is_distinct(ctx):
    return light_model(ctx) != smart_model(ctx)


# ---------------------------------------------------------------------------
#  link 1: the openrouter:subagent server tool
# ---------------------------------------------------------------------------
def server_tool_active(ctx):
    return (enabled(ctx) and provider_id(ctx) == "openrouter" and ctx.cfg.get("multiagent_server", True) is not False
            and not getattr(ctx, "ma_server_off", False) and not paused_reason(ctx))


def server_tools(ctx, prov, model):
    """Entries to add to the `tools` array of a request: [{"type": "openrouter:subagent", "parameters": {"model": ...}}] or [].
    Never added for the worker's own requests, for planning, or when the server tool was refused earlier in this session."""
    if getattr(ctx, "ma_depth", 0) or prov.get("id") != "openrouter" or getattr(ctx, "cur_phase", "build") not in ("build", "chat"):
        return []
    if not server_tool_active(ctx):
        return []
    worker = light_model(ctx)
    if not worker or worker == ROUTER_MODEL:
        return []
    params = {"model": worker, "instructions": SERVER_INSTRUCTIONS, "max_completion_tokens": int(ctx.cfg.get("worker_max_tokens", WORKER_OUT_TOKENS))}
    return [{"type": SERVER_TOOL_TYPE, "parameters": params}]


_REJECT = re.compile(r"subagent|server[ _-]?tool|openrouter:|unsupported.{0,24}tool|tools?\b.{0,30}\b(type|not supported|unsupported)|invalid.{0,24}tool|"
                     r"unknown.{0,20}tool", re.I)


def server_rejected(ctx, body, code, low):
    """The provider refused a request that carried the server tool. Drop the tool for this session. True = retry without it."""
    tools = body.get("tools") or []
    if not any(isinstance(t, dict) and t.get("type") == SERVER_TOOL_TYPE for t in tools):
        return False
    if code not in (400, 404, 422) or not _REJECT.search(low):
        return False
    ctx.ma_server_off = True
    ctx.ma_note = "OpenRouter refused the subagent tool (%s). Using the local worker only." % clip(low.replace("\n", " "), 90)
    return True


def flush_notice(ctx):
    why = paused_reason(ctx) if enabled(ctx) else ""
    if why and not getattr(ctx, "ma_paused_told", False):
        ctx.ma_paused_told = True
        out("  " + warn("! ") + dim("Worker paused: %s. The smart model works alone until the limit resets (00:00 UTC)." % why))
    elif not why:
        ctx.ma_paused_told = False
    note = getattr(ctx, "ma_note", "")
    if note:
        ctx.ma_note = ""
        out("  " + warn("! ") + dim(note))


# ---------------------------------------------------------------------------
#  link 2: the local worker
# ---------------------------------------------------------------------------
def hidden_tools(ctx):
    return set() if enabled(ctx) and not paused_reason(ctx) else {"delegate"}


def prompt_block(ctx, phase):
    if not enabled(ctx) or phase not in ("build", "chat") or paused_reason(ctx):
        return ""
    light = light_model(ctx)
    lines = ["## Multi-agent mode (on)",
             "You are the smart model (%s). A light worker model (%s) takes the bulk jobs off you. You keep the user's goal: you plan, write "
             "code, answer, and repair errors. The worker only reads and runs, and gives you a short report." % (smart_model(ctx), light),
             "- `delegate(role=\"extract\", task=...)`: unpack an archive, find and read files, condense big files into facts.",
             "- `delegate(role=\"test\", task=...)`: run a check or test command and get the failures back as file:line | error | cause.",
             "Delegate only when the job is big (many files, long output); do small jobs yourself. The worker does not see this chat, so put "
             "everything in the task: exact paths, the command, what you need back. Never delegate writing code, planning or the final answer. "
             "A report is a reading, not proof: open the file or rerun the check yourself before you rely on a surprising claim."]
    if phase == "build":
        lines += ["### Code quality (you write every line of code yourself)",
                  "- Before you write: say to yourself what the code must do, its inputs and edge cases (empty, huge, wrong type, missing file), and how you will check it.",
                  "- Write complete files that run: no placeholders, no `...`, no TODO left in finished code; every import, name, path and API call must be real.",
                  "- Small functions with honest names; handle errors where they can happen; validate input; no secrets in code; one responsibility per file.",
                  "- After writing: `verify_files`, then run it. Put a big test run on `delegate(role=\"test\")`, read its report, open the failing line yourself, fix the root cause, run again. "
                  "Finish only after a clean run.",
                  "- Read your own code once before you finish: names that do not exist, off-by-one, missing await or close, empty input, wrong path.",
                  "- The worker never writes or edits code; if you want a change, make it yourself."]
    if server_tool_active(ctx):
        lines.append("The `openrouter:subagent` tool (run by OpenRouter) also exists for text you already hold, for example a long log you paste "
                     "into its task so it comes back condensed. It cannot see files. For anything in the workspace use `delegate`.")
    return "\n".join(lines)


def _block_shell(cmd):
    if _SHELL_DENY.search(cmd or ""):
        return "ERROR: the test worker may only run checks and read-only commands (python, node, npm test, pytest, ls, cat, grep, ...). Refused: %s" % clip(cmd, 80)
    return None


def _note_usage(ctx, usage):
    st = ctx.ma_stats
    st["reqs"] += 1
    ctx.turn["ma_reqs"] = ctx.turn.get("ma_reqs", 0) + 1
    if usage:
        n = (usage.get("prompt_tokens", 0) or 0) + (usage.get("completion_tokens", 0) or 0)
        st["tokens"] += n


def _compact_label(name, args, width):
    from lumo.toolrun import TOOL_META, tool_label
    verb = TOOL_META.get(name, (name, None))[0]
    return "%s %s" % (verb, tool_label(name, args, width))


def run_worker(ctx, role, task):
    """Run a bounded job with the light model and return its report as a tool result."""
    spec = ROLES.get(role)
    if spec is None:
        raise ToolError("unknown role '%s'. Roles: %s" % (role, ", ".join(ROLES)))
    if not enabled(ctx):
        raise ToolError("multi-agent mode is off, so there is no worker. Do this job yourself (the user can switch it on with /multiagent).")
    task = str(task or "").strip()
    if len(task) < 12:
        raise ToolError("the task is too short: the worker does not see this chat. Say what to open or run and what you need back.")
    if getattr(ctx, "ma_depth", 0):
        raise ToolError("a worker cannot delegate again.")
    why = paused_reason(ctx)
    if why:
        return "SKIPPED: the worker is paused (%s). Do this job yourself with the normal tools." % why
    b = budget(ctx)
    if ctx.turn.get("ma_jobs", 0) >= b["jobs"]:
        return "SKIPPED: this task already used %d worker jobs (the limit protects the daily request quota). Do the rest yourself." % b["jobs"]
    if ctx.turn.get("ma_reqs", 0) >= b["reqs"]:
        return "SKIPPED: this task already used %d worker requests. Do the rest yourself." % b["reqs"]
    ckey = (role, " ".join(task.split()).lower(), len(ctx.changes))
    cache = ctx.__dict__.setdefault("ma_cache", {})
    if role == "extract" and ckey in cache:
        return cache[ckey] + "\n(same job as before: answered from the session cache, no new request)"
    from lumo.client import stream_chat
    from lumo.toolcalls import fix_args, normalize_tool_name, parse_text_tool_calls, repair_tool_args, sanitize_messages, slim_schemas, strip_think
    from lumo.toolrun import exec_tool, show_result
    from lumo.tools.registry import TOOLS

    model = light_model(ctx)
    names = [n for n in spec["tools"] if n in TOOLS]
    schemas = slim_schemas([TOOLS[n]["schema"] for n in names], tight=True)
    max_steps = int(ctx.cfg.get("worker_steps", spec["steps"]))
    system = spec["system"] + "\n" + ENV_LINE % (ctx.ws, max_steps)
    msgs = [{"role": "user", "content": task}]
    max_tok = int(ctx.cfg.get("worker_max_tokens", WORKER_OUT_TOKENS))
    t0, steps, final, errors = time.time(), 0, "", 0
    ctx.ma_stats["jobs"] += 1
    ctx.turn["ma_jobs"] = ctx.turn.get("ma_jobs", 0) + 1
    out("  " + bold("worker") + dim(" (%s, %s)" % (role, short_model(model))))
    out("    " + dim(clip(task.replace("\n", " "), tw() - 8)))
    ctx.ma_depth += 1
    try:
        while True:
            steps += 1
            final_round = steps > max_steps or (steps > 1 and ctx.turn.get("ma_reqs", 0) >= b["reqs"])
            sanitize_messages(msgs)
            sp = Spinner("worker thinking")
            sp.start()
            try:
                msg, finish, usage, reasoning = stream_chat(ctx, model, [{"role": "system", "content": system}] + msgs, None if final_round else schemas,
                                                            lambda t: None, None, retries=1, stream=True, fast_rate=True, max_tokens=max_tok)
            except NoToolsError:
                sp.stop()
                return "ERROR: the worker model %s cannot call tools. Choose another with /multiagent worker, or do this job yourself." % model
            except Exception as e:                                       # ApiError or anything odd: the smart model carries on by itself
                sp.stop()
                return "ERROR: the light worker (%s) failed: %s. Do this job yourself with the normal tools." % (model, clip(str(e), 160))
            finally:
                sp.stop()
            _note_usage(ctx, usage)
            calls = msg.get("tool_calls") or []
            content = strip_think(msg.get("content") or "").strip()
            if not calls and content and not final_round:
                parsed, rest_text = parse_text_tool_calls(content, set(names))
                if parsed:
                    calls, msg["tool_calls"], content = parsed, parsed, rest_text
            if final_round:
                calls = []
            used = set()
            for i, tc in enumerate(calls):
                fn = tc["function"]
                fn["name"] = normalize_tool_name(fn.get("name"), set(names)) or fn.get("name")
                if not tc.get("id") or tc["id"] in used:
                    tc["id"] = "wcall_%d_%d" % (steps, i)
                used.add(tc["id"])
                a_, _st = repair_tool_args(fn.get("arguments"), fn.get("name"))
                fn["arguments"] = json.dumps(a_ if a_ is not None else {}, ensure_ascii=False)
            msg["content"] = content or ("" if calls else None)
            msgs.append(msg)
            if not calls:
                final = content or (reasoning or "").strip()[-1500:]
                if final:
                    break
                errors += 1
                if errors >= 2 or final_round:
                    break
                msgs.append({"role": "user", "content": "Your reply was empty. Give your final report now."})
                continue
            for tc in calls:
                name = tc["function"]["name"]
                try:
                    args = fix_args(name, json.loads(tc["function"]["arguments"]))
                except ValueError:
                    args = {}
                if name not in names:
                    res = "ERROR: tool '%s' is not available to the worker. Available: %s" % (name, ", ".join(names))
                else:
                    out("    " + faint("┊ ") + dim(clip(_compact_label(name, args, tw() - 14), tw() - 10)))
                    res = (_block_shell(args.get("command")) if name == "run_shell" else None) or exec_tool(ctx, name, args)
                    if res.startswith("ERROR"):
                        out("    " + faint("┊ ") + err("✗ ") + dim(clip(res[5:].lstrip(": "), tw() - 12)))
                msgs.append({"role": "tool", "tool_call_id": tc["id"], "content": cap(res, 6000)})
            if steps >= max_steps + 2:
                break
    finally:
        ctx.ma_depth -= 1
    secs = int(time.time() - t0)
    if not final:
        final = "(the worker returned no report after %d steps; do this job yourself)" % steps
    out("    " + faint("┊ ") + ok("✓ ") + dim("report ready · %d step%s · %ds" % (steps, "" if steps == 1 else "s", secs)))
    report = "WORKER REPORT (light model %s, role %s, %d steps). A reading by a small model, not proof:\n%s" % (model, role, steps, cap(final.strip(), 7000))
    if role == "extract" and final and not final.startswith("(the worker returned no report"):
        cache[ckey] = report
    return report


def call_light(ctx, system, user, max_tokens=700):
    """One request to the light model without tools. Returns the text, or '' when it fails."""
    from lumo.client import stream_chat
    from lumo.toolcalls import strip_think
    ctx.ma_depth += 1
    try:
        msg, finish, usage, reasoning = stream_chat(ctx, light_model(ctx), [{"role": "system", "content": system}, {"role": "user", "content": user}], None,
                                                    lambda t: None, None, retries=1, stream=True, fast_rate=True, max_tokens=max_tokens)
    except Exception:                                                    # the digest is a bonus: any failure leaves the raw output as it was
        return ""
    finally:
        ctx.ma_depth -= 1
    _note_usage(ctx, usage)
    return strip_think(msg.get("content") or "").strip()


def digest_failure(ctx, name, args, res):
    """A really long failing check is read by the light model first: the smart model gets the errors in a few lines plus the tail of the raw output.
    Short output is left alone (it is already easy to read), each distinct error is condensed once, and the number per task is capped."""
    from lumo import safelimit
    b = budget(ctx)
    if (not enabled(ctx) or getattr(ctx, "ma_depth", 0) or len(res) < b["digest_min"] or res.count("\n") < DIGEST_MIN_LINES or safelimit.maximum()
            or ctx.turn.get("digests", 0) >= b["digests"] or ctx.turn.get("ma_reqs", 0) >= b["reqs"] or paused_reason(ctx) or not worker_is_distinct(ctx)):
        return res
    sig = hash(res[-400:])
    seen = ctx.__dict__.setdefault("ma_digested", set())
    if sig in seen:
        return res                                                       # the same failure again: the smart model already has the reading
    seen.add(sig)
    ctx.turn["digests"] = ctx.turn.get("digests", 0) + 1
    cmd = args.get("command") or args.get("script") or name
    sp = Spinner("light model reads the errors")
    sp.start()
    try:
        text = call_light(ctx, DIGEST_SYSTEM, "Command: %s\n\nOutput (the end is the most important part):\n%s" % (clip(str(cmd), 200), res[-9000:]), 600)
    finally:
        sp.stop()
    if not text:
        return res
    out("  " + dim("errors condensed by %s" % short_model(light_model(ctx))))
    return ("[light-model digest of this failure, read by %s; if it looks wrong trust the raw output below]\n%s\n\n[raw output, last part]\n%s"
            % (light_model(ctx), text[:1800], res[-3000:]))


# ---------------------------------------------------------------------------
#  /multiagent test: a real check of the whole machinery, a handful of requests
# ---------------------------------------------------------------------------
SELFTEST_TEXT = "Order 12 shipped on day 3 with 4 items; refund 7."
SELFTEST_TRACE = ("Traceback (most recent call last):\n  File \"app.py\", line 3, in f\n    int(\"x\")\n"
                  "ValueError: invalid literal for int() with base 10: 'x'\n[exit code 1]")


def _post_json(ctx, url, body, headers, timeout=120):
    """One non-streaming request; returns (status, parsed json or {}, error message)."""
    import urllib.error
    import urllib.request
    headers = dict(headers, Accept="application/json")
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
    status, data, msg = 0, {}, ""
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            status = r.status
            data = json.loads(r.read().decode("utf-8", "replace") or "{}")
    except urllib.error.HTTPError as e:
        status = e.code
        try:
            data = json.loads(e.read().decode("utf-8", "replace") or "{}")
            msg = str((data.get("error") or {}).get("message") or "")[:300]
        except Exception:
            msg = ""
    except Exception as e:
        msg = str(e)[:300]
    bump_req(ctx)
    return status, data, msg


def selftest(ctx):
    """Runs the real thing against the real provider and prints a short report you can copy: (A) does OpenRouter accept the subagent server tool for the
    smart model, (B) can the light model work on files through the local worker, (C) can it condense an error. Uses about 4 requests."""
    from lumo.client import build_request
    smart, light, prov = smart_model(ctx), light_model(ctx), providers.active(ctx.cfg)
    out("  multi-agent self-test" + dim("  smart %s, worker %s, %s" % (clip(smart, 28), clip(light, 28), prov["name"])))
    out("  " + dim("About 4 requests; on free models they count toward the daily limit."))
    rows = []
    was_mode, was_off, was_turn, reqs0 = ctx.cfg.get("multiagent"), getattr(ctx, "ma_server_off", False), ctx.turn, ctx.session_reqs
    ctx.cfg["multiagent"] = True                                         # the machinery is tested even when the mode is off
    ctx.ma_server_off = False
    ctx.turn = dict(was_turn, ma_jobs=0, ma_reqs=0, digests=0)
    try:
        # A. the server tool
        if prov["id"] == "openrouter":
            try:
                ctx.cur_phase = "build"
                noop = {"type": "function", "function": {"name": "noop", "description": "unused", "parameters": {"type": "object", "properties": {}}}}
                _p, url, body, headers = build_request(ctx, smart, [{"role": "user", "content":
                    "Use the subagent tool exactly once: give it the text below and ask it to extract every number. Then reply with only those numbers, separated by commas.\n"
                    "Text: " + SELFTEST_TEXT}], [noop], 400, False)
                body["tools"] = [t for t in body.get("tools", []) if t.get("type") == SERVER_TOOL_TYPE]
                sent_model = (body["tools"][0]["parameters"].get("model") if body["tools"] else None)
                if not body["tools"]:
                    rows.append((False, "server tool", "not added to the request (paused, or the worker is the random router): /multiagent worker <id>"))
                else:
                    status, data, msg = _post_json(ctx, url, body, headers)
                    if status == 200:
                        choice = (data.get("choices") or [{}])[0]
                        text = str((choice.get("message") or {}).get("content") or "").strip()
                        usage = data.get("usage") or {}
                        extra = [k for k in usage if "tool" in k.lower() or "server" in k.lower()]
                        good = all(n in text for n in ("12", "3", "4", "7"))
                        rows.append((bool(text), "server tool openrouter:subagent",
                                     "accepted (HTTP 200, worker %s). Answer: %s%s%s" % (short_model(sent_model or ""), clip(text.replace("\n", " "), 60) or "(empty)",
                                                                                      "" if good else "  [unexpected answer]", ("  usage: " + ",".join(extra)) if extra else "")))
                    elif status == 429:
                        rows.append((False, "server tool", "rate limited (HTTP 429): %s. Try again later." % (msg or "daily or per-minute limit")))
                    else:
                        rows.append((False, "server tool", "refused (HTTP %s): %s  → /multiagent server off keeps the local worker only" % (status or "?", msg or "no message")))
            except Exception as e:
                rows.append((False, "server tool", "error: %s" % clip(str(e), 120)))
        else:
            rows.append((True, "server tool", "skipped: openrouter:subagent exists only on OpenRouter (current provider: %s)" % prov["name"]))

        # B. the local worker on real files
        d = ctx.ws / HISTORY_DIRNAME / ("selftest-%d" % int(time.time()))
        try:
            d.mkdir(parents=True, exist_ok=True)
            (d / "a.txt").write_text("alpha-4821\n", encoding="utf-8")
            (d / "b.txt").write_text("bravo-7730\n", encoding="utf-8")
            rel = os.path.relpath(str(d), str(ctx.ws))
            res = run_worker(ctx, "extract", "List the files in the folder %s and report the exact content of each file." % rel)
            good = "4821" in res and "7730" in res
            rows.append((good, "local worker (extract)", "read both files correctly" if good else clip(res.replace("\n", " "), 140)))
        except Exception as e:
            rows.append((False, "local worker (extract)", "error: %s" % clip(str(e), 120)))
        finally:
            shutil.rmtree(str(d), ignore_errors=True)

        # C. condensing an error
        try:
            text = call_light(ctx, DIGEST_SYSTEM, "Command: python app.py\n\nOutput:\n" + SELFTEST_TRACE, 400)
            good = bool(text) and ("ValueError" in text or "app.py" in text)
            rows.append((good, "error digest", ("condensed: " + clip(text.replace("\n", " "), 80)) if text else "the light model returned nothing"))
        except Exception as e:
            rows.append((False, "error digest", "error: %s" % clip(str(e), 120)))
    finally:
        ctx.cfg["multiagent"] = was_mode
        ctx.ma_server_off = was_off
        ctx.turn = was_turn
    used = ctx.session_reqs - reqs0
    lines = []
    for good, title, detail in rows:
        out("  " + (ok("✓ ") if good else err("✗ ")) + bold(title) + dim("  " + detail))
        lines.append("%s %s: %s" % ("PASS" if good else "FAIL", title, detail))
    passed = sum(1 for r in rows if r[0])
    out("  " + dim("%d/%d passed · %d request%s used" % (passed, len(rows), used, "" if used == 1 else "s")))
    try:
        d = ctx.ws / HISTORY_DIRNAME
        d.mkdir(parents=True, exist_ok=True)
        head = "Lumo multi-agent self-test | smart %s | light %s | provider %s | %s" % (smart, light, prov["id"], time.strftime("%Y-%m-%d %H:%M:%S"))
        (d / "multiagent-test.txt").write_text(head + "\n" + "\n".join(lines) + "\n%d/%d passed\n" % (passed, len(rows)), encoding="utf-8")
        out("  " + dim("saved in history/multiagent-test.txt · copy the lines above if something failed"))
    except OSError:
        pass


# ---------------------------------------------------------------------------
#  /multiagent
# ---------------------------------------------------------------------------
def status_rows(ctx):
    """[(label, text)] for the banner and /multiagent."""
    if not enabled(ctx):
        return []
    link = "openrouter:subagent + delegate" if server_tool_active(ctx) else "delegate (local worker)"
    return [("smart", smart_model(ctx)), ("light", light_model(ctx)), ("link", link)]


def show_status(ctx):
    on = enabled(ctx)
    out("  multi-agent " + (ok("on") if on else dim("off")))
    if not on:
        out("  " + dim("A smart model writes the code; a small model reads files and runs tests. Turn it on with /multiagent on."))
        return
    out("  " + dim("smart   ") + clip(smart_model(ctx), tw() - 12))
    out("  " + dim("worker  ") + clip(light_model(ctx), tw() - 12))
    problem = smart_problem(ctx)
    if problem:
        out("  " + warn("! ") + dim(clip(problem, tw() - 6)))
        out("  " + dim("/multiagent smart auto picks a coding model."))
    if not worker_is_distinct(ctx):
        out("  " + warn("! ") + dim("smart and worker are the same model. /multiagent worker lets you pick another."))
    if provider_id(ctx) == "openrouter":
        if ctx.cfg.get("multiagent_server", True) is False:
            link = "local worker only (server tool off)"
        elif getattr(ctx, "ma_server_off", False):
            link = "local worker only (OpenRouter refused the server tool)"
        elif light_model(ctx) == ROUTER_MODEL:
            link = "local worker only (the random router cannot be the worker)"
        else:
            link = SERVER_TOOL_TYPE + " + local worker"
    else:
        link = "local worker (the server tool is OpenRouter only)"
    out("  " + dim("link    ") + link)
    b = budget(ctx)
    out("  " + dim("limits  ") + "%d jobs and %d worker requests per task; errors condensed from %d characters" % (b["jobs"], b["reqs"], b["digest_min"]))
    jobs, reqs = ctx.turn.get("ma_jobs", 0), ctx.turn.get("ma_reqs", 0)
    if jobs or reqs:
        out("  " + dim("task    ") + "%d job%s, %d worker request%s so far" % (jobs, "" if jobs == 1 else "s", reqs, "" if reqs == 1 else "s"))
    st = ctx.ma_stats
    if st["jobs"] or st["reqs"]:
        out("  " + dim("session ") + "%d job%s, %d request%s, %d tokens" % (st["jobs"], "" if st["jobs"] == 1 else "s", st["reqs"], "" if st["reqs"] == 1 else "s", st["tokens"]))
    left = quota_left(ctx)
    if left is not None:
        out("  " + dim("free requests left today: %d" % left) + ((" " + warn("(worker paused)")) if paused_reason(ctx) else ""))
    out("  " + dim("/multiagent off · smart · worker · server · budget · test"))


def cmd_multiagent(ctx, arg):
    sub = (arg[0].lower() if arg else "")
    if sub in ("status", "info", "?"):
        show_status(ctx)
    elif sub in ("on", "off") or not sub:
        now = (sub == "on") if sub else not enabled(ctx)
        ctx.cfg["multiagent"] = now
        ctx.ma_server_off = False
        save_config(ctx.cfg)
        if now:
            try:
                ensure_smart(ctx)                                        # the model that writes the code must be a strong one
            except Exception:
                pass
        show_status(ctx)
        if now:
            out("  " + dim("Worker requests count toward your daily request limit."))
    elif sub == "worker":
        want = arg[1] if len(arg) > 1 else ""
        if not want:
            cur = light_model(ctx)
            out("  " + dim("worker: ") + cur + dim("  (smart model: /model)"))
            try:
                rows = light_candidates(ctx, 8)
            except Exception:
                rows = []
            ctx.ma_list = [m["id"] for m, _s, _l in rows]
            for i, (m, _sc, light) in enumerate(rows, 1):
                out("  %s %s %s" % (acc("%2d" % i), clip(m["id"], tw() - 14), dim("%dk" % (int(m.get("context_length") or 0) // 1000) + (" · light" if light else ""))))
            out("  " + dim("choose: /multiagent worker <n|id> · back to automatic: /multiagent worker auto"))
        elif want.lower() == "auto":
            set_light_model(ctx, "")
            out("  " + ok("✓ worker: ") + light_model(ctx) + dim(" (automatic)"))
        elif want.isdigit() and getattr(ctx, "ma_list", None) and 1 <= int(want) <= len(ctx.ma_list):
            set_light_model(ctx, ctx.ma_list[int(want) - 1])
            out("  " + ok("✓ worker: ") + light_model(ctx))
        else:
            set_light_model(ctx, want)
            out("  " + ok("✓ worker: ") + want)
    elif sub == "smart":
        want = arg[1] if len(arg) > 1 else ""
        rows = []
        if not want:
            try:
                rows = coder_candidates(ctx, 6)
            except Exception:
                rows = []
            ctx.ma_list = [m["id"] for m, _r in rows]
            out("  " + dim("smart: ") + smart_model(ctx) + dim("  (writes the code)"))
            for i, (m, rank) in enumerate(rows, 1):
                out("  %s %s %s" % (acc("%2d" % i), clip(m["id"], tw() - 14), dim("%dk" % (int(m.get("context_length") or 0) // 1000))))
            out("  " + dim("choose: /multiagent smart <n|id> · best one: /multiagent smart auto"))
        elif want.lower() == "auto":
            ctx.cfg["model"] = ""                                        # force a fresh choice
            ensure_smart(ctx)
        else:
            if want.isdigit() and ctx.ma_list and 1 <= int(want) <= len(ctx.ma_list):
                want = ctx.ma_list[int(want) - 1]
            ctx.cfg["model"], ctx.override = want, None
            ctx.ma_auto = None
            save_config(ctx.cfg)
            out("  " + ok("✓ smart model: ") + want)
    elif sub == "budget":
        keys = {"jobs": "ma_max_jobs", "reqs": "ma_max_worker_reqs", "digest": "ma_digest_min", "low": "ma_low_quota"}
        if len(arg) > 1 and arg[1].lower() == "reset":
            for k in keys.values():
                ctx.cfg.pop(k, None)
            save_config(ctx.cfg)
        elif len(arg) > 2 and arg[1].lower() in keys and arg[2].isdigit():
            ctx.cfg[keys[arg[1].lower()]] = int(arg[2])
            save_config(ctx.cfg)
        b = budget(ctx)
        out("  worker limits")
        out("  " + dim("jobs per task      ") + str(b["jobs"]) + dim("   /multiagent budget jobs <n>"))
        out("  " + dim("requests per task  ") + str(b["reqs"]) + dim("   /multiagent budget reqs <n>"))
        out("  " + dim("condense errors    ") + "from %d characters" % b["digest_min"] + dim("   /multiagent budget digest <n>"))
        out("  " + dim("pause at           ") + "%d free requests left" % int(ctx.cfg.get("ma_low_quota", LOW_QUOTA)) + dim("   /multiagent budget low <n>"))
        out("  " + dim("defaults:          /multiagent budget reset"))
    elif sub == "test":
        selftest(ctx)
    elif sub == "server":
        val = (arg[1].lower() if len(arg) > 1 else "")
        if val in ("on", "off"):
            ctx.cfg["multiagent_server"] = val == "on"
            ctx.ma_server_off = False
            save_config(ctx.cfg)
        show_status(ctx)
    else:
        out("  " + dim("usage: /multiagent [on|off|status] · smart [id|n|auto] · worker [id|n|auto] · server on|off · budget · test"))
