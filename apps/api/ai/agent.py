"""Writing assistant: chat, direct JSON completion, and a tool-calling agent that proposes patches.

Port of routes/agent.js + services/agentService.js. The tool loop talks to the OpenAI tools API directly
(LangChain's AgentExecutor was only used for this loop). Patches are never written: they are returned for the
user to confirm in the editor.
"""
import json

from projects import files as pfiles
from projects.models import ProjectFile
from projects.paths import InvalidPath, safe_path

from . import arxiv, llm
from .i18n import t
from .patches import PatchError, apply_patch, extract_path, make_patch

MAX_STEPS = 15
READ_LIMIT = 20000

SYSTEM_TOOLS = ' '.join([
    'You are a LaTeX paper assistant for OpenPrism.',
    'You can read files and propose patches via tools, and you may call tools multiple times.',
    'If a request affects multiple files (e.g., sections + bib), inspect and update all relevant files.',
    'You can use arxiv_search to find papers and arxiv_bibtex to generate BibTeX.',
    'Never assume writes are applied; use propose_patch and wait for user confirmation.',
    'Use apply_patch for localized edits; use propose_patch for full-file rewrites.',
    'Be concise. Provide a short summary in the final response.'])

TOOL_SPECS = [
    ('read_file', 'Read a UTF-8 file from the project. Input: { path } (relative to project root).',
     {'path': {'type': 'string'}}, ['path']),
    ('list_files', 'List files under a directory. Input: { dir } (relative path, optional).',
     {'dir': {'type': 'string'}}, []),
    ('propose_patch', 'Propose a full file rewrite. Input: { path, content }. This does NOT write. It returns a patch for user confirmation.',
     {'path': {'type': 'string'}, 'content': {'type': 'string'}}, ['path', 'content']),
    ('apply_patch', 'Apply a unified diff to a file and propose changes. Input: { patch, path? }. This does NOT write.',
     {'patch': {'type': 'string'}, 'path': {'type': 'string'}}, ['patch']),
    ('get_compile_log', 'Return the latest compile log from the client (read-only). Input: { }.', {}, []),
    ('arxiv_search', 'Search arXiv papers. Input: { query, maxResults? }.',
     {'query': {'type': 'string'}, 'maxResults': {'type': 'number'}}, ['query']),
    ('arxiv_bibtex', 'Generate BibTeX for an arXiv paper. Input: { arxivId }.', {'arxivId': {'type': 'string'}}, ['arxivId']),
]
TOOLS = [{'type': 'function', 'function': {'name': n, 'description': d,
                                           'parameters': {'type': 'object', 'properties': p, 'required': r}}}
         for n, d, p, r in TOOL_SPECS]


def _llm_failure(lang, res):
    return {'ok': False, 'reply': t(lang, 'llm_error', error=res.get('error') or 'unknown error'), 'suggestion': ''}


def chat_mode(p, cfg, lang):
    history = [h for h in (p.get('history') or []) if isinstance(h, dict) and h.get('role') in ('user', 'assistant')
               and isinstance(h.get('content'), str)]
    system = ' '.join(['You are a helpful academic writing assistant.',
                       'This is chat-only mode: do not propose edits, patches, or JSON.', 'Respond concisely and helpfully.'])
    user = '\n\n'.join(x for x in [
        f"User Prompt: {p['prompt']}" if p.get('prompt') else '',
        f"Selection (read-only):\n{p['selection']}" if p.get('selection') else '',
        '' if p.get('selection') else (f"Current File (read-only):\n{p['content']}" if p.get('content') else ''),
        f"Compile Log (read-only):\n{p['compileLog']}" if p.get('compileLog') else ''] if x)
    res = llm.chat([{'role': 'system', 'content': system}, *history, {'role': 'user', 'content': user}], cfg)
    if not res['ok']:
        return _llm_failure(lang, res)
    return {'ok': True, 'reply': res['content'], 'suggestion': ''}


def direct_mode(p, cfg, lang):
    task = p.get('task') or 'polish'
    if task == 'autocomplete':
        system = ' '.join(['You are an autocomplete engine for LaTeX.', 'Only return JSON with keys: reply, suggestion.',
                           'suggestion must be the continuation text after the cursor.',
                           'Do not include explanations or code fences.'])
    else:
        system = ' '.join(['You are a LaTeX writing assistant for academic papers.',
                           'Return a concise response and a suggested rewrite for the selection or full content.',
                           'Output in JSON with keys: reply, suggestion.'])
    user = '\n\n'.join(x for x in [
        f'Task: {task}', 'Mode: direct',
        f"User Prompt: {p['prompt']}" if p.get('prompt') else '',
        f"Selection:\n{p['selection']}" if p.get('selection') else '',
        '' if p.get('selection') else f"Full Content:\n{p.get('content') or ''}"] if x)
    res = llm.chat([{'role': 'system', 'content': system}, {'role': 'user', 'content': user}], cfg)
    if not res['ok']:
        return _llm_failure(lang, res)
    try:
        parsed = json.loads(res['content'])
        return {'ok': True, 'reply': parsed.get('reply') or '', 'suggestion': parsed.get('suggestion') or ''}
    except (ValueError, AttributeError):
        return {'ok': True, 'reply': res['content'], 'suggestion': ''}


class ToolBox:
    def __init__(self, project, compile_log):
        self.project, self.compile_log, self.patches = project, compile_log, []

    def _read(self, path):
        try:
            return pfiles.read_text(self.project, path)
        except pfiles.FileNotFound:
            return None

    def call(self, name, args):
        """Run a tool; failures come back as text so the model can correct itself."""
        fn = getattr(self, f'tool_{name}', None)
        if fn is None:
            return f'Error: unknown tool {name}'
        try:
            return fn(**args)
        except (TypeError, PatchError, InvalidPath, pfiles.FileNotFound, RuntimeError, ValueError, IsADirectoryError) as exc:
            return f'Error: {exc}'

    def tool_read_file(self, path):
        content = self._read(path)
        if content is None:
            raise pfiles.FileNotFound(f'File not found: {path}')
        return content[:READ_LIMIT]

    def tool_list_files(self, dir=None):
        prefix = safe_path(dir) + '/' if dir else ''
        names = [i['path'] for i in pfiles.list_tree(self.project) if i['type'] == 'file' and i['path'].startswith(prefix)]
        return json.dumps({'files': [n[len(prefix):] for n in names]})

    def tool_propose_patch(self, path, content):
        path = safe_path(path)
        original = self._read(path) or ''
        self.patches.append({'path': path, 'original': original, 'content': content, 'diff': make_patch(path, original, content)})
        return f'Patch prepared for {path}. Awaiting user confirmation.'

    def tool_apply_patch(self, patch, path=None):
        path = safe_path(path or extract_path(patch) or '')
        original = self._read(path)
        if original is None:
            raise pfiles.FileNotFound(f'File not found: {path}')
        patched = apply_patch(original, patch)
        self.patches.append({'path': path, 'original': original, 'content': patched, 'diff': make_patch(path, original, patched)})
        return f'Patch applied in memory for {path}. Awaiting user confirmation.'

    def tool_get_compile_log(self):
        return self.compile_log or 'No compile log provided.'

    def tool_arxiv_search(self, query, maxResults=None):
        res = arxiv.search(query, maxResults)
        if not res['ok']:
            raise RuntimeError(res['error'])
        return json.dumps({'papers': res['papers']})

    def tool_arxiv_bibtex(self, arxivId):
        arxiv_id = arxiv.extract_id(arxivId)
        if not arxiv_id:
            raise ValueError('Invalid arXiv ID')
        entry = arxiv.fetch_entry(arxiv_id)
        if not entry:
            raise RuntimeError('No arXiv metadata found')
        return arxiv.build_bibtex(entry)


def tools_mode(p, project, cfg, lang):
    if project is None:
        return {'ok': False, 'reply': t(lang, 'missing_project_id_tools'), 'patches': []}
    if not llm.resolve_config(cfg)['api_key']:
        return {'ok': False, 'reply': 'OPENPRISM_LLM_API_KEY not set', 'patches': []}
    box = ToolBox(project, p.get('compileLog'))
    user = '\n\n'.join(x for x in [
        f"Task: {p.get('task') or 'polish'}",
        f"Active file: {p['activePath']}" if p.get('activePath') else '',
        f"User prompt: {p['prompt']}" if p.get('prompt') else '',
        f"Selection:\n{p['selection']}" if p.get('selection') else '',
        f"Compile log:\n{p['compileLog']}" if p.get('compileLog') else ''] if x)
    messages = [{'role': 'system', 'content': SYSTEM_TOOLS}, {'role': 'user', 'content': user}]
    for _ in range(MAX_STEPS):
        res = llm.chat_raw(messages, cfg, tools=TOOLS)
        if not res['ok']:
            return {'ok': False, 'reply': res['error'], 'patches': box.patches}
        message = res['message']
        calls = message.get('tool_calls') or []
        if not calls:
            return {'ok': True, 'reply': message.get('content') or '', 'patches': box.patches}
        messages.append({'role': 'assistant', 'content': message.get('content'), 'tool_calls': calls})
        for call in calls:
            try:
                args = json.loads(call['function'].get('arguments') or '{}')
            except ValueError:
                args = None
            result = box.call(call['function']['name'], args) if isinstance(args, dict) else 'Error: tool arguments were not valid JSON'
            messages.append({'role': 'tool', 'tool_call_id': call['id'], 'content': str(result)})
    return {'ok': True, 'reply': f'Stopped after {MAX_STEPS} steps without a final answer.', 'patches': box.patches}


def run(p, project, cfg, lang):
    if (p.get('interaction') or 'agent') == 'chat':
        return chat_mode(p, cfg, lang)
    if p.get('mode') == 'tools':
        return tools_mode(p, project, cfg, lang)
    return direct_mode(p, cfg, lang)
