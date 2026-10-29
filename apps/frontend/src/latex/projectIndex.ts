import type { Completion, CompletionContext, CompletionResult } from '@codemirror/autocomplete';
import type { Diagnostic } from '@codemirror/lint';
import type { EditorState } from '@codemirror/state';

/** What the whole project defines, so completion and checks can see beyond the file being edited. */
export interface ProjectIndex {
  /** label name -> file that defines it */
  labels: Map<string, string>;
  /** bibliography key -> entry summary */
  cites: Map<string, { file: string; detail: string }>;
  /** every file path in the project */
  paths: string[];
}

const IMAGE_EXT = /\.(png|jpe?g|pdf|eps|svg)$/i;

/** Drop `% comments` (keeping `\%`) so commented-out commands are not indexed. */
export function stripComments(text: string): string {
  return text.replace(/(^|[^\\])%.*$/gm, '$1');
}

function bibEntries(file: string, text: string, out: ProjectIndex['cites']) {
  const start = /@([A-Za-z]+)\s*[{(]\s*([^,\s{}()]+)\s*,/g;
  let m: RegExpExecArray | null;
  while ((m = start.exec(text))) {
    const kind = m[1].toLowerCase();
    if (kind === 'comment' || kind === 'string' || kind === 'preamble') continue;
    const body = text.slice(m.index, m.index + 1500);
    const field = (name: string) =>
      new RegExp(`\\b${name}\\s*=\\s*[{"]+([^}"]*)`, 'i').exec(body)?.[1]?.replace(/\s+/g, ' ').trim();
    const author = field('author')?.split(/\s+and\s+/i)[0];
    const title = field('title');
    const year = field('year');
    out.set(m[2], { file, detail: [author, year, title].filter(Boolean).join(' · ') });
  }
}

export function labelsIn(text: string): string[] {
  const out: string[] = [];
  const re = /\\label\s*\{([^}\s]+)\}/g;
  let m: RegExpExecArray | null;
  const clean = stripComments(text);
  while ((m = re.exec(clean))) out.push(m[1]);
  return out;
}

export function buildProjectIndex(texts: Record<string, string>, paths: string[]): ProjectIndex {
  const index: ProjectIndex = { labels: new Map(), cites: new Map(), paths };
  for (const [file, text] of Object.entries(texts)) {
    const lower = file.toLowerCase();
    if (lower.endsWith('.bib')) {
      bibEntries(file, text, index.cites);
    } else if (lower.endsWith('.tex') || lower.endsWith('.sty') || lower.endsWith('.cls')) {
      for (const name of labelsIn(text)) if (!index.labels.has(name)) index.labels.set(name, file);
      const clean = stripComments(text);
      const item = /\\bibitem\s*(?:\[[^\]]*\])?\s*\{([^}\s]+)\}/g;
      let m: RegExpExecArray | null;
      while ((m = item.exec(clean))) index.cites.set(m[1], { file, detail: 'bibitem' });
    }
  }
  return index;
}

/** Overlay the live text of the file being edited on the saved index (labels only; bib files are indexed on save). */
function withLiveDoc(index: ProjectIndex, state: EditorState, activePath: string): ProjectIndex {
  if (!activePath.toLowerCase().endsWith('.tex')) return index;
  const labels = new Map(index.labels);
  for (const name of labelsIn(state.doc.toString())) labels.set(name, activePath);
  return { ...index, labels };
}

// Argument of a \ref-like or \cite-like command being typed; `list` is what precedes the current key in `{a,b,`.
const REF_ARG = /\\(?:[a-zA-Z]*ref|[a-zA-Z]*Ref|cref|Cref|autoref|nameref|vref|eqref|pageref)\*?\{([^{}]*,)?\s*([^{},]*)$/;
const CITE_ARG = /\\[a-zA-Z]*cite[a-zA-Z]*\*?(?:\[[^\]]*\]){0,2}\{([^{}]*,)?\s*([^{},]*)$/;
const FILE_ARG = /\\(includegraphics|input|include|bibliography|addbibresource|subfile)\s*(?:\[[^\]]*\])?\{([^{}]*,)?\s*([^{},]*)$/;

function linePrefix(context: CompletionContext) {
  const line = context.state.doc.lineAt(context.pos);
  return { text: context.state.doc.sliceString(line.from, context.pos), from: line.from };
}

/** Completion for the keys inside \ref{}, \cite{} and for file names inside \includegraphics{}, \input{}, … */
export function projectCompletionSource(getIndex: () => ProjectIndex | null, getActivePath: () => string) {
  return (context: CompletionContext): CompletionResult | null => {
    const index = getIndex();
    if (!index) return null;
    const { text, from: lineFrom } = linePrefix(context);

    const ref = REF_ARG.exec(text);
    if (ref) {
      const typed = ref[2];
      const live = withLiveDoc(index, context.state, getActivePath());
      const options: Completion[] = [...live.labels].map(([label, file]) => ({
        label,
        type: 'constant',
        detail: file
      }));
      return { from: lineFrom + text.length - typed.length, options, validFor: /^[^{},\s]*$/ };
    }

    const cite = CITE_ARG.exec(text);
    if (cite) {
      const typed = cite[2];
      const options: Completion[] = [...index.cites].map(([key, info]) => ({
        label: key,
        type: 'text',
        detail: info.detail,
        info: info.file
      }));
      return { from: lineFrom + text.length - typed.length, options, validFor: /^[^{},\s]*$/ };
    }

    const file = FILE_ARG.exec(text);
    if (file) {
      const command = file[1];
      const typed = file[3];
      let candidates = index.paths;
      let strip = false;
      if (command === 'includegraphics') candidates = candidates.filter((p) => IMAGE_EXT.test(p));
      else if (command === 'bibliography' || command === 'addbibresource') {
        candidates = candidates.filter((p) => p.toLowerCase().endsWith('.bib'));
        strip = command === 'bibliography';
      } else {
        candidates = candidates.filter((p) => p.toLowerCase().endsWith('.tex'));
        strip = command !== 'subfile';
      }
      const options: Completion[] = candidates.map((p) => ({
        label: strip ? p.replace(/\.[^./]+$/, '') : p,
        type: 'file'
      }));
      return { from: lineFrom + text.length - typed.length, options, validFor: /^[^{},]*$/ };
    }
    return null;
  };
}

/** Flags \ref / \cite keys that nothing in the project defines. A warning, because they may be defined by a package or an aux file. */
export function projectReferenceLinter(getIndex: () => ProjectIndex | null, getActivePath: () => string) {
  return (state: EditorState): Diagnostic[] => {
    const active = getActivePath();
    const index = getIndex();
    if (!index || !active.toLowerCase().endsWith('.tex')) return [];
    const live = withLiveDoc(index, state, active);
    // A project with no bibliography at all is the package linter's business, not ours.
    const checkCites = index.cites.size > 0;
    const doc = state.doc.toString();
    const diagnostics: Diagnostic[] = [];
    const command = /\\([a-zA-Z]*(?:ref|Ref|cite[a-zA-Z]*))\*?((?:\[[^\]]*\]){0,2})\{([^{}]*)\}/g;
    const lines = doc.split('\n');
    let offset = 0;
    for (const line of lines) {
      const pct = /(^|[^\\])%/.exec(line);
      const code = pct ? line.slice(0, pct.index + pct[1].length) : line;
      command.lastIndex = 0;
      let m: RegExpExecArray | null;
      while ((m = command.exec(code))) {
        const name = m[1];
        const isCite = /cite/i.test(name);
        if (isCite ? !checkCites : false) continue;
        if (!isCite && !/^(?:[a-zA-Z]*ref|[a-zA-Z]*Ref)$/.test(name)) continue;
        const argStart = offset + m.index + m[0].length - m[3].length - 1;
        let at = 0;
        for (const part of m[3].split(',')) {
          const key = part.trim();
          const keyFrom = argStart + at + part.indexOf(key);
          at += part.length + 1;
          if (!key || key === '*') continue;
          const known = isCite ? index.cites.has(key) : live.labels.has(key);
          if (!known) {
            diagnostics.push({
              from: keyFrom,
              to: keyFrom + key.length,
              severity: 'warning',
              message: isCite ? `No bibliography entry "${key}" in this project` : `No \\label{${key}} in this project`
            });
          }
        }
      }
      offset += line.length + 1;
    }
    return diagnostics;
  };
}
