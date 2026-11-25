"""Which folder is the workspace.

Order: the folder named on the command line, then the folder Lumo was started in (unless that is your home folder or
Lumo's own folder), then the workspace you used last (set by /cd or by the previous start), then ~/workspace.
"""

from pathlib import Path

from lumo.config import APP_DIR

KEY = "workspace"


def default_dir():
    return Path.home() / "workspace"


def saved(cfg):
    """(folder, note). The remembered workspace when it is still a folder; otherwise (None, a note when one was saved, else "")."""
    raw = (cfg or {}).get(KEY)
    if not isinstance(raw, str) or not raw.strip():
        return None, ""
    p = Path(raw).expanduser()
    try:
        if p.is_dir():
            return p, ""
    except OSError:
        pass
    return None, "The saved workspace %s is not available. Using %s." % (raw, default_dir())


def resolve(arg, cfg, cwd=None):
    """(workspace, note) for a start. `arg` is the folder given on the command line, if any."""
    if arg:
        return Path(arg).expanduser(), ""
    here = Path(cwd or Path.cwd()).resolve()
    if here not in (Path.home().resolve(), APP_DIR.resolve()):
        return here, ""
    folder, note = saved(cfg)
    if folder:
        return folder, ""
    return default_dir(), note


def remember(cfg, ws):
    """Put the workspace into the settings. True when it changed."""
    s = str(ws)
    if cfg.get(KEY) == s:
        return False
    cfg[KEY] = s
    return True


def persist(ws):
    """Write only the workspace into the settings file, so no other setting of this run is saved by accident."""
    from lumo.state import load_config, save_config
    try:
        cfg = load_config()
        if remember(cfg, ws):
            save_config(cfg)
    except OSError:
        pass
