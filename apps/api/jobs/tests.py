import os
import shutil
import struct
import tempfile
import zlib
from datetime import timedelta
from unittest import mock, skipUnless

from django.test import TestCase, override_settings
from django.utils import timezone

from common import secrets as job_secrets
from projects import files, storage
from projects.models import Project
from projects.test_api import ApiBase, client_for, make_user

from . import compile as tex
from . import tasks
from .models import Job



def make_png():
    """A valid 1x1 PNG."""
    def chunk(kind, data):
        body = kind + data
        return struct.pack('>I', len(data)) + body + struct.pack('>I', zlib.crc32(body))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(b'\x00\xff\x00\x00')) + chunk(b'IEND', b''))


HAS_TEX = shutil.which('pdflatex') is not None
DOC = '\\documentclass{article}\n\\begin{document}\nHello \\LaTeX\n\\end{document}\n'


class CompileApiTests(ApiBase):
    def setUp(self):
        super().setUp()
        self.pid = self.new_project()
        files.write_text(Project.objects.get(pk=self.pid), 'main.tex', DOC)
        patcher = mock.patch('jobs.views.compile_project.delay')
        self.delay = patcher.start()
        self.addCleanup(patcher.stop)

    def compile(self, **body):
        return self.c.post('/api/compile', {'projectId': self.pid, **body}, format='json')

    def test_queues_job_and_returns_id(self):
        res = self.compile(engine='xelatex')
        self.assertTrue(res.data['ok'])
        job = Job.objects.get(pk=res.data['jobId'])
        self.assertEqual((job.type, job.status, job.params), ('compile', 'queued', {'mainFile': 'main.tex', 'engine': 'xelatex'}))
        self.delay.assert_called_once_with(str(job.id))

    def test_validation_uses_ok_false_shape(self):
        self.assertEqual(self.c.post('/api/compile', {}, format='json').data['error'], 'Missing projectId.')
        self.assertIn('Unsupported engine', self.compile(engine='word').data['error'])
        self.assertIn('Main file not found', self.compile(mainFile='nope.tex').data['error'])
        self.assertEqual(self.compile(mainFile='../x.tex').data['error'], 'Invalid main file path.')
        self.delay.assert_not_called()

    def test_other_users_project_is_404(self):
        other = client_for(make_user('other@example.com'))
        self.assertEqual(other.post('/api/compile', {'projectId': self.pid}, format='json').status_code, 404)

    def test_limits_active_jobs_per_user(self):
        for _ in range(3):
            self.assertTrue(self.compile().data['ok'])
        res = self.compile()
        self.assertEqual(res.status_code, 429)
        self.assertFalse(res.data['ok'])

    def test_status_and_pdf_download(self):
        job = Job.objects.create(type='compile', user=self.user, project=Project.objects.get(pk=self.pid), status='queued')
        self.assertNotIn('result', self.c.get(f'/api/jobs/{job.id}').data)  # only once finished
        key = f'jobs/{job.id}/output.pdf'
        storage.put_bytes(key, b'%PDF-test')
        self.addCleanup(storage.delete_prefix, f'jobs/{job.id}/')
        job.status, job.result = 'success', {'log': 'LOG', 'exitStatus': 0, 'engine': 'pdflatex', 'mainFile': 'main.tex', 'pdfKey': key}
        job.save()
        data = self.c.get(f'/api/jobs/{job.id}').data
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['result'], {'log': 'LOG', 'status': 0, 'engine': 'pdflatex', 'mainFile': 'main.tex',
                                          'pdfUrl': f'/api/jobs/{job.id}/pdf'})
        pdf = self.c.get(f'/api/jobs/{job.id}/pdf')
        self.assertEqual((pdf.content, pdf['Content-Type']), (b'%PDF-test', 'application/pdf'))
        other = client_for(make_user('other@example.com'))
        self.assertEqual(other.get(f'/api/jobs/{job.id}').status_code, 404)
        self.assertEqual(other.get(f'/api/jobs/{job.id}/pdf').status_code, 404)


class CompileTaskTests(TestCase):
    """The task wrapper with the TeX run mocked out: status transitions, storage, retries."""

    def setUp(self):
        self.user = make_user('t@example.com')
        ws = self.user.memberships.first().workspace
        self.project = Project.objects.create(workspace=ws, name='p')
        self.job = Job.objects.create(type='compile', user=self.user, project=self.project,
                                      params={'mainFile': 'main.tex', 'engine': 'pdflatex'})
        self.addCleanup(storage.delete_prefix, f'jobs/{self.job.id}/')

    def run_task(self, **mock_kwargs):
        with mock.patch('jobs.tasks.tex.compile_project', **mock_kwargs):
            tasks.compile_project(str(self.job.id))
        self.job.refresh_from_db()

    def test_success_stores_pdf(self):
        self.run_task(return_value={'pdf': b'%PDF', 'log': 'ok', 'status': 0})
        self.assertEqual(self.job.status, 'success')
        self.assertEqual(storage.get_bytes(self.job.result['pdfKey']), b'%PDF')
        self.assertEqual(self.job.result['log'], 'ok')

    def test_no_pdf_fails_but_keeps_log(self):
        self.run_task(return_value={'pdf': None, 'log': '! Undefined control sequence.', 'status': 1})
        self.assertEqual((self.job.status, self.job.error), ('failed', 'No PDF generated.'))
        self.assertIn('Undefined control sequence', self.job.result['log'])

    def test_setup_error_and_crash_fail_the_job(self):
        self.run_task(side_effect=tex.CompileError('pdflatex not available: x'))
        self.assertEqual((self.job.status, self.job.error), ('failed', 'pdflatex not available: x'))
        self.job.status = 'queued'
        self.job.save()
        self.run_task(side_effect=RuntimeError('boom'))
        self.assertEqual(self.job.status, 'failed')
        self.assertIn('boom', self.job.error)

    def test_redelivery_of_finished_job_is_a_noop(self):
        self.job.status = 'success'
        self.job.save()
        with mock.patch('jobs.tasks.tex.compile_project') as run:
            tasks.compile_project(str(self.job.id))
        run.assert_not_called()

    def test_missing_job_is_ignored(self):
        tasks.compile_project('00000000-0000-0000-0000-000000000000')

    def test_reaper_fails_dead_jobs_only(self):
        old = timezone.now() - timedelta(hours=2)
        stale = Job.objects.create(type='compile', status='running')
        stuck = Job.objects.create(type='compile', status='queued')
        fresh = Job.objects.create(type='compile', status='running')
        Job.objects.filter(pk__in=[stale.pk, stuck.pk]).update(updated_at=old)
        job_secrets.put(str(stale.pk), {'apiKey': 'k'})
        self.assertEqual(tasks.reap_stale_jobs(), 2)
        self.assertEqual(job_secrets.get(str(stale.pk)), {})  # a reaped job must not leave its API key behind
        for j in (stale, stuck, fresh):
            j.refresh_from_db()
        self.assertEqual((stale.status, stuck.status, fresh.status), ('failed', 'failed', 'running'))

    def test_cleanup_removes_old_finished_jobs_and_output(self):
        storage.put_bytes(f'jobs/{self.job.id}/output.pdf', b'x')
        Job.objects.filter(pk=self.job.pk).update(status='success', updated_at=timezone.now() - timedelta(days=3))
        running = Job.objects.create(type='compile', status='running')
        Job.objects.filter(pk=running.pk).update(updated_at=timezone.now() - timedelta(days=3))
        self.assertEqual(tasks.cleanup_old_jobs(), 1)
        self.assertFalse(Job.objects.filter(pk=self.job.pk).exists())
        self.assertTrue(Job.objects.filter(pk=running.pk).exists())
        with self.assertRaises(Exception):
            storage.get_bytes(f'jobs/{self.job.id}/output.pdf')


@skipUnless(HAS_TEX, 'needs TeX Live: docker compose run --rm worker-tex python manage.py test jobs')
class RealCompileTests(TestCase):
    def setUp(self):
        user = make_user('real@example.com')
        self.project = Project.objects.create(workspace=user.memberships.first().workspace, name='p')
        self.addCleanup(files.delete_project_files, self.project)

    def test_pdflatex_produces_pdf(self):
        files.write_text(self.project, 'main.tex', DOC)
        out = tex.compile_project(self.project, 'main.tex', 'pdflatex')
        self.assertTrue(out['pdf'].startswith(b'%PDF'))

    def test_subdirectories_and_binary_assets(self):
        png = make_png()
        files.write_binary(self.project, 'figs/dot.png', png)
        files.write_text(self.project, 'sec/a.tex', 'From a subfolder.')
        files.write_text(self.project, 'main.tex', '\\documentclass{article}\\usepackage{graphicx}\\begin{document}'
                         '\\input{sec/a}\\includegraphics[width=1cm]{figs/dot.png}\\end{document}')
        out = tex.compile_project(self.project, 'main.tex', 'pdflatex')
        self.assertTrue(out['pdf'], out['log'][-800:])

    def test_bibtex_pass_resolves_citations(self):
        files.write_text(self.project, 'refs.bib', '@book{k, author={A. Author}, title={A Title}, year={2020}, publisher={P}}')
        files.write_text(self.project, 'main.tex', '\\documentclass{article}\\begin{document}See \\cite{k}.'
                         '\\bibliographystyle{plain}\\bibliography{refs}\\end{document}')
        out = tex.compile_project(self.project, 'main.tex', 'pdflatex')
        self.assertTrue(out['pdf'])
        self.assertIn('This is BibTeX', out['log'])
        last_pass = out['log'].split('This is pdfTeX')[-1]
        self.assertNotIn("Citation `k' undefined", last_pass)

    def test_latex_error_returns_log_not_exception(self):
        files.write_text(self.project, 'main.tex', '\\documentclass{article}\\begin{document}\\undefinedcmd\\end{document}')
        out = tex.compile_project(self.project, 'main.tex', 'pdflatex')
        self.assertIn('Undefined control sequence', out['log'])

    def test_missing_main_and_unavailable_engine(self):
        with self.assertRaisesRegex(tex.CompileError, 'Main file not found'):
            tex.compile_project(self.project, 'main.tex', 'pdflatex')
        files.write_text(self.project, 'main.tex', DOC)
        with self.assertRaisesRegex(tex.CompileError, 'tectonic not available'):
            tex.compile_project(self.project, 'main.tex', 'tectonic')  # not installed in the worker image

    @override_settings(COMPILE_TIMEOUT_SECONDS=3)
    def test_runaway_document_is_killed(self):
        files.write_text(self.project, 'main.tex', '\\documentclass{article}\\begin{document}\\def\\x{\\x}\\x\\end{document}')
        out = tex.compile_project(self.project, 'main.tex', 'pdflatex')
        self.assertIn('timed out after 3s', out['log'])

    def test_shell_escape_is_disabled(self):
        marker = os.path.join(tempfile.gettempdir(), 'openprism-pwned')
        if os.path.exists(marker):
            os.remove(marker)
        files.write_text(self.project, 'main.tex', '\\documentclass{article}\\begin{document}'
                         f'\\immediate\\write18{{touch {marker}}}x\\end{{document}}')
        tex.compile_project(self.project, 'main.tex', 'pdflatex')
        self.assertFalse(os.path.exists(marker), 'shell escape executed a command')

    def test_temp_dirs_are_cleaned_up(self):
        files.write_text(self.project, 'main.tex', DOC)
        before = {p for p in os.listdir(tempfile.gettempdir()) if p.startswith('openprism-compile-')}
        tex.compile_project(self.project, 'main.tex', 'pdflatex')
        after = {p for p in os.listdir(tempfile.gettempdir()) if p.startswith('openprism-compile-')}
        self.assertEqual(before, after)
