"""Subprocess entry point: render a table to a PNG using LLM-written matplotlib code.

Run as `python -I plot_runner.py payload.json` with a scrubbed environment (see plot.py). The LLM code runs with
a whitelist of builtins; plot.py has already rejected imports and dunder access. This is defence in depth, not a
sandbox: real isolation is the container (no secrets, no egress).
"""
import builtins
import importlib.util
import json
import os
import re
import sys

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402

pd = sns = np = None
if importlib.util.find_spec('pandas'):
    import pandas as pd  # noqa: E402
if importlib.util.find_spec('seaborn'):
    import seaborn as sns  # noqa: E402
if importlib.util.find_spec('numpy'):
    import numpy as np  # noqa: E402

SAFE_BUILTINS = {name: getattr(builtins, name) for name in (
    'abs', 'all', 'any', 'bool', 'dict', 'enumerate', 'filter', 'float', 'int', 'isinstance', 'len', 'list', 'map',
    'max', 'min', 'print', 'range', 'reversed', 'round', 'set', 'slice', 'sorted', 'str', 'sum', 'tuple', 'zip',
    'True', 'False', 'None', 'ValueError', 'TypeError', 'KeyError', 'IndexError', 'Exception')}


def parse_table(latex):
    m = re.search(r'\\begin{tabular}.*?\\end{tabular}', latex, re.S)
    if m:
        latex = m.group(0)
    latex = re.sub(r'\\begin{tabular}{[^}]*}', '', latex)
    latex = re.sub(r'\\end{tabular}', '', latex)
    latex = re.sub(r'\\(toprule|midrule|bottomrule|hline)', '', latex)
    latex = latex.replace('\\\n', '\\\\')
    rows = [r.strip() for r in latex.split('\\\\') if r.strip()]
    data = []
    for row in rows:
        if row.strip().startswith('%'):
            continue
        raw_cells = [c.strip() for c in re.split(r'(?<!\\)&', row)]  # split on unescaped &
        if len(raw_cells) == 1 and raw_cells[0] == '':
            continue
        expanded = []
        for cell in raw_cells:
            m = re.match(r'\\multicolumn\{(\d+)\}\{[^}]*\}\{(.+)\}', cell)
            if m:
                expanded.append(m.group(2).strip())
                expanded.extend([''] * (int(m.group(1)) - 1))
            else:
                m2 = re.match(r'\\multirow\{[^}]*\}\{[^}]*\}\{(.+)\}', cell)
                expanded.append(m2.group(1).strip() if m2 else cell)
        data.append(expanded)
    return data


def is_number(val):
    try:
        float(val)
        return True
    except Exception:
        return False


def build_table(latex):
    data = parse_table(latex)
    if not data:
        raise RuntimeError('No table rows parsed')
    max_cols = max(len(r) for r in data)
    if all(not is_number(c) for c in data[0]):
        header, rows = data[0], data[1:]
    else:
        header, rows = [f'col{i + 1}' for i in range(max_cols)], data
    if len(header) < max_cols:
        header = header + [f'col{i + 1}' for i in range(len(header), max_cols)]
    elif len(header) > max_cols:
        header = header[:max_cols]
    if not rows:
        raise RuntimeError('No data rows after header')
    rows = [(r + [''] * (max_cols - len(r)))[:max_cols] for r in rows]
    return header, rows


def main(payload_path):
    with open(payload_path, 'r', encoding='utf-8') as f:
        payload = json.load(f)
    latex, title = payload.get('tableLatex', ''), payload.get('title', '')
    output_path, plot_code = payload.get('outputPath', ''), payload.get('plotCode', '')
    if not latex or not output_path:
        raise RuntimeError('Missing input or output path')
    header, rows = build_table(latex)
    if not plot_code:
        raise RuntimeError('Missing plot code')

    plt.figure(figsize=(6, 4))
    df = df_numeric = None
    if pd is not None:
        df = pd.DataFrame(rows, columns=header)
        df_numeric = df.apply(lambda col: pd.to_numeric(col, errors='coerce'))
    namespace = {'__builtins__': SAFE_BUILTINS, 'df': df, 'df_numeric': df_numeric, 'rows': rows,
                 'header': header, 'sns': sns, 'plt': plt, 'np': np, 'pd': pd}
    exec(compile(plot_code, '<plot>', 'exec'), namespace)

    if title:
        plt.title(title)
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)


if __name__ == '__main__':
    main(sys.argv[1])
