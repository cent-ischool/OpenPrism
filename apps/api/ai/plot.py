"""Run LLM-generated plotting code in a constrained subprocess (see plot_runner.py)."""
import ast
import json
import os
import resource
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

from django.conf import settings

RUNNER = Path(__file__).with_name('plot_runner.py')
FORBIDDEN_NAMES = {'open', 'exec', 'eval', 'compile', '__import__', 'getattr', 'setattr', 'delattr', 'globals',
                   'locals', 'vars', 'input', 'breakpoint', 'help', 'dir', 'type', 'memoryview', 'super', 'object'}
MEMORY_LIMIT = 4 * 1024 ** 3  # address space, not RSS: numpy/OpenBLAS reserve a lot of virtual memory


class UnsafeCode(ValueError):
    pass


def check_code(source):
    """Reject plotting code that imports modules or reaches for dunders/introspection. Raises UnsafeCode."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise UnsafeCode(f'Syntax error in generated code: {exc}')
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            raise UnsafeCode('Imports are not allowed; use the provided names (df, df_numeric, rows, header, plt, sns, np, pd).')
        if isinstance(node, ast.Name) and (node.id in FORBIDDEN_NAMES or node.id.startswith('__')):
            raise UnsafeCode(f'Use of {node.id!r} is not allowed.')
        if isinstance(node, ast.Attribute) and node.attr.startswith('_'):
            raise UnsafeCode(f'Access to private attribute {node.attr!r} is not allowed.')
        if isinstance(node, (ast.Global, ast.Nonlocal)):
            raise UnsafeCode('global/nonlocal are not allowed.')


def _limits():
    resource.setrlimit(resource.RLIMIT_CPU, (settings.PLOT_TIMEOUT_SECONDS * 2,) * 2)
    resource.setrlimit(resource.RLIMIT_AS, (MEMORY_LIMIT,) * 2)
    resource.setrlimit(resource.RLIMIT_FSIZE, (50 * 1024 * 1024,) * 2)
    # No RLIMIT_NPROC: it counts every process of this uid (the whole Celery worker), so it can't bound just this child.
    # Cap pids with the container runtime instead (pids_limit / k8s podPidsLimit).


def render(table_latex, plot_code, chart_type='bar', title=''):
    """Returns {'ok': True, 'png': bytes} or {'ok': False, 'error': str} (the error is fed back to the LLM)."""
    try:
        check_code(plot_code)
    except UnsafeCode as exc:
        return {'ok': False, 'error': str(exc)}
    tmp = Path(tempfile.mkdtemp(prefix='openprism-plot-'))
    try:
        out = tmp / 'plot.png'
        (tmp / 'payload.json').write_text(json.dumps({
            'tableLatex': table_latex, 'chartType': chart_type, 'title': title,
            'outputPath': str(out), 'plotCode': plot_code}), encoding='utf-8')
        # Scrubbed environment: none of the worker's secrets (DB/S3/LLM keys) are visible to generated code.
        env = {'PATH': os.environ.get('PATH', '/usr/bin'), 'HOME': str(tmp), 'MPLCONFIGDIR': str(tmp),
               'MPLBACKEND': 'Agg', 'TMPDIR': str(tmp),
               'OPENBLAS_NUM_THREADS': '1', 'OMP_NUM_THREADS': '1'}
        proc = subprocess.Popen([sys.executable, '-I', str(RUNNER), str(tmp / 'payload.json')], cwd=tmp, env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
                                start_new_session=True, preexec_fn=_limits)
        try:
            stdout, stderr = proc.communicate(timeout=settings.PLOT_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.communicate()
            return {'ok': False, 'error': f'Plot rendering timed out after {settings.PLOT_TIMEOUT_SECONDS}s.'}
        if proc.returncode != 0:
            msg = (stderr or stdout).decode('utf-8', 'replace').strip()
            return {'ok': False, 'error': msg[-2000:] or f'Python exited with {proc.returncode}'}
        if not out.is_file():
            return {'ok': False, 'error': 'Plot render produced no image.'}
        return {'ok': True, 'png': out.read_bytes()}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
