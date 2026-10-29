"""Process hardening for workers that run untrusted code (LaTeX, LLM-written plotting code)."""
import ctypes
import sys

PR_SET_DUMPABLE = 4


def make_undumpable():
    """Mark this process non-dumpable (Linux).

    The kernel then refuses other processes of the same user access to /proc/<pid>/environ, /proc/<pid>/mem and
    ptrace. Workers hold the database and storage credentials in their environment and spawn children that run
    user-supplied documents; without this, such a document could read its parent's environment through the
    /proc filesystem (LuaTeX's Lua io.open cannot be restricted by TeX's own file-access settings).
    Returns True if the flag was set.
    """
    if not sys.platform.startswith('linux'):
        return False
    try:
        return ctypes.CDLL(None, use_errno=True).prctl(PR_SET_DUMPABLE, 0, 0, 0, 0) == 0
    except (OSError, AttributeError):
        return False
