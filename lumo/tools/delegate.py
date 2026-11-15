"""delegate: hand a bulk job to the light worker model (multi-agent mode, see lumo/multiagent.py)."""

from lumo import multiagent
from lumo.tools.registry import S, tool


@tool("delegate",
      "Multi-agent mode only. Hand a bulk job to the light worker model and get a short report back. role=extract: unpack an archive, find and read files, "
      "condense them into facts. role=test: run a check or test command and report the failures. The worker has no memory of this chat and cannot edit "
      "files: put the exact paths, the command and what you need back in task. Do small jobs yourself.",
      {"role": S("extract | test", enum=["extract", "test"]),
       "task": S("everything the worker needs: paths, command, and the format of the answer you want")},
      ["role", "task"])
def t_delegate(a, ctx):
    return multiagent.run_worker(ctx, str(a.get("role") or "").strip().lower(), a.get("task"))
