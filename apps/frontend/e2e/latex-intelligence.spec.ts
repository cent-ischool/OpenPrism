import { expect, test } from '@playwright/test';
import { newAccount, newProject, signIn } from './helpers';

const MAIN = [
  '\\documentclass{article}',
  '\\begin{document}',
  '\\section{Intro}\\label{sec:intro}',
  'See Section~\\ref{sec:intro} and \\cite{knuth84}.',
  '\\end{document}',
  ''
].join('\n');
const BIB = '@book{knuth84,\n  author = {Donald Knuth},\n  title = {The TeXbook},\n  year = {1984}\n}\n';

test.describe('LaTeX editor intelligence', () => {
  test.beforeEach(async ({ page }) => {
    const session = await newAccount('latex');
    const id = await newProject(session, 'Intel', { 'main.tex': MAIN, 'refs.bib': BIB, 'chapters/two.tex': '\\section{Two}\\label{sec:two}\n' });
    await signIn(page, session);
    await page.goto(`/editor/${id}`);
    await page.waitForSelector('.cm-editor');
    await page.waitForTimeout(1500); // project index loads shortly after the tree
  });

  const typeAtEnd = async (page: import('@playwright/test').Page, text: string) => {
    await page.locator('.cm-content').click();
    await page.keyboard.press('Control+End');
    await page.keyboard.press('ArrowUp'); // before \end{document}
    await page.keyboard.press('End');
    await page.keyboard.type(text, { delay: 30 });
  };

  test('highlights commands, environments and comments with distinct styles', async ({ page }) => {
    const colors = await page.locator('.cm-content span').evaluateAll((els) =>
      new Set(els.map((e) => getComputedStyle(e).color)).size
    );
    expect(colors).toBeGreaterThan(3);
  });

  test('\\cite{ offers keys from the .bib file', async ({ page }) => {
    await typeAtEnd(page, '\n\\cite{kn');
    await expect(page.locator('.cm-tooltip-autocomplete li', { hasText: 'knuth84' })).toBeVisible();
  });

  test('\\ref{ offers labels from other files too', async ({ page }) => {
    await typeAtEnd(page, '\n\\ref{sec:');
    await expect(page.locator('.cm-tooltip-autocomplete li', { hasText: 'sec:two' })).toBeVisible();
    await expect(page.locator('.cm-tooltip-autocomplete li', { hasText: 'sec:intro' })).toBeVisible();
  });

  test('\\begin{ completes environment names', async ({ page }) => {
    await typeAtEnd(page, '\n\\begin{itemi');
    await expect(page.locator('.cm-tooltip-autocomplete li', { hasText: 'itemize' })).toBeVisible();
  });

  test('\\includegraphics{ and \\input{ complete project files', async ({ page }) => {
    await typeAtEnd(page, '\n\\input{chap');
    await expect(page.locator('.cm-tooltip-autocomplete li', { hasText: 'chapters/two' })).toBeVisible();
  });

  test('flags a \\ref and a \\cite that nothing defines, but not the defined ones', async ({ page }) => {
    await typeAtEnd(page, '\nBad \\ref{nope} and \\cite{ghost}.');
    await expect(page.locator('.cm-lintRange-warning')).toHaveCount(2, { timeout: 5000 });
    const flagged = await page.locator('.cm-lintRange-warning').allInnerTexts();
    expect(flagged.sort()).toEqual(['ghost', 'nope']);
  });

  test('popups follow the dark theme', async ({ page }) => {
    await page.evaluate(() => {
      window.localStorage.setItem('openprism-theme', 'dark');
      document.documentElement.setAttribute('data-theme', 'dark');
    });
    await typeAtEnd(page, '\n\\cite{kn');
    const popup = page.locator('.cm-tooltip-autocomplete');
    await expect(popup).toBeVisible();
    const [bg, fg] = await popup.evaluate((el) => {
      const cs = getComputedStyle(el);
      const lum = (c: string) => c.match(/\d+(\.\d+)?/g)!.slice(0, 3).map(Number).reduce((a, b) => a + b, 0) / 3;
      return [lum(cs.backgroundColor), lum(getComputedStyle(el.querySelector('li')!).color)];
    });
    expect(bg).toBeLessThan(80); // dark surface
    expect(fg).toBeGreaterThan(150); // light text
  });
});
