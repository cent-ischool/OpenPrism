"""Multipart parsing that preserves relative upload paths.

Django (and DRF) reduce an uploaded filename to its basename, but the frontend sends folder structure
in the filename (`form.append('files', file, 'figs/a.png')`). The parser below keeps the sanitised path
and exposes it as `uploaded_file.full_path`.
"""
import html

from django.core.files.uploadhandler import MemoryFileUploadHandler, TemporaryFileUploadHandler
from django.http.multipartparser import MultiPartParser as DjangoMultiPartParser
from django.http.multipartparser import MultiPartParserError
from rest_framework.exceptions import ParseError
from rest_framework.parsers import DataAndFiles, MultiPartParser

from projects.paths import sanitize_upload_path


class PathPreservingDjangoParser(DjangoMultiPartParser):
    def sanitize_file_name(self, file_name):
        return sanitize_upload_path(html.unescape(file_name or ''))


class PathMemoryHandler(MemoryFileUploadHandler):
    def file_complete(self, file_size):
        f = super().file_complete(file_size)
        if f is not None:
            f.full_path = self.file_name
        return f


class PathTemporaryHandler(TemporaryFileUploadHandler):
    def file_complete(self, file_size):
        f = super().file_complete(file_size)
        f.full_path = self.file_name
        return f


class PathMultiPartParser(MultiPartParser):
    def parse(self, stream, media_type=None, parser_context=None):
        parser_context = parser_context or {}
        request = parser_context['request']
        meta = request.META.copy()
        meta['CONTENT_TYPE'] = media_type
        upload_handlers = request.upload_handlers
        encoding = parser_context.get('encoding', 'utf-8')
        try:
            parser = PathPreservingDjangoParser(meta, stream, upload_handlers, encoding)
            data, files = parser.parse()
            return DataAndFiles(data, files)
        except MultiPartParserError as exc:
            raise ParseError(f'Multipart form parse error - {exc}')


def upload_path(uploaded):
    """The sanitised relative path of an uploaded file."""
    return getattr(uploaded, 'full_path', None) or sanitize_upload_path(uploaded.name)
