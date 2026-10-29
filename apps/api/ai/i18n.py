"""Messages shown to users in the language of the x-lang header (port of apps/backend/src/i18n)."""
import re

DICT = {
    'zh-CN': {
        'llm_error': 'LLM 未配置或调用失败：{error}。你可以在前端设置里填写 API Key/Endpoint，或配置 OPENPRISM_LLM_* 环境变量。',
        'missing_project_id_tools': '缺少 projectId，无法使用工具模式。',
        'arxiv_download_failed': 'arXiv 下载失败: {error}',
    },
    'en-US': {
        'llm_error': 'LLM is not configured or the call failed: {error}. You can set the API Key/Endpoint in the UI or configure OPENPRISM_LLM_* environment variables.',
        'missing_project_id_tools': 'Missing projectId; tools mode is unavailable.',
        'arxiv_download_failed': 'arXiv download failed: {error}',
    },
}


def get_lang(header):
    return 'zh-CN' if 'zh' in (header or '').lower() else 'en-US'


def t(lang, key, **params):
    template = DICT.get(lang, DICT['en-US']).get(key) or DICT['en-US'].get(key) or key
    return re.sub(r'\{(\w+)\}', lambda m: '' if params.get(m.group(1)) is None else str(params[m.group(1)]), template)
