"""LLM output helpers for the transfer pipeline (port of transferAgent/utils.js)."""
import json
import re

from ai import llm


class TransferError(Exception):
    """A failure that ends the transfer job; the message is shown to the user."""


def strip_code_fences(text):
    text = re.sub(r'^```(?:json|latex|tex)?\s*\n?', '', text, flags=re.I)
    text = re.sub(r'\n?```\s*$', '', text, flags=re.I)
    return text.strip()


def extract_json(text):
    """Parse the first JSON object/array in `text`, tolerating fences and surrounding prose. None if absent."""
    cleaned = strip_code_fences(text)
    try:
        return json.loads(cleaned)
    except ValueError:
        pass
    starts = [i for i in (cleaned.find('{'), cleaned.find('[')) if i != -1]
    if not starts:
        return None
    start = min(starts)
    opener = cleaned[start]
    closer = '}' if opener == '{' else ']'
    depth, in_string, escape = 0, False, False
    for i in range(start, len(cleaned)):
        ch = cleaned[i]
        if escape:
            escape = False
            continue
        if ch == '\\':
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
        if depth == 0:
            try:
                return json.loads(cleaned[start:i + 1])
            except ValueError:
                return None
    return None


def validate_schema(obj, schema):
    """schema: {field: {'type': 'string'|'array'|'object', 'required': bool}}. Returns a list of error strings."""
    if not isinstance(obj, dict):
        return ['Value is not an object']
    errors = []
    for field, rule in schema.items():
        val = obj.get(field)
        if val is None:
            if rule.get('required'):
                errors.append(f'Missing required field "{field}"')
            continue
        kind = rule['type']
        if kind == 'array' and not isinstance(val, list):
            errors.append(f'Field "{field}" should be an array')
        elif kind == 'object' and not isinstance(val, dict):
            errors.append(f'Field "{field}" should be an object')
        elif kind == 'string' and not isinstance(val, str):
            errors.append(f'Field "{field}" should be a string')
    return errors


def ask(messages, cfg):
    """One completion; raises TransferError so the job fails with the provider's message."""
    res = llm.chat(messages, cfg)
    if not res['ok']:
        raise TransferError(f"LLM call failed: {res['error']}")
    return res['content']


def ask_for_json(messages, cfg, schema=None, max_retries=2):
    """Ask for JSON, re-prompting on parse/schema failures. Returns (parsed|None, raw, retries)."""
    raw = ''
    for attempt in range(max_retries + 1):
        raw = ask(messages, cfg)
        parsed = extract_json(raw)
        if parsed is None:
            if attempt < max_retries:
                messages = [*messages, {'role': 'assistant', 'content': raw}, {'role': 'user', 'content':
                            'Your previous response could not be parsed as valid JSON. '
                            'Please output ONLY a valid JSON object with no extra text.'}]
                continue
            break
        if schema:
            errors = validate_schema(parsed, schema)
            if errors and attempt < max_retries:
                messages = [*messages, {'role': 'assistant', 'content': raw}, {'role': 'user', 'content':
                            f"The JSON was parsed but has schema issues: {'; '.join(errors)}. "
                            'Please fix and output ONLY the corrected JSON object.'}]
                continue
        return parsed, raw, attempt
    return None, raw, max_retries
