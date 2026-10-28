"""Safe zip extraction: sanitised paths, no directory entries, bounded size."""
import zipfile

from projects.paths import sanitize_upload_path

MAX_MEMBERS = 20000
MAX_TOTAL_BYTES = 500 * 1024 * 1024


def iter_zip_files(fileobj, skip=lambda path: False):
    """Yield (relative_path, bytes) for each regular file. Raises zipfile.BadZipFile or ValueError."""
    with zipfile.ZipFile(fileobj) as zf:
        infos = zf.infolist()
        if len(infos) > MAX_MEMBERS:
            raise ValueError('Zip has too many entries')
        if sum(i.file_size for i in infos) > MAX_TOTAL_BYTES:
            raise ValueError('Zip is too large when extracted')
        for info in infos:
            if info.is_dir():
                continue
            path = sanitize_upload_path(info.filename)
            if not path or skip(path):
                continue
            yield path, zf.read(info)
