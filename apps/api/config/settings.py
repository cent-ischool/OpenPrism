"""Settings are 12-factor: everything comes from environment variables."""
import os
import sys
from datetime import timedelta
from pathlib import Path
from urllib.parse import unquote, urlparse

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def env(name, default=None, required=False):
    value = os.environ.get(name, default)
    if required and value in (None, ''):
        raise ImproperlyConfigured(f'Missing required environment variable {name}')
    return value


def env_bool(name, default=False):
    return str(env(name, str(default))).lower() in ('1', 'true', 'yes', 'on')


DEBUG = env_bool('DJANGO_DEBUG', False)
TESTING = 'test' in sys.argv

# No insecure default: a deployment that forgets the secret must fail to start.
SECRET_KEY = env('DJANGO_SECRET_KEY', 'test-only-secret' if TESTING else None, required=True)
ALLOWED_HOSTS = [h for h in env('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',') if h]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'rest_framework',
    'accounts',
    'projects',
    'templates_app',
    'jobs',
    'collab',
    'common',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
]

ROOT_URLCONF = 'config.urls'
ASGI_APPLICATION = 'config.asgi.application'
WSGI_APPLICATION = None

TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [],
    'APP_DIRS': True,
    'OPTIONS': {'context_processors': [
        'django.template.context_processors.request',
        'django.contrib.auth.context_processors.auth',
        'django.contrib.messages.context_processors.messages',
    ]},
}]


def _database():
    url = urlparse(env('DATABASE_URL', required=True))
    return {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': url.path.lstrip('/'),
        'USER': unquote(url.username or ''),
        'PASSWORD': unquote(url.password or ''),
        'HOST': url.hostname,
        'PORT': url.port or 5432,
        'CONN_MAX_AGE': 60,
    }


DATABASES = {'default': _database()}

AUTH_USER_MODEL = 'accounts.User'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True
STATIC_URL = '/static/'

# Uploads up to 200 MB, as the Node backend allowed.
DATA_UPLOAD_MAX_MEMORY_SIZE = 200 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
FILE_UPLOAD_HANDLERS = ['common.uploads.PathMemoryHandler', 'common.uploads.PathTemporaryHandler']

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': ['rest_framework_simplejwt.authentication.JWTAuthentication'],
    'DEFAULT_PERMISSION_CLASSES': ['rest_framework.permissions.IsAuthenticated'],
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
        'common.uploads.PathMultiPartParser',
    ],
    'DEFAULT_RENDERER_CLASSES': ['rest_framework.renderers.JSONRenderer'],
    'EXCEPTION_HANDLER': 'common.exceptions.ok_error_handler',
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=int(env('JWT_ACCESS_MINUTES', '30'))),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=int(env('JWT_REFRESH_DAYS', '14'))),
    'AUTH_HEADER_TYPES': ('Bearer',),
}

REDIS_URL = env('REDIS_URL', 'redis://localhost:6379/0')
CELERY_BROKER_URL = env('CELERY_BROKER_URL', REDIS_URL)
CELERY_RESULT_BACKEND = env('CELERY_RESULT_BACKEND', REDIS_URL)
CELERY_TASK_ACKS_LATE = True  # a task whose worker dies is redelivered; tasks must tolerate re-running
CELERY_WORKER_PREFETCH_MULTIPLIER = 1  # long jobs: don't let one worker hoard queued tasks
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_BROKER_TRANSPORT_OPTIONS = {'visibility_timeout': 900}  # must exceed the longest task time_limit
CELERY_TASK_ROUTES = {
    'jobs.tasks.compile_*': {'queue': 'compile'},
}
CELERY_BEAT_SCHEDULE = {
    'reap-stale-jobs': {'task': 'jobs.tasks.reap_stale_jobs', 'schedule': 60.0},
    'cleanup-old-jobs': {'task': 'jobs.tasks.cleanup_old_jobs', 'schedule': 3600.0},
}

COMPILE_TIMEOUT_SECONDS = int(env('COMPILE_TIMEOUT_SECONDS', '120'))  # per command (each pass / bibtex)
COMPILE_MAX_FILE_BYTES = int(env('COMPILE_MAX_FILE_BYTES', str(200 * 1024 * 1024)))
JOB_RUNNING_STALE_MINUTES = int(env('JOB_RUNNING_STALE_MINUTES', '10'))
JOB_QUEUED_STALE_MINUTES = int(env('JOB_QUEUED_STALE_MINUTES', '30'))
JOB_RETENTION_HOURS = int(env('JOB_RETENTION_HOURS', '24'))

S3_ENDPOINT_URL = env('S3_ENDPOINT_URL', 'http://localhost:3900')
# URL embedded in presigned links; must be reachable by the browser, not just containers.
S3_PUBLIC_ENDPOINT_URL = env('S3_PUBLIC_ENDPOINT_URL', S3_ENDPOINT_URL)
S3_REGION = env('S3_REGION', 'garage')
S3_BUCKET = env('S3_BUCKET', 'openprism')
S3_ACCESS_KEY_ID = env('S3_ACCESS_KEY_ID', required=True)
S3_SECRET_ACCESS_KEY = env('S3_SECRET_ACCESS_KEY', required=True)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {'console': {'class': 'logging.StreamHandler'}},
    'root': {'handlers': ['console'], 'level': env('LOG_LEVEL', 'INFO')},
}
