from rest_framework.views import exception_handler


def _flatten(detail):
    if isinstance(detail, dict):
        return '; '.join(f'{k}: {_flatten(v)}' if k != 'detail' else _flatten(v) for k, v in detail.items())
    if isinstance(detail, (list, tuple)):
        return ' '.join(_flatten(v) for v in detail)
    return str(detail)


def ok_error_handler(exc, context):
    """Render every API error as {ok: false, error: <message>}, the shape client.ts expects."""
    response = exception_handler(exc, context)
    if response is not None:
        response.data = {'ok': False, 'error': _flatten(response.data)}
    return response
