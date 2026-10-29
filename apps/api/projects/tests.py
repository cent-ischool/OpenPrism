from django.test import SimpleTestCase, TestCase

from . import files, storage
from .models import Project, Workspace
from .paths import InvalidPath, is_text_file, safe_path, sanitize_upload_path


class PathTests(SimpleTestCase):
    def test_safe_path_normalises(self):
        self.assertEqual(safe_path('a//b/./c.tex'), 'a/b/c.tex')
        self.assertEqual(safe_path('a\\b.tex'), 'a/b.tex')

    def test_safe_path_rejects_escape(self):
        for bad in ('../x', 'a/../../x', '/etc/passwd', '', '..', 'a\x00b'):
            with self.assertRaises(InvalidPath, msg=bad):
                safe_path(bad)

    def test_sanitize_upload_path_strips(self):
        self.assertEqual(sanitize_upload_path('/../a/./b.png'), 'a/b.png')

    def test_is_text_file(self):
        self.assertTrue(is_text_file('main.TEX'))
        self.assertFalse(is_text_file('fig.png'))


class FileServiceTests(TestCase):
    """Runs against the real Postgres and Garage from compose.yaml."""

    def setUp(self):
        ws = Workspace.objects.create(name='w')
        self.project = Project.objects.create(workspace=ws, name='p')
        self.addCleanup(files.delete_project_files, self.project)

    def test_text_roundtrip_and_tree(self):
        files.write_text(self.project, 'main.tex', 'héllo')
        files.write_text(self.project, 'sec/intro.tex', 'x')
        files.mkdir(self.project, 'empty')
        self.assertEqual(files.read_text(self.project, 'main.tex'), 'héllo')
        self.assertEqual(files.list_tree(self.project), [
            {'path': 'empty', 'type': 'dir'}, {'path': 'main.tex', 'type': 'file'},
            {'path': 'sec', 'type': 'dir'}, {'path': 'sec/intro.tex', 'type': 'file'}])

    def test_binary_goes_to_s3(self):
        row = files.write_binary(self.project, 'img/a.png', b'\x89PNG\x00data')
        self.assertTrue(row.s3_key.startswith(f'projects/{self.project.id}/'))
        self.assertEqual(files.read_bytes(self.project, 'img/a.png'), b'\x89PNG\x00data')

    def test_overwrite_binary_deletes_old_object(self):
        first = files.write_binary(self.project, 'a.png', b'1')
        files.write_binary(self.project, 'a.png', b'2')
        with self.assertRaises(Exception):
            storage.get_bytes(first.s3_key)
        self.assertEqual(files.read_bytes(self.project, 'a.png'), b'2')

    def test_write_file_routes_by_extension(self):
        self.assertEqual(files.write_file(self.project, 'a.bib', b'@x{}').kind, 'text')
        self.assertEqual(files.write_file(self.project, 'a.pdf', b'%PDF').kind, 'binary')
        self.assertEqual(files.write_file(self.project, 'bad.tex', b'\xff\xfe').kind, 'binary')

    def test_rename_directory_moves_children(self):
        files.write_text(self.project, 'a/x.tex', '1')
        files.write_binary(self.project, 'a/y.png', b'2')
        files.rename(self.project, 'a', 'b')
        self.assertEqual(files.read_text(self.project, 'b/x.tex'), '1')
        self.assertEqual(files.read_bytes(self.project, 'b/y.png'), b'2')
        with self.assertRaises(files.FileNotFound):
            files.read_text(self.project, 'a/x.tex')

    def test_rename_rejects_existing_and_self_nesting(self):
        files.write_text(self.project, 'a.tex', '1')
        files.write_text(self.project, 'b.tex', '2')
        with self.assertRaises(FileExistsError):
            files.rename(self.project, 'a.tex', 'b.tex')
        files.mkdir(self.project, 'd')
        with self.assertRaises(ValueError):
            files.rename(self.project, 'd', 'd/e')

    def test_delete_dir_removes_s3_objects(self):
        row = files.write_binary(self.project, 'd/y.png', b'2')
        files.delete(self.project, 'd')
        self.assertEqual(self.project.files.count(), 0)
        with self.assertRaises(Exception):
            storage.get_bytes(row.s3_key)

    def test_copy_project_files(self):
        files.write_text(self.project, 'main.tex', 'm')
        files.write_binary(self.project, 'i.png', b'img')
        other = Project.objects.create(workspace=self.project.workspace, name='copy')
        self.addCleanup(files.delete_project_files, other)
        files.copy_project_files(self.project, other)
        self.assertEqual(files.read_text(other, 'main.tex'), 'm')
        self.assertEqual(files.read_bytes(other, 'i.png'), b'img')
        files.delete(self.project, 'i.png')  # copy must be independent
        self.assertEqual(files.read_bytes(other, 'i.png'), b'img')

    def test_presigned_url_fetchable(self):
        # The URL is signed for the public host; reach it via the internal endpoint with that Host header.
        import urllib.request
        from urllib.parse import urlparse
        from django.conf import settings
        row = files.write_binary(self.project, 'a.png', b'xyz')
        url = urlparse(storage.presigned_url(row.s3_key))
        self.assertEqual(url.netloc, urlparse(settings.S3_PUBLIC_ENDPOINT_URL).netloc)
        internal = f"{settings.S3_ENDPOINT_URL}{url.path}?{url.query}"
        req = urllib.request.Request(internal, headers={'Host': url.netloc})
        self.assertEqual(urllib.request.urlopen(req).read(), b'xyz')
