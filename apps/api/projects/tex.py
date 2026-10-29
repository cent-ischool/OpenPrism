"""Helpers for merging LaTeX template bodies (port of texUtils.js)."""
BEGIN, END = '\\begin{document}', '\\end{document}'


def extract_document_body(tex):
    start, end = tex.find(BEGIN), tex.rfind(END)
    if start == -1 or end == -1 or end <= start:
        return ''
    return tex[start + len(BEGIN):end].strip()


def merge_template_body(template, body):
    start, end = template.find(BEGIN), template.rfind(END)
    if start == -1 or end == -1 or end <= start:
        return template
    return f"{template[:start + len(BEGIN)]}{chr(10) + body + chr(10) if body else chr(10)}{template[end:]}"
