"""Transfer pipeline nodes (port of services/transferAgent/nodes/*.js).

Each node takes the Run and returns a dict of state updates; the special key `progressLog` is appended to the
job's visible log. Large intermediate values (full source text, Markdown, plan) live only in memory for the
duration of a segment; only the small keys listed in engine.PERSISTED survive between segments.
"""
import json
import posixpath
import re
import time

from jobs import compile as tex
from projects import files as pfiles
from projects import storage
from projects.paths import InvalidPath, safe_path

from . import mineru
from .llmjson import TransferError, ask, ask_for_json, extract_json, strip_code_fences, validate_schema

MAX_COMPILE_LOOPS = 5
MAX_LAYOUT_LOOPS = 3
MAX_LOG_TAIL = 8000
INPUT_RE = re.compile(r'\\(?:input|include)\{([^}]+)\}')
OUTLINE_RE = re.compile(r'\\(section|subsection|subsubsection)\*?\{([^}]*)\}')


def _fill(template, **values):
    for key, value in values.items():
        template = template.replace(f'@@{key}@@', str(value))
    return template


def resolve_inputs(project, rel, visited=None):
    """Concatenate a .tex file with everything it \\input{}s / \\include{}s, recursively."""
    visited = set() if visited is None else visited
    if rel in visited:
        return ''
    visited.add(rel)
    try:
        content = pfiles.read_text(project, rel)
    except (pfiles.FileNotFound, InvalidPath):
        return ''
    out, last = [], 0
    for m in INPUT_RE.finditer(content):
        out.append(content[last:m.start()])
        ref = m.group(1).strip()
        if not posixpath.splitext(ref)[1]:
            ref += '.tex'
        out.append(resolve_inputs(project, ref, visited))
        last = m.end()
    out.append(content[last:])
    return ''.join(out)


def parse_outline(content):
    return [{'level': m.group(1), 'title': m.group(2).strip()} for m in OUTLINE_RE.finditer(content)]


def write_with_snapshot(run, path, content):
    """Overwrite a project file, keeping the previous version in S3 (not in the project tree)."""
    try:
        old = pfiles.read_text(run.target, path)
        storage.put_bytes(run.key(f"snapshots/{path.replace('/', '_')}.{int(time.time() * 1000)}.bak"),
                          old.encode('utf-8'), 'text/plain')
    except (pfiles.FileNotFound, InvalidPath):
        pass
    pfiles.write_text(run.target, path, content)


def project_file_paths(project):
    return [i['path'] for i in pfiles.list_tree(project) if i['type'] == 'file']


# ---- legacy: LaTeX -> LaTeX ------------------------------------------------------------------------

def analyze_source(run):
    src = run.source
    all_files = project_file_paths(src)
    full = resolve_inputs(src, run.params['sourceMainFile'])
    outline = parse_outline(full)
    assets = {'bib': [], 'images': [], 'styles': [], 'other': []}
    for m in re.finditer(r'\\(?:bibliography|addbibresource)\{([^}]+)\}', full):
        for ref in (r.strip() for r in m.group(1).split(',')):
            assets['bib'].append(ref if posixpath.splitext(ref)[1] else ref + '.bib')
    for m in re.finditer(r'\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}', full):
        assets['images'].append(m.group(1).strip())
    assets['styles'] = [p for p in all_files if posixpath.splitext(p)[1].lower() in ('.sty', '.cls', '.bst')]
    return {'sourceOutline': outline, 'sourceFullContent': full, 'sourceAssets': assets,
            'progressLog': f"[analyzeSource] Parsed {len(outline)} sections, found {len(assets['bib'])} bib files, "
                           f"{len(assets['images'])} images, {len(assets['styles'])} style files."}


def analyze_target(run):
    full = resolve_inputs(run.target, run.params['targetMainFile'])
    idx = full.find('\\begin{document}')
    preamble = full if idx == -1 else full[:idx].strip()
    outline = parse_outline(full)
    return {'targetOutline': outline, 'targetPreamble': preamble, 'targetTemplateContent': full,
            'progressLog': f'[analyzeTarget] Template has {len(outline)} sections. Preamble length: {len(preamble)} chars.'}


PLAN_PROMPT = r'''You are a LaTeX template migration planner.

Given a SOURCE paper outline and a TARGET template outline, produce a JSON migration plan.

SOURCE OUTLINE:
@@SOURCE_OUTLINE@@

TARGET OUTLINE:
@@TARGET_OUTLINE@@

SOURCE ASSETS:
@@SOURCE_ASSETS@@

TARGET PREAMBLE (first 2000 chars):
@@PREAMBLE@@

Produce a JSON object with this structure:
{
  "sectionMapping": [
    { "sourceSection": "...", "targetSection": "...", "action": "map|merge|create|drop" }
  ],
  "assetStrategy": {
    "bibFiles": ["copy list"],
    "images": ["copy list"],
    "bibCommand": "bibliography|addbibresource"
  },
  "notes": "any special instructions for the migration"
}

Rules:
- Map each source section to the closest target section
- If target has no matching section, use action "create"
- If source section has no place in target, use action "drop" (rare)
- Preserve all citations, references, labels, and figure/table environments
- Keep the target preamble unchanged
- Output ONLY valid JSON, no markdown fences'''

PLAN_SCHEMA = {'sectionMapping': {'type': 'array', 'required': True}, 'assetStrategy': {'type': 'object', 'required': True},
               'notes': {'type': 'string', 'required': False}}


def draft_plan(run):
    s = run.s
    prompt = _fill(PLAN_PROMPT, SOURCE_OUTLINE=json.dumps(s['sourceOutline'], indent=2),
                   TARGET_OUTLINE=json.dumps(s['targetOutline'], indent=2),
                   SOURCE_ASSETS=json.dumps(s['sourceAssets'], indent=2), PREAMBLE=(s.get('targetPreamble') or '')[:2000])
    parsed, raw, retries = ask_for_json([{'role': 'user', 'content': prompt}], run.llm_cfg(), PLAN_SCHEMA)
    plan = parsed if isinstance(parsed, dict) else {'raw': raw, 'parseError': True, 'sectionMapping': [], 'assetStrategy': {}, 'notes': ''}
    note = f' (after {retries} retries)' if retries else ''
    return {'transferPlan': plan,
            'progressLog': f"[draftPlan] Generated migration plan with {len(plan.get('sectionMapping') or [])} section mappings{note}."}


LEGACY_PROMPT = r'''You are a LaTeX template migration expert.

TASK: Migrate the source paper content into the target template structure.

MIGRATION PLAN:
@@PLAN@@

TARGET TEMPLATE (full):
@@TARGET@@

SOURCE CONTENT (full):
@@SOURCE@@

RULES:
1. Keep the target preamble (everything before \begin{document}) EXACTLY as-is
2. Only modify content between \begin{document} and \end{document}
3. Follow the section mapping in the migration plan
4. Preserve ALL \cite{}, \ref{}, \label{} commands from the source
5. Preserve ALL figure, table, algorithm environments from the source
6. Adapt section/subsection commands to match the target template style
7. Do NOT add any content that doesn't exist in the source
8. Do NOT remove any substantive content from the source
9. If the source uses \bibliography{} but target uses \addbibresource{}, adapt accordingly
10. Output the COMPLETE .tex file content, not just the body

Output ONLY the complete LaTeX file content. No explanations, no markdown fences.'''

MINERU_PROMPT = r'''You are a LaTeX template filling expert.

TASK: Fill the following Markdown content (extracted from a PDF) into the target LaTeX template.

## MARKDOWN CONTENT (from PDF parsing):
@@MARKDOWN@@

## TARGET TEMPLATE (complete .tex file):
@@TARGET@@

## IMAGE FILES AVAILABLE:
@@IMAGES@@

## RULES:
1. Keep the target preamble (everything before \begin{document}) EXACTLY as-is
2. Only modify content between \begin{document} and \end{document}
3. Map Markdown headings to the corresponding \section{}, \subsection{} etc. in the template
4. Formulas in the Markdown are already in LaTeX format ($...$ or $$...$$) — preserve them as-is
5. Convert HTML tables in the Markdown to LaTeX \begin{tabular} environments
6. For images referenced in the Markdown, use \includegraphics{images/<filename>} wrapped in \begin{figure}...\end{figure}
7. Preserve ALL text content — do not omit any paragraphs or sections
8. Do NOT add content that doesn't exist in the Markdown
9. Output the COMPLETE .tex file content, not just the body

Output ONLY the complete LaTeX file content. No explanations, no markdown fences.'''


def apply_transfer(run):
    s, mode = run.s, run.params['mode']
    if mode == 'mineru':
        prompt = _fill(MINERU_PROMPT, MARKDOWN=s['sourceMarkdown'], TARGET=s['targetTemplateContent'],
                       IMAGES=', '.join(i['name'] for i in s.get('sourceImages') or []) or '(none)')
        label = 'applyTransfer:mineru'
    else:
        prompt = _fill(LEGACY_PROMPT, PLAN=json.dumps(s['transferPlan'], indent=2), TARGET=s['targetTemplateContent'],
                       SOURCE=s['sourceFullContent'])
        label = 'applyTransfer'
    content = strip_code_fences(ask([{'role': 'user', 'content': prompt}], run.llm_cfg()))
    write_with_snapshot(run, run.params['targetMainFile'], content)
    return {'progressLog': f"[{label}] Wrote {'content' if mode == 'mineru' else 'migrated content'} to "
                           f"{run.params['targetMainFile']} ({len(content)} chars)."}


def _copy_asset(run, rel):
    """Copy one file source -> target; on a name clash put it under assets/source/. Returns the outcome."""
    try:
        rel = safe_path(rel)
        data = pfiles.read_bytes(run.source, rel)
    except (pfiles.FileNotFound, InvalidPath):
        return 'missing'
    dest = rel
    if run.target.files.filter(path=rel).exists():
        dest = f'assets/source/{rel}'
    try:
        pfiles.write_file(run.target, dest, data)
    except IsADirectoryError:
        return 'missing'
    return 'conflict' if dest != rel else 'copied'


def copy_assets(run):
    s = run.s
    if run.params['mode'] == 'mineru':
        copied = 0
        for img in s.get('sourceImages') or []:
            pfiles.write_file(run.target, f"images/{img['name']}", storage.get_bytes(img['key']))
            copied += 1
        bibs = 0
        if run.source is not None:
            candidates = (s.get('sourceAssets') or {}).get('bib') or [
                p for p in project_file_paths(run.source) if p.lower().endswith('.bib')]
            for bib in dict.fromkeys(candidates):
                bibs += _copy_asset(run, bib) == 'copied'
        return {'progressLog': f'[copyAssets:mineru] Copied {copied} images, {bibs} bib files.'}
    assets, results = s.get('sourceAssets') or {}, []
    for rel in [*assets.get('bib', []), *assets.get('images', [])]:
        results.append(_copy_asset(run, rel))
    for sty in assets.get('styles', []):
        if not run.target.files.filter(path=sty).exists():
            results.append(_copy_asset(run, sty))
    return {'progressLog': f"[copyAssets] Copied {results.count('copied')} files, {results.count('conflict')} conflicts "
                           f"(relocated), {results.count('missing')} missing."}


# ---- compile loop ------------------------------------------------------------------------------------

def _compile(run, project, main_file):
    """Compile and return {ok, status, error, log, pdf(bytes|None)}; setup failures become ok=False."""
    try:
        out = tex.compile_project(project, main_file, run.params['engine'], progress=run.beat)
    except tex.CompileError as exc:
        return {'ok': False, 'status': -1, 'error': str(exc), 'log': '', 'pdf': None}
    return {'ok': bool(out['pdf']), 'status': out['status'], 'log': out['log'], 'pdf': out['pdf'],
            'error': None if out['pdf'] else 'No PDF generated.'}


def compile_node(run):
    out = _compile(run, run.target, run.params['targetMainFile'])
    attempt = run.s.get('compileAttempt', 0) + 1
    pdf_key = ''
    if out['ok']:
        pdf_key = run.key('output.pdf')
        storage.put_bytes(pdf_key, out['pdf'], 'application/pdf')
    result = {'ok': out['ok'], 'status': out['status'], 'error': out['error'], 'log': out['log'][-50000:], 'pdfKey': pdf_key}
    return {'compileResult': result, 'compileAttempt': attempt,
            'progressLog': f"[compile] Attempt {attempt}: {'SUCCESS' if out['ok'] else 'FAILED'} (exit {out['status']})."}


FIX_COMPILE_PROMPT = r'''You are a LaTeX compilation error fixer.

The following LaTeX file failed to compile. Fix the errors and return the corrected COMPLETE file.

COMPILE LOG (last @@TAIL@@ chars):
@@LOG@@

CURRENT FILE (@@FILE@@):
@@TEX@@

Common fixes:
- Missing packages: add \usepackage{...} in preamble
- Undefined commands: replace with standard alternatives or define them
- Mismatched braces: fix bracket/brace pairing
- Missing files: comment out or remove references to missing files
- Encoding issues: ensure UTF-8 compatibility

Output ONLY the complete corrected LaTeX file. No explanations, no markdown fences.'''


def fix_compile(run):
    main = run.params['targetMainFile']
    prompt = _fill(FIX_COMPILE_PROMPT, TAIL=MAX_LOG_TAIL, LOG=(run.s['compileResult'].get('log') or '')[-MAX_LOG_TAIL:],
                   FILE=main, TEX=pfiles.read_text(run.target, main))
    fixed = strip_code_fences(ask([{'role': 'user', 'content': prompt}], run.llm_cfg()))
    write_with_snapshot(run, main, fixed)
    return {'progressLog': f"[fixCompile] Applied LLM fix for compile attempt {run.s.get('compileAttempt')}."}


# ---- layout check loop -------------------------------------------------------------------------------

def request_page_images(run):
    return {'progressLog': '[requestPageImages] Compilation succeeded. Waiting for frontend to submit page screenshots.'}


LAYOUT_PROMPT = r'''You are a LaTeX document layout reviewer.

Examine the PDF page screenshots and identify layout issues.

Return a JSON object:
{
  "summary": "brief overall assessment",
  "issues": [
    {
      "page": 1,
      "severity": "high|medium|low",
      "type": "overflow|overlap|spacing|alignment|missing_content",
      "description": "what is wrong",
      "suggestion": "how to fix in LaTeX"
    }
  ]
}

Focus on:
- Text overflow (content going beyond margins)
- Overlapping elements (figures/tables overlapping text)
- Missing content (blank pages, cut-off text)
- Severely broken formatting

Ignore minor aesthetic differences. Only flag issues that affect readability.
Output ONLY valid JSON.'''

LAYOUT_SCHEMA = {'summary': {'type': 'string', 'required': False}, 'issues': {'type': 'array', 'required': True}}


def check_layout(run):
    s = run.s
    attempt = s.get('layoutAttempt', 0) + 1
    images = []
    if s.get('pageImagesKey'):
        images = json.loads(storage.get_bytes(s['pageImagesKey']))
    if not images:
        return {'layoutCheckResult': {'ok': True, 'issues': []}, 'layoutAttempt': attempt,
                'progressLog': '[checkLayout] No page images provided, skipping layout check.'}
    parts = [{'type': 'text', 'text': LAYOUT_PROMPT}] + [
        {'type': 'image_url', 'image_url': {'url': f"data:{img.get('mime') or 'image/png'};base64,{img['base64']}"}}
        for img in images]
    first = [{'role': 'user', 'content': parts}]
    messages, result, retries = first, None, 0
    for attempt_no in range(3):
        raw = ask(messages, run.llm_cfg())
        parsed = extract_json(raw)
        if parsed is None:
            if attempt_no < 2:
                messages = [*first, {'role': 'assistant', 'content': raw}, {'role': 'user', 'content':
                            'Your previous response could not be parsed as valid JSON. '
                            'Please output ONLY a valid JSON object with no extra text.'}]
                retries += 1
                continue
            result = {'ok': False, 'issues': [], 'parseError': True, 'raw': raw}  # parse failure is NOT "ok"
            break
        errors = validate_schema(parsed, LAYOUT_SCHEMA)
        if errors and attempt_no < 2:
            messages = [*first, {'role': 'assistant', 'content': raw}, {'role': 'user', 'content':
                        f"The JSON was parsed but has schema issues: {'; '.join(errors)}. "
                        'Please fix and output ONLY the corrected JSON object.'}]
            retries += 1
            continue
        result = parsed
        break
    result = result or {'ok': False, 'issues': [], 'parseError': True}
    issues = result.get('issues') or []
    has_high = any(isinstance(i, dict) and i.get('severity') == 'high' for i in issues)
    note = (f' (after {retries} retries)' if retries else '') + (' [JSON parse failed]' if result.get('parseError') else '')
    # Same precedence as the Node code ({ok: !hasIssues, ...result}): a parse failure (ok: false) must stay not-ok.
    return {'layoutCheckResult': {'ok': not has_high, **result}, 'layoutAttempt': attempt,
            'progressLog': f"[checkLayout] Found {len(issues)} issues, {'needs fix' if has_high else 'acceptable'}{note}."}


FIX_LAYOUT_PROMPT = r'''You are a LaTeX layout fixer.

The following LaTeX file has layout issues identified by visual inspection.
Fix the issues and return the corrected COMPLETE file.

LAYOUT ISSUES:
@@ISSUES@@

CURRENT FILE (@@FILE@@):
@@TEX@@

Common layout fixes:
- Overflow: adjust figure width, use \resizebox, or \adjustbox
- Overlap: use [H] or [htbp] float placement, add \clearpage
- Spacing: adjust \vspace, \baselineskip, or use \newpage
- Tables too wide: use tabularx, resizebox, or reduce columns

Output ONLY the complete corrected LaTeX file. No explanations, no markdown fences.'''


def fix_layout(run):
    main = run.params['targetMainFile']
    issues = (run.s.get('layoutCheckResult') or {}).get('issues') or []
    prompt = _fill(FIX_LAYOUT_PROMPT, ISSUES=json.dumps(issues, indent=2), FILE=main, TEX=pfiles.read_text(run.target, main))
    fixed = strip_code_fences(ask([{'role': 'user', 'content': prompt}], run.llm_cfg()))
    write_with_snapshot(run, main, fixed)
    return {'progressLog': f"[fixLayout] Applied LLM fix for {len(issues)} layout issues (attempt {run.s.get('layoutAttempt')})."}


def finalize(run):
    result = run.s.get('compileResult') or {}
    ok = bool(result.get('ok') and result.get('pdfKey'))
    status = 'success' if ok else 'failed'
    return {'status': status, 'error': None if result.get('pdfKey') else (result.get('error') or 'No PDF generated after all attempts.'),
            'progressLog': f"[finalize] Transfer {status}. Compile attempts: {run.s.get('compileAttempt', 0)}, "
                           f"Layout attempts: {run.s.get('layoutAttempt', 0)}."}


# ---- MinerU: PDF -> Markdown -------------------------------------------------------------------------

def compile_source(run):
    s = run.s
    if s.get('sourcePdfKey'):
        return {'progressLog': f"[compileSource] Using provided PDF: {s['sourcePdfKey']}"}
    if run.source is None or not run.params.get('sourceMainFile'):
        raise TransferError('No source PDF available. Upload a PDF first or provide sourceProjectId + sourceMainFile.')
    out = _compile(run, run.source, run.params['sourceMainFile'])
    if not out['ok']:
        raise TransferError(f"Source compilation failed: {out['error'] or out['log'] or 'unknown error'}")
    key = run.key('source.pdf')
    storage.put_bytes(key, out['pdf'], 'application/pdf')
    return {'sourcePdfKey': key, 'progressLog': f'[compileSource] Compiled source project to PDF ({key}).'}


def parse_pdf_with_mineru(run):
    cfg = mineru.resolve_config(run.params.get('mineruConfig'), run.secrets.get('mineruToken', ''))
    last = {}

    def on_progress(info):
        if info != last:  # log (and heartbeat) only when MinerU's state changes
            last.clear()
            last.update(info)
            run.beat(f"MinerU: {info.get('phase')}" + (f" {info['state']}" if info.get('state') else '')
                     + (f" ({info['extractedPages']}/{info['totalPages']} pages)" if info.get('totalPages') else ''))

    out = mineru.parse_pdf(storage.get_bytes(run.s['sourcePdfKey']), 'source.pdf', cfg, on_progress)
    images = []
    for name, data in out['images']:
        key = run.key(f'mineru/{name}')
        storage.put_bytes(key, data)
        images.append({'name': name, 'key': key})
    return {'sourceMarkdown': out['markdown'], 'sourceImages': images,
            'progressLog': f"[parsePdfWithMineru] Parsed PDF: {len(out['markdown'])} chars markdown, {len(images)} images."}


NODES = {
    'analyzeSource': analyze_source, 'analyzeTarget': analyze_target, 'draftPlan': draft_plan,
    'applyTransfer': apply_transfer, 'copyAssets': copy_assets, 'compile': compile_node, 'fixCompile': fix_compile,
    'requestPageImages': request_page_images, 'checkLayout': check_layout, 'fixLayout': fix_layout, 'finalize': finalize,
    'compileSource': compile_source, 'parsePdfWithMineru': parse_pdf_with_mineru,
}
