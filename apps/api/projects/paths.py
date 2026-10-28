"""Path validation for project files (port of safeJoin / sanitizeUploadPath in the Node backend)."""
import posixpath

TEXT_EXTENSIONS = {'.tex', '.bib', '.cls', '.sty', '.bst', '.txt', '.md', '.json', '.yaml', '.yml', '.csv', '.tsv'}


class InvalidPath(ValueError):
    pass


def safe_path(raw):
    """Return a normalised relative path, or raise InvalidPath if it is absolute or escapes the root."""
    if not isinstance(raw, str) or not raw.strip() or '\x00' in raw:
        raise InvalidPath('Invalid path')
    path = raw.replace('\\', '/')
    if path.startswith('/'):
        raise InvalidPath('Invalid path')
    parts = [p for p in path.split('/') if p and p != '.']
    if not parts or '..' in parts:
        raise InvalidPath('Invalid path')
    return '/'.join(parts)


def sanitize_upload_path(filename):
    """Lenient variant for uploads: silently drops empty, '.' and '..' segments."""
    if not filename:
        return ''
    parts = filename.replace('\\', '/').lstrip('/').split('/')
    return '/'.join(p for p in parts if p and p not in ('.', '..'))


def is_text_file(path):
    return posixpath.splitext(path)[1].lower() in TEXT_EXTENSIONS
