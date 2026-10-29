"""Synchronous DB side of collaboration (called from async code through database_sync_to_async)."""
import hashlib

from django.db import connection, transaction
from pycrdt import Doc, Text

from projects import files as pfiles
from projects.models import Project, ProjectFile

from .models import CollabDoc


def _lock(project_id, path):
    """Transaction-scoped advisory lock on (project, path): serialises seeding and flushes across replicas."""
    digest = hashlib.sha1(f'{project_id}:{path}'.encode()).digest()
    key = int.from_bytes(digest[:8], 'big') & 0x7FFFFFFFFFFFFFFF
    with connection.cursor() as cur:
        cur.execute('SELECT pg_advisory_xact_lock(%s)', [key])


def _file_text(project, path):
    row = project.files.filter(path=path, kind=ProjectFile.TEXT).values_list('content', flat=True).first()
    return row  # None when the file does not exist (yet)


def diff_replace(text, new):
    """Rewrite a pycrdt Text to `new` by replacing only the differing middle (keeps other people's cursors sane)."""
    old = str(text)
    if old == new:
        return False
    prefix = 0
    limit = min(len(old), len(new))
    while prefix < limit and old[prefix] == new[prefix]:
        prefix += 1
    suffix = 0
    while suffix < limit - prefix and old[len(old) - 1 - suffix] == new[len(new) - 1 - suffix]:
        suffix += 1
    if len(old) - suffix > prefix:
        del text[prefix:len(old) - suffix]
    insert = new[prefix:len(new) - suffix]
    if insert:
        text.insert(prefix, insert)
    return True


def load(project_id, path):
    """The Yjs update to start a room from, created exactly once however many replicas race to open the file.

    If the file's text changed outside collaboration since the last flush (REST edit, template apply, …) the
    stored state is brought in line with the file, as a normal CRDT edit.
    """
    with transaction.atomic():
        _lock(project_id, path)
        project = Project.objects.get(pk=project_id)
        file_text = _file_text(project, path)
        row = CollabDoc.objects.filter(project=project, path=path).first()
        doc = Doc()
        text = doc.get('content', type=Text)
        if row and row.state:
            doc.apply_update(bytes(row.state))
        changed = False
        if file_text is not None:
            changed = diff_replace(text, file_text)
        if row is None:
            row = CollabDoc(project=project, path=path)
            changed = True
        if changed:
            row.state = doc.get_update()
            row.save()
        return bytes(row.state)


def flush(project_id, path, local_update):
    """Merge a room's state into the stored state, project the text into the file, return the merged update.

    Merging (rather than overwriting) is what keeps replicas convergent: whatever any replica persisted is
    folded in, and the caller applies the result back to its live doc.
    """
    with transaction.atomic():
        _lock(project_id, path)
        project = Project.objects.get(pk=project_id)
        row, _ = CollabDoc.objects.get_or_create(project=project, path=path)
        doc = Doc()
        text = doc.get('content', type=Text)
        if row.state:
            doc.apply_update(bytes(row.state))
        doc.apply_update(local_update)
        merged = doc.get_update()
        new_text = str(text)
        if new_text != _file_text(project, path):
            pfiles.write_text(project, path, new_text)
        if merged != bytes(row.state):
            row.state = merged
            row.save(update_fields=['state', 'updated_at'])
        return merged


def project_name(project_id):
    return Project.objects.filter(pk=project_id).values_list('name', flat=True).first()
