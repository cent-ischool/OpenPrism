import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib
from datetime import timedelta
from unittest import mock, skipUnless

from django.conf import settings
from django.test import TestCase, override_settings
from django.utils import timezone

from common import secrets as job_secrets
from projects import files, storage
from projects.models import Project
from projects.test_api import ApiBase, client_for, make_user

from config.hardening import make_undumpable

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


class ScrubbedEnvironmentTests(TestCase):
    """No credentials may reach the processes that run user documents."""

    def test_tex_env_is_an_allow_list(self):
        secrets = {'DATABASE_URL': 'postgres://u:pw@db/x', 'DJANGO_SECRET_KEY': 'k', 'S3_SECRET_ACCESS_KEY': 's3',
                   'REDIS_URL': 'redis://:pw@r', 'OPENPRISM_LLM_API_KEY': 'sk-x', 'PATH': '/usr/bin', 'LANG': 'C.UTF-8'}
        with mock.patch.dict(os.environ, secrets):
            env = tex._tex_env('/tmp/work')
        self.assertEqual(env['PATH'], '/usr/bin')
        self.assertEqual(env['HOME'], '/tmp/work')
        self.assertEqual((env['shell_escape'], env['openin_any'], env['openout_any']), ('f', 'p', 'p'))
        self.assertEqual(tex._tex_env('/tmp/work', 'lualatex')['openin_any'], 'a')   # luaotfload cannot run in paranoid mode
        blob = json.dumps(env)
        for secret in ('postgres://', 'pw@', 's3', 'sk-x', 'DJANGO_SECRET_KEY'):
            self.assertNotIn(secret, blob)

    def test_run_command_requires_an_explicit_environment(self):
        with self.assertRaises(TypeError):
            tex.run_command(['true'], '/tmp', tex.LogBuffer())  # would have inherited the worker's secrets

    @skipUnless(os.path.isdir('/proc/self'), 'needs Linux /proc')
    def test_undumpable_process_hides_its_environment_from_children(self):
        code = ("import os, subprocess; from config.hardening import make_undumpable; os.environ['SECRET_PROBE'] = 'hunter2';"
                "print('set', make_undumpable());"
                "r = subprocess.run(['cat', f'/proc/{os.getpid()}/environ'], capture_output=True);"
                "print('rc', r.returncode, 'leaked', b'hunter2' in r.stdout)")
        out = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, cwd=str(settings.BASE_DIR),
                             env={**os.environ, 'DJANGO_SETTINGS_MODULE': 'config.settings'}).stdout
        self.assertIn('set True', out)
        self.assertIn('leaked False', out)
        self.assertNotIn('rc 0', out)  # the read was refused, not merely empty


@skipUnless(HAS_TEX, 'needs TeX Live: docker compose run --rm worker-tex python manage.py test jobs')
class HostileDocumentTests(TestCase):
    """Documents written by an attacker who can edit a project (an invited guest is enough)."""

    def setUp(self):
        user = make_user('attacker@example.com')
        self.project = Project.objects.create(workspace=user.memberships.first().workspace, name='p')
        self.addCleanup(files.delete_project_files, self.project)

    def compile(self, tex_source, engine='pdflatex', extra=None):
        files.write_text(self.project, 'main.tex', tex_source)
        for path, content in (extra or {}).items():
            files.write_text(self.project, path, content)
        return tex.compile_project(self.project, 'main.tex', engine)

    PROBE = (r'\documentclass{article}\begin{document}\makeatletter\newread\f'
             r'\def\probe#1#2{\openin\f=#2\relax\ifeof\f\typeout{[#1] BLOCKED}\else\read\f to\l\typeout{[#1] READ: \meaning\l}\closein\f\fi}'
             r'\probe{passwd}{/etc/passwd}\probe{environ}{/proc/self/environ}\probe{parent}{/proc/PPID/environ}\end{document}')

    def test_tex_cannot_read_system_files_or_process_environments(self):
        out = self.compile(self.PROBE.replace('PPID', str(os.getpid())))
        probes = [l for l in out['log'].splitlines() if l.startswith('[') and ('READ' in l or 'BLOCKED' in l)]
        self.assertTrue(probes, out['log'][-800:])
        self.assertTrue(all('BLOCKED' in l for l in probes), probes)   # /etc/passwd, own and parent environ
        self.assertNotIn('root:x', out['log'])

    def test_project_files_are_still_readable(self):
        out = self.compile(r'\documentclass{article}\begin{document}\input{part}\end{document}', extra={'part.tex': 'Included fine.'})
        self.assertTrue(out['pdf'])

    def test_latexmkrc_in_a_project_is_not_executed(self):
        marker = os.path.join(tempfile.gettempdir(), f'openprism-rce-{os.getpid()}')
        self.addCleanup(lambda: os.path.exists(marker) and os.remove(marker))
        out = self.compile(DOC, engine='latexmk', extra={'latexmkrc': f'system("touch {marker}");\n', '.latexmkrc': f'system("touch {marker}");\n'})
        self.assertFalse(os.path.exists(marker), 'a project latexmkrc ran code in the worker')
        self.assertTrue(out['pdf'], out['log'][-500:])                # latexmk itself still works

    def test_lua_cannot_read_the_workers_environment(self):
        make_undumpable()  # what the Celery worker does at startup; this test process plays the worker
        os.environ['OPENPRISM_PROBE_SECRET'] = 'hunter2-probe'
        self.addCleanup(os.environ.pop, 'OPENPRISM_PROBE_SECRET', None)
        out = self.compile('\\documentclass{article}\\begin{document}\n\\directlua{local e = io.open("/proc/%d/environ") '
                           'if e then texio.write_nl("LUAENV " .. e:read("*a"):sub(1, 3000)) else texio.write_nl("LUABLOCKED") end}\n\\end{document}' % os.getpid(),
                           engine='lualatex')
        self.assertIn('LUABLOCKED', out['log'])
        self.assertNotIn('hunter2-probe', out['log'])

    def test_every_engine_still_compiles_under_the_restrictions(self):
        for engine in ('pdflatex', 'xelatex', 'lualatex', 'latexmk'):
            body = r'\documentclass{article}\usepackage{amsmath,graphicx}\begin{document}Hello $x^2$ \input{part}\end{document}'
            out = self.compile(body, engine=engine, extra={'part.tex': 'included'})
            self.assertTrue(out['pdf'], f"{engine}: {out['log'][-400:]}")

    def test_biber_ignores_project_configuration(self):
        files.write_text(self.project, 'refs.bib', '@book{k, author={A. Author}, title={A Title}, year={2020}, publisher={P}}')
        out = self.compile('\\documentclass{article}\\usepackage[backend=biber]{biblatex}\\addbibresource{refs.bib}\\begin{document}See \\cite{k}.\\printbibliography\\end{document}',
                           extra={'biber.conf': '<this is not valid biber configuration>'})
        self.assertIn('This is Biber', out['log'])
        self.assertTrue(out['pdf'], out['log'][-600:])
