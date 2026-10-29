import { expect, test } from '@playwright/test';
import type { Page } from '@playwright/test';
import { SECTIONS, newAccount, newProject, sectionedDocument, signIn } from './helpers';
import type { Session } from './helpers';

// After a recompile the PDF preview should show the part of the document being edited (SyncTeX forward search), and
// otherwise leave the reader where they were. The document has one section per page.

const PAGES = SECTIONS.length;
const container = (page: Page) => page.locator('.pdf-page').first().locator('xpath=..');

async function openEditor(page: Page, session: Session, files: Record<string, string>) {
  const projectId = await newProject(session, 'Preview', files);
  await signIn(page, session);
  await page.goto(`/editor/${projectId}`);
  await page.waitForSelector('.cm-editor');
  return projectId;
}

/** Remember the current first page element, so we can tell when the *new* PDF has replaced it. */
const markOldPdf = (page: Page) => page.evaluate(() => { (window as unknown as { __old: Element | null }).__old = document.querySelector('.pdf-page'); });

/** Wait until the newly compiled PDF is fully rendered (every page and its text) and the scroll position has stopped moving. */
async function pdfRendered(page: Page) {
  await page.waitForFunction((pages) => {
    const first = document.querySelector('.pdf-page');
    return !!first && first !== (window as unknown as { __old: Element | null }).__old
      && document.querySelectorAll('.pdf-page').length >= pages && document.querySelectorAll('.pdf-page .textLayer span').length > 20;
  }, PAGES, { timeout: 30_000 });
  let last = -1;
  for (let i = 0; i < 20; i += 1) {
    const top = await container(page).evaluate((c) => c.scrollTop);
    if (top === last) break;
    last = top;
    await page.waitForTimeout(250);
  }
}

async function compile(page: Page) {
  await markOldPdf(page);
  const pdf = page.waitForResponse((r) => /\/api\/jobs\/[^/]+\/pdf/.test(r.url()));
  await page.keyboard.press('Control+Enter');
  await pdf;
  await pdfRendered(page);
}

const caretIn = (page: Page, text: string) => page.locator('.cm-line', { hasText: text }).first().click();

/** Is the heading of this section entirely inside the preview's visible area? */
const headingVisible = (page: Page, name: string) => page.evaluate((name) => {
  const c = document.querySelector('.pdf-page')?.parentElement;
  const span = [...(c?.querySelectorAll('.textLayer span') ?? [])].find((s) => s.textContent?.includes(`Section ${name}`));
  if (!c || !span) return false;
  const view = c.getBoundingClientRect();
  const box = span.getBoundingClientRect();
  return box.top >= view.top - 1 && box.bottom <= view.bottom + 1;
}, name);

test.describe('PDF preview after recompiling', () => {
  test('jumps to the section being edited, up and down, including the last page', async ({ page }) => {
    await openEditor(page, await newAccount(), { 'main.tex': sectionedDocument() });
    await caretIn(page, 'Paragraph 3 of the Charlie');
    await compile(page);
    expect(await headingVisible(page, 'Charlie')).toBe(true); // the very first compile already goes there

    await caretIn(page, 'Paragraph 2 of the Foxtrot'); // down, to the last page (which is mostly blank below the text)
    await compile(page);
    expect(await headingVisible(page, 'Foxtrot')).toBe(true);

    await caretIn(page, 'Paragraph 4 of the Bravo'); // and back up
    await compile(page);
    expect(await headingVisible(page, 'Bravo')).toBe(true);
  });

  test('does not pull away a reader who scrolled while it was compiling', async ({ page }) => {
    await openEditor(page, await newAccount(), { 'main.tex': sectionedDocument() });
    await caretIn(page, 'Paragraph 3 of the Charlie');
    await compile(page);

    await caretIn(page, 'Paragraph 2 of the Echo');
    await markOldPdf(page);
    const pdf = page.waitForResponse((r) => /\/api\/jobs\/[^/]+\/pdf/.test(r.url()));
    await page.keyboard.press('Control+Enter');
    await container(page).evaluate((c) => { c.scrollTop = 40; }); // the reader scrolls right after pressing the shortcut
    await pdf;
    await pdfRendered(page);

    expect(await container(page).evaluate((c) => c.scrollTop)).toBeLessThan(600); // stayed near the top…
    expect(await headingVisible(page, 'Echo')).toBe(false); // …instead of jumping to Echo
  });

  test('keeps the reader in place when the caret is somewhere SyncTeX cannot map (a .bib file)', async ({ page }) => {
    await openEditor(page, await newAccount(), { 'main.tex': sectionedDocument(), 'refs.bib': '@book{k, title={A Title}, author={A. Author}, year={2020}}\n' });
    await caretIn(page, 'Paragraph 2 of the Alpha');
    await compile(page);
    await container(page).evaluate((c) => { c.scrollTop = 1500; });
    await page.waitForTimeout(300);

    await page.locator('.tree-row', { hasText: 'refs.bib' }).click();
    await page.locator('.cm-content').click();
    await compile(page);

    const top = await container(page).evaluate((c) => c.scrollTop);
    expect(Math.abs(top - 1500)).toBeLessThan(8);
  });

  test('keeps the reader at the same place when the zoom changes', async ({ page }) => {
    await openEditor(page, await newAccount(), { 'main.tex': sectionedDocument() });
    await caretIn(page, 'Paragraph 2 of the Alpha');
    await compile(page);
    const position = () => container(page).evaluate((c) => ({ ratio: c.scrollTop / c.scrollHeight, height: c.scrollHeight }));
    await container(page).evaluate((c) => { c.scrollTop = c.scrollHeight * 0.5; });
    await page.waitForTimeout(400);
    const before = await position();

    await markOldPdf(page);
    await page.getByRole('button', { name: '100%', exact: true }).click(); // changes the scale, so every page is re-rendered
    await pdfRendered(page);
    const after = await position();

    expect(after.height).not.toBe(before.height); // it really did re-render at another size
    expect(Math.abs(after.ratio - before.ratio)).toBeLessThan(0.02);
  });

  test('in a live collaborative session, words typed just before compiling are in the PDF and on screen', async ({ page }) => {
    await openEditor(page, await newAccount(), { 'main.tex': sectionedDocument() });
    await page.getByRole('button', { name: 'Collaboration', exact: true }).click();
    await page.locator('.collab-panel .op-btn-primary').click(); // creating an invite switches collaboration on
    await expect(page.locator('body')).toContainText(/Connected|已连接/);
    await page.getByRole('button', { name: 'Collaboration', exact: true }).click();

    await caretIn(page, 'Paragraph 2 of the Delta');
    await page.keyboard.press('End');
    await page.keyboard.type(' Zebrafish');
    await compile(page); // no pause: the editor must save the live document before the server compiles it

    const shown = await page.evaluate(() => {
      const c = document.querySelector('.pdf-page')?.parentElement;
      const span = [...(c?.querySelectorAll('.textLayer span') ?? [])].find((s) => s.textContent?.includes('Zebrafish'));
      if (!c || !span) return false;
      const view = c.getBoundingClientRect();
      const box = span.getBoundingClientRect();
      return box.top >= view.top && box.bottom <= view.bottom;
    });
    expect(shown).toBe(true);
  });
});
