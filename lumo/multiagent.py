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
import re
import time

from lumo import providers
from lumo.config import ROUTER_MODEL
from lumo.state import ApiError, NoToolsError, save_config, ToolError
from lumo.ui import acc, bold, clip, dim, err, faint, ok, out, short_model, Spinner, tw, warn
from lumo.util import cap


SERVER_TOOL_TYPE = "openrouter:subagent"

DIGEST_MIN_CHARS = 1800        # a failing check with less output than this is already short enough to read
DIGESTS_PER_TURN = 3
WORKER_MAX_STEPS = 10
WORKER_OUT_TOKENS = 4000

SERVER_INSTRUCTIONS = (
    "You are the light worker of Lumo Code. Do exactly the task you are given, using only the text inside the task. "
    "Extract or condense; add no opinions, advice or new code. Copy names, numbers, paths and error messages exactly. "
    "If something the task asks for is not in the text, write 'not in the text'. Keep the answer short and structured."
)

ENV_LINE = "Workspace: %s. Answer in the language of the task. Keep the final report short."

ROLES = {
    "extract": {
        "label": "unpack and read files",
        "tools": ("extract_archive", "list_dir", "read_file", "find_files", "search_files"),
        "steps": 10,
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
        "steps": 8,
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
        return "the random router picks a different model every time, so code quality jumps around"
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
            out("  " + warn("! ") + dim("smart model: " + problem + ". Pick a strong one with /models."))
        return False
    pick = best[0][0]["id"]
    if pick == ctx.cfg.get("model"):
        return False
    ctx.cfg["model"] = pick
    ctx.override = None
    ctx.ma_auto = None
    save_config(ctx.cfg)
    if say:
        out("  " + ok("✓ ") + dim("smart model set to ") + pick + dim(" (best for coding; " + problem + ")"))
    return True


def worker_is_distinct(ctx):
    return light_model(ctx) != smart_model(ctx)


# ---------------------------------------------------------------------------
#  link 1: the openrouter:subagent server tool
# ---------------------------------------------------------------------------
def server_tool_active(ctx):
    return (enabled(ctx) and provider_id(ctx) == "openrouter" and ctx.cfg.get("multiagent_server", True) is not False
            and not getattr(ctx, "ma_server_off", False))


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
    ctx.ma_note = "OpenRouter did not accept the subagent server tool for this request (%s). Multi-agent goes on with the local worker (delegate)." % clip(low.replace("\n", " "), 90)
    return True


def flush_notice(ctx):
    note = getattr(ctx, "ma_note", "")
    if note:
        ctx.ma_note = ""
        out("  " + warn("! ") + dim(note))


# ---------------------------------------------------------------------------
#  link 2: the local worker
# ---------------------------------------------------------------------------
def hidden_tools(ctx):
    return set() if enabled(ctx) else {"delegate"}


def prompt_block(ctx, phase):
    if not enabled(ctx) or phase not in ("build", "chat"):
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
    from lumo.client import stream_chat
    from lumo.toolcalls import fix_args, normalize_tool_name, parse_text_tool_calls, repair_tool_args, sanitize_messages, slim_schemas, strip_think
    from lumo.toolrun import exec_tool, show_result
    from lumo.tools.registry import TOOLS

    model = light_model(ctx)
    names = [n for n in spec["tools"] if n in TOOLS]
    schemas = slim_schemas([TOOLS[n]["schema"] for n in names], tight=True)
    system = spec["system"] + "\n" + ENV_LINE % ctx.ws
    msgs = [{"role": "user", "content": task}]
    max_steps = int(ctx.cfg.get("worker_steps", spec["steps"]))
    max_tok = int(ctx.cfg.get("worker_max_tokens", WORKER_OUT_TOKENS))
    t0, steps, final, errors = time.time(), 0, "", 0
    ctx.ma_stats["jobs"] += 1
    out("  " + acc("◈ ") + bold("worker") + dim(" · %s · %s" % (role, short_model(model))))
    out("    " + dim(clip(task.replace("\n", " "), tw() - 8)))
    ctx.ma_depth += 1
    try:
        while True:
            steps += 1
            final_round = steps > max_steps
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
    return "WORKER REPORT (light model %s, role %s, %d steps). A reading by a small model, not proof:\n%s" % (model, role, steps, cap(final.strip(), 7000))


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
    """A long failing check is read by the light model first: the smart model gets the errors in a few lines plus the tail of the raw output."""
    from lumo import safelimit
    if (not enabled(ctx) or getattr(ctx, "ma_depth", 0) or len(res) < DIGEST_MIN_CHARS or safelimit.maximum()
            or ctx.turn.get("digests", 0) >= DIGESTS_PER_TURN or not worker_is_distinct(ctx)):
        return res
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
    out("  " + faint("◈ ") + dim("errors condensed by %s" % short_model(light_model(ctx))))
    return ("[light-model digest of this failure, read by %s; if it looks wrong trust the raw output below]\n%s\n\n[raw output, last part]\n%s"
            % (light_model(ctx), text[:1800], res[-3000:]))


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
    out("  " + acc("◈ ") + bold("multi-agent  ") + (ok("on") if on else warn("off")))
    if not on:
        out("    " + dim("one smart model plans and codes; a light model unpacks files and runs tests."))
        out("    " + dim("switch on: /multiagent on"))
        return
    out("    " + dim("smart  ") + clip(smart_model(ctx), tw() - 14) + dim("   plans · codes · answers · fixes errors"))
    problem = smart_problem(ctx)
    if problem:
        out("    " + warn("! ") + dim(clip(problem, tw() - 10)))
        out("    " + dim("fix: /multiagent smart auto"))
    out("    " + dim("light  ") + clip(light_model(ctx), tw() - 14) + dim("   unpacks files · runs tests · condenses errors"))
    if not worker_is_distinct(ctx):
        out("    " + warn("! ") + dim("both roles use the same model. Pick a lighter one: /multiagent worker"))
    if provider_id(ctx) == "openrouter":
        if ctx.cfg.get("multiagent_server", True) is False:
            out("    " + dim("link   delegate only (server tool off: /multiagent server on)"))
        elif getattr(ctx, "ma_server_off", False):
            out("    " + dim("link   delegate only (OpenRouter refused the server tool this session)"))
        elif light_model(ctx) == ROUTER_MODEL:
            out("    " + dim("link   delegate only (the random router cannot be the worker: /multiagent worker)"))
        else:
            out("    " + dim("link   ") + SERVER_TOOL_TYPE + dim(" (server tool) + delegate (local worker)"))
    else:
        out("    " + dim("link   delegate (local worker); the server tool is OpenRouter only"))
    st = ctx.ma_stats
    if st["jobs"] or st["reqs"]:
        out("    " + dim("session %d worker job%s · %d request%s · %d tokens" % (st["jobs"], "" if st["jobs"] == 1 else "s", st["reqs"], "" if st["reqs"] == 1 else "s", st["tokens"])))
    out("    " + dim("/multiagent off · smart [id|auto] · worker [id|auto] · server on|off"))


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
            out("    " + dim("every worker request counts toward your request limit; free models share one daily limit."))
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
    elif sub == "server":
        val = (arg[1].lower() if len(arg) > 1 else "")
        if val in ("on", "off"):
            ctx.cfg["multiagent_server"] = val == "on"
            ctx.ma_server_off = False
            save_config(ctx.cfg)
        show_status(ctx)
    else:
        out("  " + dim("usage: /multiagent [on|off|status] · smart [id|n|auto] · worker [id|n|auto] · server on|off"))
