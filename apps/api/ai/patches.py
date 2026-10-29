"""Unified-diff helpers for the agent's patch tools (replaces jsdiff createTwoFilesPatch/applyPatch)."""
import difflib
import re

HUNK_RE = re.compile(r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@')


class PatchError(ValueError):
    pass


def make_patch(path, original, proposed):
    lines = list(difflib.unified_diff(
        original.splitlines(keepends=True), proposed.splitlines(keepends=True),
        fromfile=f'{path}\tcurrent', tofile=f'{path}\tproposed', n=3))
    body = ''.join(line if line.endswith('\n') else line + '\n\\ No newline at end of file\n' for line in lines)
    return f'Index: {path}\n{"=" * 67}\n{body}'


def extract_path(patch):
    lines = patch.split('\n')
    for line in lines:
        if line.startswith('+++ '):
            path = line[4:].split('\t')[0].strip()
            return path[2:] if path.startswith('b/') else path
    for line in lines:
        if line.startswith('--- '):
            path = line[4:].split('\t')[0].strip()
            return path[2:] if path.startswith('a/') else path
    return ''


def apply_patch(original, patch):
    """Apply a unified diff to `original`. Context must match; hunks may be offset from their stated line."""
    src = original.splitlines(keepends=True)
    out, pos = [], 0  # pos = index into src already consumed
    hunks, current = [], None
    patch_lines = patch.split('\n')
    while patch_lines and patch_lines[-1] == '':
        patch_lines.pop()  # trailing newline of the patch text itself
    for line in patch_lines:
        match = HUNK_RE.match(line)
        if match:
            current = {'start': int(match.group(1)), 'lines': []}
            hunks.append(current)
        elif current is None or line.startswith('\\'):
            continue  # file headers before the first hunk, or "\ No newline at end of file"
        elif line == '':
            current['lines'].append(' ')  # editors/LLMs often strip the leading space of a blank context line
        elif line[0] in ' +-':
            current['lines'].append(line)
    if not hunks:
        raise PatchError('Patch contains no hunks')
    for hunk in hunks:
        old = [l[1:] for l in hunk['lines'] if l[0] in ' -']
        new = [l[1:] for l in hunk['lines'] if l[0] in ' +']
        start = _find(src, old, max(hunk['start'] - 1, pos))
        if start is None:
            raise PatchError(f"Hunk at line {hunk['start']} does not match the file")
        out.extend(src[pos:start])
        out.extend(_with_endings(new, src, start, len(old)))
        pos = start + len(old)
    out.extend(src[pos:])
    return ''.join(out)


def _norm(line):
    return line.rstrip('\r\n')


def _find(src, old, hint):
    """Index where `old` (lines without endings) matches src, searching outward from the hinted position."""
    if not old:
        return min(hint, len(src))
    n = len(old)
    for delta in range(0, len(src) + 1):
        for idx in {hint + delta, hint - delta}:
            if idx < 0 or idx + n > len(src):
                continue
            if all(_norm(src[idx + i]) == _norm(old[i]) for i in range(n)):
                return idx
    return None


def _with_endings(new, src, start, old_len):
    eol = '\r\n' if src and src[min(start, len(src) - 1)].endswith('\r\n') else '\n'
    out = [_norm(l) + eol for l in new]
    # keep "no trailing newline" when the replaced block was the end of a file without one
    if out and start + old_len == len(src) and src and not src[-1].endswith('\n'):
        out[-1] = _norm(out[-1])
    return out
