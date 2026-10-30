import { expect, test } from '@playwright/test';
import type { Page } from '@playwright/test';
import { newAccount, newProject, signIn } from './helpers';

// Whichever .tex file you are editing is the outline, the PDF, the table of contents and the figures, and they stay
// that way (even while you look at a .bib or an image) until you open another .tex file.

const head = '\\documentclass{article}\n\\usepackage[margin=1in]{geometry}\n\\usepackage{hyperref}\n\\begin{document}\n';
const svg = (name: string) => `<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40"><title>${name}</title><rect width="40" height="40"/></svg>`;
const FILES = {
  'paper.tex': `${head}\\section{Paper Intro}\nPaper text.\n\\input{body}\n\\newpage\\section{Paper End}\n\\iffalse \\includegraphics{figs/paper-fig.svg} \\fi\n\\end{document}\n`,
  'body.tex': '\\newpage\\section{Body Heading}\nBody text.\n\\newpage\\section{Body Second}\n\\iffalse \\includegraphics{figs/body-fig.svg} \\fi\n',
  'other.tex': `${head}\\section{Other Heading}\nOther text.\n\\newpage\\section{Other Second}\n\\iffalse \\includegraphics{figs/other-fig.svg} \\fi\n\\end{document}\n`,
  'refs.bib': '@book{k,\n  author = {A},\n  title = {T},\n  year = {1984}\n}\n',
  'figs/paper-fig.svg': svg('paper'),
  'figs/body-fig.svg': svg('body'),
  'figs/other-fig.svg': svg('other'),
  'figs/unused-fig.svg': svg('unused')
};

async function open(page: Page) {
  const session = await newAccount('curtex');
  const id = await newProject(session, 'Sticky', FILES);
  await signIn(page, session);
  await page.goto(`/editor/${id}`);
  await page.waitForSelector('.cm-editor');
}

const rail = (page: Page, name: string) => page.getByRole('button', { name, exact: true }).first();
const tab = (page: Page, name: string) => page.locator('button', { hasText: new RegExp(`^\\s*${name}\\s*$`) }).first();
async function openFile(page: Page, name: string) {
  const label = page.locator('.tree-label', { hasText: name }).first();
  if (!(await label.isVisible())) await rail(page, 'Files').click(); // the rail button toggles, so only when hidden
  await label.click();
  await expect(page.locator('.ed-breadcrumb, .cm-editor').first()).toBeVisible();
}
const outline = async (page: Page) => {
  if (!(await page.locator('.outline-list, .ed-panel-note').first().isVisible().catch(() => false))) await rail(page, 'Outline').click();
  return page.locator('.outline-title');
};
const pdfWord = (page: Page, w: string) => page.locator('.pdf-page .textLayer span', { hasText: w }).first();

test.describe('the current .tex file drives outline, PDF, contents and figures', () => {
  test.beforeEach(async ({ page }) => open(page));

  test('outline lists the file being edited, with its \\input files expanded', async ({ page }) => {
    await openFile(page, 'other.tex');
    let titles = await outline(page);
    await expect(titles).toHaveText(['Other Heading', 'Other Second']);

    await openFile(page, 'paper.tex');
    titles = await outline(page);
    await expect(titles).toHaveText(['Paper Intro', 'Body Heading', 'Body Second', 'Paper End']);

    await openFile(page, 'body.tex'); // a section file lists its own headings
    titles = await outline(page);
    await expect(titles).toHaveText(['Body Heading', 'Body Second']);
  });

  test('figures are the ones the current file includes, and they follow the file', async ({ page }) => {
    await openFile(page, 'other.tex');
    await tab(page, 'Figures').click();
    await expect(page.locator('.figure-display img')).toHaveAttribute('alt', 'figs/other-fig.svg');

    await openFile(page, 'body.tex'); // figures stay the active view and switch with the file
    await expect(page.locator('.figure-display img')).toHaveAttribute('alt', 'figs/body-fig.svg');

    await openFile(page, 'paper.tex'); // paper's own figure first; body.tex's comes along through \input
    await expect(page.locator('.figure-display img')).toHaveAttribute('alt', 'figs/body-fig.svg');
  });

  test('PDF and contents are those of the current file; clicking a contents entry scrolls there', async ({ page }) => {
    await openFile(page, 'paper.tex');
    await page.locator('.cm-content').click();
    await page.keyboard.press('Control+Enter');
    await expect(pdfWord(page, 'Paper Intro')).toBeVisible({ timeout: 60_000 });

    await openFile(page, 'other.tex'); // never compiled: no leftover PDF from paper.tex
    await expect(page.locator('.pdf-page')).toHaveCount(0);

    await openFile(page, 'body.tex'); // a section shows the PDF of the document that includes it
    await expect(pdfWord(page, 'Paper Intro')).toBeVisible({ timeout: 30_000 });

    await openFile(page, 'refs.bib'); // not a .tex file: nothing changes
    await expect(pdfWord(page, 'Paper Intro')).toBeVisible();

    await tab(page, 'Table of contents').click();
    await expect(page.locator('.toc-item .toc-title-text')).toHaveText(['Paper Intro', 'Body Heading', 'Body Second', 'Paper End']);
    await page.locator('.toc-item', { hasText: 'Body Second' }).click();
    await expect(pdfWord(page, 'Body Second')).toBeVisible({ timeout: 15_000 });
    const inView = await page.evaluate(() => {
      const container = document.querySelector('.pdf-page')?.parentElement;
      const page3 = container?.querySelector('.pdf-page[data-page-number="3"]');
      if (!container || !page3) return false;
      const c = container.getBoundingClientRect();
      const p = page3.getBoundingClientRect();
      return p.top < c.bottom && p.bottom > c.top && p.top >= c.top - 2;
    });
    expect(inView).toBe(true); // it lands on page 3, not at the top
  });

  test('contents follow the file even while the contents tab is showing', async ({ page }) => {
    await openFile(page, 'paper.tex');
    await page.locator('.cm-content').click();
    await page.keyboard.press('Control+Enter');
    await expect(pdfWord(page, 'Paper Intro')).toBeVisible({ timeout: 60_000 });
    await openFile(page, 'other.tex');
    await page.locator('.cm-content').click();
    await page.keyboard.press('Control+Enter');
    await expect(pdfWord(page, 'Other Heading')).toBeVisible({ timeout: 60_000 });

    await tab(page, 'Table of contents').click();
    await expect(page.locator('.toc-item .toc-title-text')).toHaveText(['Other Heading', 'Other Second']);
    await openFile(page, 'paper.tex');
    await expect(page.locator('.toc-item .toc-title-text')).toHaveText(['Paper Intro', 'Body Heading', 'Body Second', 'Paper End']);
  });
});
