import { expect, test } from '@playwright/test';
import { newAccount, newProject, signIn } from './helpers';

test.describe('file panel toolbar', () => {
  test.beforeEach(async ({ page }) => {
    const session = await newAccount('files');
    const projectId = await newProject(session, 'Files', { 'main.tex': '\\documentclass{article}\n\\begin{document}\nHi\n\\end{document}\n' });
    await signIn(page, session);
    await page.goto(`/editor/${projectId}`);
    await page.waitForSelector('.cm-editor');
  });

  const rows = (page: import('@playwright/test').Page) => page.locator('.tree-row');

  test('New file creates and lists the file', async ({ page }) => {
    await page.getByRole('button', { name: 'New file', exact: true }).click();
    await page.keyboard.type('notes.tex');
    await page.keyboard.press('Enter');
    await expect(rows(page).filter({ hasText: 'notes.tex' })).toBeVisible();
  });

  test('New folder creates and lists the folder', async ({ page }) => {
    await page.getByRole('button', { name: 'New folder', exact: true }).click();
    await page.keyboard.type('figs');
    await page.keyboard.press('Enter');
    await expect(rows(page).filter({ hasText: 'figs' })).toBeVisible();
  });

  test('Upload files adds the chosen file', async ({ page }) => {
    const chooser = page.waitForEvent('filechooser');
    await page.getByRole('button', { name: 'Upload files', exact: true }).click();
    await (await chooser).setFiles({ name: 'upload-me.tex', mimeType: 'text/plain', buffer: Buffer.from('Uploaded\n') });
    await expect(rows(page).filter({ hasText: 'upload-me.tex' })).toBeVisible();
  });
});
