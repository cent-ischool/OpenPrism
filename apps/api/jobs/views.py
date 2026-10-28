from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, authentication_classes
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from projects import storage
from projects.access import QueryTokenJWTAuthentication, get_project
from projects.models import Membership
from projects.paths import InvalidPath, safe_path

from .compile import SUPPORTED_ENGINES
from .models import Job
from .tasks import ACTIVE, compile_project

MAX_ACTIVE_COMPILES_PER_USER = 3


def fail(message, status=200):
    return Response({'ok': False, 'error': message}, status=status)


def get_job(request, job_id):
    job = get_object_or_404(Job.objects.select_related('project'), pk=job_id)
    allowed = job.user_id == request.user.id or (
        job.project_id and Membership.objects.filter(workspace_id=job.project.workspace_id, user=request.user).exists())
    if not allowed:
        raise NotFound('Job not found')
    return job


def job_json(job):
    out = {
        'ok': True, 'jobId': str(job.id), 'type': job.type, 'status': job.status,
        'progressLog': job.progress_log, 'error': job.error,
        'createdAt': job.created_at.isoformat(), 'updatedAt': job.updated_at.isoformat(),
    }
    if job.status not in ACTIVE and job.type == Job.COMPILE:
        r = job.result
        out['result'] = {
            'log': r.get('log', ''), 'status': r.get('exitStatus'), 'engine': r.get('engine'), 'mainFile': r.get('mainFile'),
            'pdfUrl': f'/api/jobs/{job.id}/pdf' if r.get('pdfKey') else None,
        }
    if job.status not in ACTIVE and job.type != Job.COMPILE:
        out['result'] = job.result.get('body')  # the endpoint's response body; never contains secrets
    return out


@api_view(['POST'])
def start_compile(request):
    """Queue a compilation. Poll GET /api/jobs/<jobId>, then fetch the PDF from result.pdfUrl."""
    project_id = request.data.get('projectId')
    main_file = request.data.get('mainFile') or 'main.tex'
    engine = request.data.get('engine') or 'pdflatex'
    if not project_id:
        return fail('Missing projectId.')
    if engine not in SUPPORTED_ENGINES:
        return fail(f"Unsupported engine: {engine}. Supported: {', '.join(SUPPORTED_ENGINES)}")
    project = get_project(request, project_id)
    try:
        main_file = safe_path(main_file)
    except InvalidPath:
        return fail('Invalid main file path.')
    if not project.files.filter(path=main_file).exclude(kind='dir').exists():
        return fail(f'Main file not found: {main_file}')
    active = Job.objects.filter(user=request.user, type=Job.COMPILE, status__in=ACTIVE).count()
    if active >= MAX_ACTIVE_COMPILES_PER_USER:
        return fail('Too many compilations in progress. Wait for one to finish.', 429)
    job = Job.objects.create(type=Job.COMPILE, user=request.user, project=project,
                             params={'mainFile': main_file, 'engine': engine}, progress_log=['Queued'])
    compile_project.delay(str(job.id))
    return Response({'ok': True, 'jobId': str(job.id), 'status': job.status})


@api_view(['GET'])
def job_status(request, pk):
    return Response(job_json(get_job(request, pk)))


@api_view(['GET'])
@authentication_classes([QueryTokenJWTAuthentication])
def job_pdf(request, pk):
    job = get_job(request, pk)
    key = job.result.get('pdfKey')
    if not key:
        raise NotFound('No PDF for this job')
    resp = HttpResponse(storage.get_bytes(key), content_type='application/pdf')
    resp['X-Content-Type-Options'] = 'nosniff'
    return resp
