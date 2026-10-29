import { expect, test } from '@playwright/test';
import { newAccount, newProject, sectionedDocument, signIn } from './helpers';

test('Ctrl+Enter in the editor compiles once and does not insert a line', async ({ page }) => {
  const session = await newAccount();
  const projectId = await newProject(session, 'Shortcut', { 'main.tex': sectionedDocument() });
  await signIn(page, session);
  let compiles = 0;
  page.on('request', (r) => { if (r.method() === 'POST' && r.url().endsWith('/api/compile')) compiles += 1; });

  await page.goto(`/editor/${projectId}`);
  await page.locator('.cm-line', { hasText: 'Paragraph 3 of the Charlie' }).first().click();
  const linesBefore = await page.locator('.cm-line').count();

  const pdf = page.waitForResponse((r) => /\/api\/jobs\/[^/]+\/pdf/.test(r.url()));
  await page.keyboard.press('Control+Enter');
  await pdf; // the compile ran and its PDF was fetched

  expect(compiles).toBe(1); // exactly one: not also from the window-level handler
  expect(await page.locator('.cm-line').count()).toBe(linesBefore); // CodeMirror's "insert blank line" did not run
});
