"""Download an arXiv source bundle and turn it into a project (port of the import-arxiv-sse route)."""
import gzip
import tarfile
import tempfile
import time

import httpx

from . import files as pfiles
from .paths import InvalidPath, safe_path

MAX_FILES = 20000
MAX_TOTAL_BYTES = 500 * 1024 * 1024
DOWNLOAD_TIMEOUT = 300


class ImportFailed(Exception):
    pass


def download(arxiv_id, dest, on_progress):
    """Stream https://arxiv.org/e-print/<id> into the open binary file `dest`."""
    try:
        with httpx.stream('GET', f'https://arxiv.org/e-print/{arxiv_id}', headers={'User-Agent': 'openprism/1.0'},
                          timeout=DOWNLOAD_TIMEOUT, follow_redirects=True) as res:
            if res.status_code != 200:
                raise ImportFailed(f'arXiv download failed: {res.status_code}')
            total = int(res.headers.get('content-length') or 0)
            received = 0
            for chunk in res.iter_bytes():
                dest.write(chunk)
                received += len(chunk)
                if received > MAX_TOTAL_BYTES:
                    raise ImportFailed('arXiv source is too large')
                on_progress({'received': received, 'total': total})
    except httpx.HTTPError as exc:
        raise ImportFailed(f'arXiv download failed: {exc}')


def _clean(name):
    """Normalise a tar member path; None to skip (absolute or escaping paths are dropped, like the Node filter)."""
    try:
        return safe_path(name)
    except InvalidPath:
        return None


def extract_into(project, path):
    """Unpack a downloaded bundle: a (gzipped) tar, or a single gzipped .tex file. Returns the file count."""
    try:
        tar = tarfile.open(path, 'r:*')
    except tarfile.ReadError:
        return _single_file(project, path)
    count, total = 0, 0
    with tar:
        for member in tar:
            if not member.isfile():  # skips directories, symlinks, hardlinks, devices
                continue
            name = _clean(member.name)
            if name is None:
                continue
            count += 1
            total += member.size
            if count > MAX_FILES or total > MAX_TOTAL_BYTES:
                raise ImportFailed('arXiv source is too large')
            pfiles.write_file(project, name, tar.extractfile(member).read())
    if not count:
        raise ImportFailed('arXiv source contained no files')
    return count


def _single_file(project, path):
    try:
        with gzip.open(path) as f:
            data = f.read(MAX_TOTAL_BYTES + 1)
    except (OSError, EOFError):
        raise ImportFailed('arXiv source is not a recognised archive')
    if len(data) > MAX_TOTAL_BYTES:
        raise ImportFailed('arXiv source is too large')
    pfiles.write_text(project, 'main.tex', data.decode('utf-8', 'replace'))
    return 1


def run(job_id_str, progress):
    """Create the project from the job's params. `progress(dict)` receives {phase, percent, ...} updates."""
    from jobs.models import Job
    from .models import Project, Workspace

    job = Job.objects.get(pk=job_id_str)
    p = job.params
    project = Project.objects.create(workspace=Workspace.objects.get(pk=p['workspaceId']), created_by=job.user,
                                     name=p['name'])
    try:
        progress({'phase': 'download', 'percent': 0})
        last = [0.0]

        def on_download(info):
            now = time.monotonic()
            if now - last[0] < 0.3:  # throttle DB writes
                return
            last[0] = now
            total = info['total']
            progress({'phase': 'download', 'percent': round(info['received'] / total * 100) if total > 0 else -1, **info})

        with tempfile.NamedTemporaryFile(prefix='openprism-arxiv-') as tmp:
            download(p['arxivId'], tmp, on_download)
            tmp.flush()
            progress({'phase': 'extract', 'percent': -1})
            extract_into(project, tmp.name)
    except Exception:
        pfiles.delete_project_files(project)
        project.delete()
        raise
    return project
