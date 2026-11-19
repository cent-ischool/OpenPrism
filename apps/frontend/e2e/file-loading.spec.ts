import { expect, test } from '@playwright/test';
import { newAccount, newProject, signIn } from './helpers';
import type { Session } from './helpers';

// While a clicked file is still being fetched the editor shows the previous file. Keys pressed then used to edit that
// text and save it under the new file's name (#212); the editor is now read-only until the file arrives.

const base = () => process.env.E2E_BASE_URL || 'http://localhost:5173';
const doc = (word: string) => `\\documentclass{article}\n\\begin{document}\n${word}\n\\end{document}\n`;

async function saved(session: Session, id: string, path: string) {
  const res = await fetch(`${base()}/api/projects/${id}/file?path=${encodeURIComponent(path)}`, {
    headers: { authorization: `Bearer ${session.access}` }
  });
  return ((await res.json()) as { content: string }).content;
}

test('typing while a clicked file loads changes neither file, and typing works once it has loaded', async ({ page }) => {
  const session = await newAccount('loadtype');
  const id = await newProject(session, 'Loadtype', { 'a.tex': doc('Alphadoc'), 'b.tex': doc('Betadoc') });
  await signIn(page, session);
  await page.route(new RegExp(`/api/projects/${id}/file\\?path=b\\.tex`), async (route) => {
    await new Promise((r) => setTimeout(r, 2500));
    await route.continue();
  });
  await page.goto(`/editor/${id}`);
  await page.waitForSelector('.cm-editor');
  await page.locator('.tree-label', { hasText: 'a.tex' }).first().click();
  await expect(page.locator('.cm-content')).toContainText('Alphadoc');

  await page.locator('.tree-label', { hasText: 'b.tex' }).first().click();
  await page.locator('.cm-content').click();
  await page.keyboard.press('Control+End');
  await page.keyboard.type('Strayword', { delay: 5 }); // b.tex is still on its way
  await expect(page.locator('.cm-content')).toContainText('Betadoc', { timeout: 10_000 });
  await expect(page.locator('.cm-content')).not.toContainText('Strayword');
  await page.waitForTimeout(2500); // past autosave's 1.5 s debounce
  expect(await saved(session, id, 'b.tex')).toBe(doc('Betadoc'));
  expect(await saved(session, id, 'a.tex')).toBe(doc('Alphadoc'));

  await page.locator('.cm-content').click();
  await page.keyboard.press('Control+End');
  await page.keyboard.type('Laterword', { delay: 5 });
  await expect.poll(() => saved(session, id, 'b.tex'), { timeout: 10_000 }).toContain('Laterword');
  expect(await saved(session, id, 'a.tex')).toBe(doc('Alphadoc'));
});

test('compile pressed while a section file loads builds the main file, not the section', async ({ page }) => {
  const session = await newAccount('loadsec');
  const id = await newProject(session, 'Loadsec', { 'a.tex': doc('Alphadoc'), 'part.tex': '\\section{Just a part}\n' });
  await signIn(page, session);
  await page.route(new RegExp(`/api/projects/${id}/file\\?path=part\\.tex`), async (route) => {
    await new Promise((r) => setTimeout(r, 2500));
    await route.continue();
  });
  await page.goto(`/editor/${id}`);
  await page.waitForSelector('.cm-editor');
  await expect(page.locator('.cm-content')).toContainText('Alphadoc');
  await page.locator('.tree-label', { hasText: 'part.tex' }).first().click();
  await page.locator('.cm-content').click();
  // The editor still shows a.tex, a complete document; the compile used to take it for part.tex's text.
  const request = page.waitForRequest((r) => r.method() === 'POST' && /\/api\/compile$/.test(r.url()));
  await page.keyboard.press('Control+Enter');
  expect(JSON.parse((await request).postData() ?? '{}').mainFile).toBe('a.tex');
});
