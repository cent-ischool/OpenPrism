"""arXiv metadata (port of arxivService.js and the search route)."""
import re
import xml.etree.ElementTree as ET

import httpx

NS = {'a': 'http://www.w3.org/2005/Atom'}
HEADERS = {'User-Agent': 'openprism/1.0'}


def extract_id(value):
    if not value:
        return ''
    text = str(value).strip()
    m = re.search(r'arxiv\.org/(abs|pdf|e-print)/([^?#/]+)', text, re.I)
    arxiv_id = m.group(2) if m else text
    arxiv_id = re.sub(r'\.pdf$', '', arxiv_id, flags=re.I)
    return re.sub(r'v\d+$', '', arxiv_id, flags=re.I)


def _clean(text):
    return re.sub(r'\s+', ' ', text or '').strip()


def _entries(xml_text):
    root = ET.fromstring(xml_text)
    for entry in root.findall('a:entry', NS):
        yield {
            'title': _clean(entry.findtext('a:title', '', NS)),
            'abstract': _clean(entry.findtext('a:summary', '', NS)),
            'authors': [n for n in (a.findtext('a:name', '', NS) for a in entry.findall('a:author', NS)) if n],
            'id': (entry.findtext('a:id', '', NS) or '').strip(),
            'published': (entry.findtext('a:published', '', NS) or '').strip(),
        }


def search(query, max_results=5):
    """Returns {'ok': True, 'papers': [...]} or {'ok': False, 'error': str}."""
    if not query or not str(query).strip():
        return {'ok': False, 'error': 'Missing query.'}
    limit = min(10, max(1, int(max_results or 5)))
    try:
        res = httpx.get('https://export.arxiv.org/api/query', headers=HEADERS, timeout=30,
                        params={'search_query': f'all:{query}', 'start': 0, 'max_results': limit})
    except httpx.HTTPError as exc:
        return {'ok': False, 'error': f'arXiv search failed: {exc}'}
    if res.status_code != 200:
        return {'ok': False, 'error': f'arXiv search failed: {res.status_code}'}
    papers = [{'title': e['title'], 'abstract': e['abstract'], 'authors': e['authors'], 'url': e['id'],
               'arxivId': e['id'].rsplit('/', 1)[-1] if e['id'] else ''} for e in _entries(res.text)]
    return {'ok': True, 'papers': papers}


def fetch_entry(arxiv_id):
    res = httpx.get('https://export.arxiv.org/api/query', headers=HEADERS, timeout=30, params={'id_list': arxiv_id})
    if res.status_code != 200:
        raise RuntimeError(f'arXiv API failed: {res.status_code}')
    entry = next(_entries(res.text), None)
    if not entry:
        return None
    return {'title': entry['title'], 'abstract': entry['abstract'], 'authors': entry['authors'],
            'year': entry['published'][:4], 'id': entry['id'], 'arxivId': arxiv_id}


def build_bibtex(entry):
    if not entry:
        return ''
    return (f"@article{{arxiv:{entry['arxivId']},\n  title={{{entry['title']}}},\n"
            f"  author={{{' and '.join(entry['authors'])}}},\n"
            f"  journal={{arXiv preprint arXiv:{entry['arxivId']}}},\n  year={{{entry['year'] or '2024'}}}\n}}")
