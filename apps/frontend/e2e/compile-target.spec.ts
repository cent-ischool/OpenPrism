import { expect, test } from '@playwright/test';
import type { Page } from '@playwright/test';
import { newAccount, newProject, signIn } from './helpers';

// Compile must build the document that is open in the editor, including edits typed a moment ago.

const doc = (word: string) => `\\documentclass{article}\n\\begin{document}\n${word}\n\\end{document}\n`;

async function openProject(page: Page) {
  const session = await newAccount('target');
  const id = await newProject(session, 'Target', {
    'a.tex': doc('Alphadoc'),
    'b.tex': doc('Betadoc'),
    'part.tex': '\\section{Just a part}\n'
  });
  await signIn(page, session);
  await page.goto(`/editor/${id}`);
  await page.waitForSelector('.cm-editor');
  return id;
}

const openFile = (page: Page, name: string) => page.locator('.tree-label', { hasText: name }).first().click();

/** Press compile and return the mainFile the browser asked the server to build. */
async function compiledFile(page: Page) {
  const request = page.waitForRequest((r) => r.method() === 'POST' && /\/api\/compile$/.test(r.url()));
  await page.keyboard.press('Control+Enter');
  return JSON.parse((await request).postData() ?? '{}').mainFile as string;
}

test.describe('what compile builds', () => {
  test('the open file, when it is a complete document', async ({ page }) => {
    await openProject(page);
    await openFile(page, 'b.tex');
    await page.locator('.cm-content').click();
    expect(await compiledFile(page)).toBe('b.tex'); // not a.tex, the first file alphabetically
  });

  test('the main file, when the open file is only a section', async ({ page }) => {
    await openProject(page);
    await openFile(page, 'part.tex');
    await page.locator('.cm-content').click();
    expect(await compiledFile(page)).toBe('a.tex');
  });

  test('includes what was typed a moment ago, before autosave fires', async ({ page }) => {
    await openProject(page);
    await openFile(page, 'b.tex');
    await page.locator('.cm-content').click();
    await page.keyboard.press('Control+End');
    await page.keyboard.press('ArrowUp');
    await page.keyboard.type('Zebraword', { delay: 5 });
    const pdf = page.waitForResponse((r) => /\/api\/jobs\/[^/]+\/pdf/.test(r.url()));
    await page.keyboard.press('Control+Enter'); // well inside autosave's 1.5 s debounce
    await pdf;
    await expect(page.locator('.pdf-page .textLayer span', { hasText: 'Zebraword' }).first()).toBeVisible({ timeout: 30_000 });
  });
});
