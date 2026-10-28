"""LaTeX compilation (port of apps/backend/src/services/compileService.js).

Runs inside the `worker-tex` image. Project files are materialised into a temp dir, compiled with the
requested engine, and the PDF is returned as bytes; nothing is left on local disk afterwards.
"""
import os
import re
import resource
import shutil
import signal
import subprocess
import tempfile
from pathlib import Path

from django.conf import settings

from projects import storage
from projects.models import ProjectFile
from projects.paths import safe_path

SUPPORTED_ENGINES = ['pdflatex', 'xelatex', 'lualatex', 'latexmk', 'tectonic']
MULTI_PASS_ENGINES = ('pdflatex', 'xelatex', 'lualatex')  # need bibtex/biber + 2 more passes for citations
MAX_LOG_BYTES = 200_000
BIBLATEX_RE = re.compile(r'\\usepackage(\[.*?\])?\{biblatex\}')


class CompileError(Exception):
    """Reported to the user as the job error."""


class LogBuffer:
    def __init__(self, limit=MAX_LOG_BYTES):
        self.limit, self.size, self.parts = limit, 0, []

    def push(self, text):
        if not text or self.size >= self.limit:
            return
        text = text[:self.limit - self.size]
        self.parts.append(text)
        self.size += len(text)

    def text(self):
        return ''.join(self.parts)


def build_command(engine, out_dir, main_file):
    if engine in MULTI_PASS_ENGINES:
        return [engine, '-interaction=nonstopmode', f'-output-directory={out_dir}', main_file]
    if engine == 'latexmk':
        return ['latexmk', '-pdf', '-interaction=nonstopmode', f'-outdir={out_dir}', main_file]
    if engine == 'tectonic':
        return ['tectonic', '--outdir', str(out_dir), main_file]
    raise CompileError(f'Unsupported engine: {engine}')


def _limit_child():
    """Applied in the child before exec: cap CPU seconds and the size of any file it writes."""
    resource.setrlimit(resource.RLIMIT_CPU, (settings.COMPILE_TIMEOUT_SECONDS * 2,) * 2)
    resource.setrlimit(resource.RLIMIT_FSIZE, (settings.COMPILE_MAX_FILE_BYTES,) * 2)


def run_command(args, cwd, log, env=None, timeout=None):
    """Run one command, appending its output to `log`. Returns the exit code (-1 on timeout).

    Raises FileNotFoundError when the executable does not exist.
    """
    timeout = timeout or settings.COMPILE_TIMEOUT_SECONDS
    proc = subprocess.Popen(
        args, cwd=cwd, env=env or os.environ.copy(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL, start_new_session=True, preexec_fn=_limit_child)
    try:
        out, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)  # kill the whole group (latexmk spawns children)
        out, _ = proc.communicate()
        log.push(out.decode('utf-8', 'replace'))
        log.push(f'\n[error] {args[0]} timed out after {timeout}s and was killed.\n')
        return -1
    log.push(out.decode('utf-8', 'replace'))
    return proc.returncode


def materialise(project, root):
    """Write every project file under `root`. Text comes from Postgres, binaries from S3."""
    root = Path(root).resolve()
    for row in project.files.all():
        target = (root / safe_path(row.path)).resolve()
        if root not in target.parents and target != root:
            raise CompileError('Invalid path in project')
        if row.kind == ProjectFile.DIR:
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if row.kind == ProjectFile.TEXT:
            target.write_text(row.content, encoding='utf-8')
        else:
            target.write_bytes(storage.get_bytes(row.s3_key))


def _tex_env():
    env = os.environ.copy()
    # Never allow \write18; keep TeX from writing outside the working tree.
    env.update({'shell_escape': 'f', 'openout_any': 'p'})
    return env


def compile_project(project, main_file, engine, progress=lambda msg: None):
    """Compile and return {'pdf': bytes|None, 'log': str, 'status': int}. Raises CompileError for setup failures."""
    if engine not in SUPPORTED_ENGINES:
        raise CompileError(f'Unsupported engine: {engine}')
    main_file = safe_path(main_file)
    work = Path(tempfile.mkdtemp(prefix='openprism-compile-'))
    log = LogBuffer()
    try:
        src = work / 'src'
        src.mkdir()
        progress('Preparing project files')
        materialise(project, src)
        if not (src / main_file).is_file():
            raise CompileError(f'Main file not found: {main_file}')

        out_dir = src / '.compile' / 'out'
        out_dir.mkdir(parents=True)
        cmd = build_command(engine, out_dir, main_file)
        base = Path(main_file).stem
        env = _tex_env()

        try:
            progress(f'Running {engine}')
            code = run_command(cmd, src, log, env)
            if engine in MULTI_PASS_ENGINES:
                code = _bibliography_and_passes(cmd, src, out_dir, main_file, base, env, log, progress)
        except FileNotFoundError as exc:
            raise CompileError(f'{engine} not available: {exc}')

        pdf_path = out_dir / f'{base}.pdf'
        pdf = pdf_path.read_bytes() if pdf_path.is_file() else None
        return {'pdf': pdf, 'log': log.text(), 'status': code}
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _bibliography_and_passes(cmd, src, out_dir, main_file, base, env, log, progress):
    aux = out_dir / f'{base}.aux'
    use_biber = aux.is_file() and '\\abx@aux@' in aux.read_text(encoding='utf-8', errors='replace')
    if not use_biber:
        use_biber = bool(BIBLATEX_RE.search((src / main_file).read_text(encoding='utf-8', errors='replace')))
    bib_cmd = 'biber' if use_biber else 'bibtex'
    bib_env = {**env, 'BIBINPUTS': f'{src}:', 'BSTINPUTS': f'{src}:'}
    # cwd=out_dir with a relative base name, because openout_any=p blocks writes to absolute paths.
    bib_args = [bib_cmd, f'--input-directory={src}', base] if use_biber else [bib_cmd, base]
    progress(f'Running {bib_cmd}')
    try:
        run_command(bib_args, out_dir, log, bib_env)
    except FileNotFoundError:
        log.push(f'[warn] {bib_cmd} not available, skipping bibliography pass.\n')
    code = 0
    for n in (2, 3):
        progress(f'Pass {n}')
        code = run_command(cmd, src, log, env)
    return code
