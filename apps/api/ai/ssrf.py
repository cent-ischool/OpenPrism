"""Refuse to call URLs that resolve to internal addresses.

LLM endpoints are user-supplied. Inside a cluster, an unchecked URL could reach Postgres, Garage's admin API,
the cloud metadata service, etc. Set LLM_ALLOW_PRIVATE_ENDPOINTS=1 for local models (Ollama, vLLM on localhost).
Known gap: a hostname can be re-pointed between this check and the request (DNS rebinding); use NetworkPolicies too.
"""
import ipaddress
import socket
from urllib.parse import urlparse

from django.conf import settings


class BlockedEndpoint(ValueError):
    pass


def assert_public_url(url):
    if settings.LLM_ALLOW_PRIVATE_ENDPOINTS:
        return
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname:
        raise BlockedEndpoint('Endpoint must be an http(s) URL.')
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == 'https' else 80))
    except socket.gaierror as exc:
        raise BlockedEndpoint(f'Cannot resolve endpoint host: {exc}')
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:  # private, loopback, link-local, reserved, ...
            raise BlockedEndpoint('Endpoint resolves to a non-public address, which is not allowed.')
