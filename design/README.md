# Open Prism design system

Lives at the repo root (`/design`) and is imported by the frontend as `@design`
(alias set in `apps/frontend/vite.config.ts` and `apps/frontend/tsconfig.json`).

Everything visual starts here. Pages and features should compose these pieces
instead of adding their own buttons, dropdowns, icons or colours.

| File | What it gives you |
|---|---|
| `tokens.css` | Colour (light + dark), type, spacing, radius, motion tokens and the `op-` component classes. Loaded once in `apps/frontend/src/main.tsx`. |
| `Icon.tsx` / `iconPaths.ts` | `<Icon name="…" />` — the only icon source. One outline family, 24px grid, 1.75 stroke. |
| `Logo.tsx` | `<Logo />` and `<LogoMark />` (the prism mark, also `apps/frontend/public/favicon.svg`). |
| `ui.tsx` | `Button`, `IconButton`, `Badge`, `Tag`, `Avatar`, `Menu` / `MenuButton`, `Select`, `SegmentedControl`, `Modal`, `PanelHeader`, `EmptyState`, `FieldError` (inline validation message under a field). |
| `AppTopBar.tsx` | Shared top bar: logo · workspace switcher › breadcrumbs ……… actions · account menu. Invite-link guests get a static label instead of the switcher and a different account menu. |
| `AuthScreen.tsx` | Full-screen sign-in / create-account form (validation, show-password toggle, error banner). Takes `mode`, `onModeChange`, an async `onSubmit` that rejects with a displayable `Error`, and an optional `notice`. |
| `theme.ts` | `useTheme()` — light / dark / system, stored in `localStorage`. |
| `workspace.tsx` | The contract between the UI and the data behind accounts and workspaces: types, `WorkspaceContextValue`, `<WorkspaceProvider value={…}>` and `useWorkspace()`. It knows nothing about the API; `apps/frontend/src/auth` builds the real value. Actions are async and reject with an `Error` whose message is safe to show. |

## Rules of thumb

- **Colour:** use tokens only (`var(--surface)`, `var(--text-2)`, `var(--accent)`, …). No hex or rgba values in components. Dark mode is designed separately, so test both themes.
- **Accent:** one accent (terracotta). Use it for the single primary action in a region, the current selection and focus rings — nothing decorative.
- **Icons:** always `<Icon>`. No emoji, no text glyphs (✕ ▾ ▸ −), no pasted SVGs. An icon-only button needs a `label` (it becomes the tooltip and accessible name).
- **Buttons:** `primary` once per region, `secondary` for supporting actions, `ghost` in toolbars, `danger` only inside a confirmation.
- **Choices:** use `Select` for picking a value from a list, and `SegmentedControl` for switching modes within the same view (Chat / Agent, Editor / Split / PDF).
- **Menus:** each menu lives on the object it acts on (workspace, project, file, compile, account). Destructive items go last, followed by `…` when they open a confirmation.
- **Panels:** the editor uses collapsible, resizable side panels. A `PanelHeader` holds the title, up to three icon actions, and Collapse.
- **Forms:** a `label` for every input, `aria-invalid` plus a `FieldError` (linked with `aria-describedby`) for problems, validate on blur and on submit, and show server errors in a banner above the form.
- **Copy:** use sentence case and name the object, saying what happened or what to do next. Wrap new strings in `t('English text')` and add a `zh-CN` translation.

## Reference

`reference/` holds the static HTML exports from the design phase:

- `reference/design-system.html` — living style guide: foundations, the icon set, components with their states, layout and menu rules, roles, and copy guidelines.
- `reference/index.html` — clickable prototype of the workspace home and the editor shell with collapsible panels (mock data).

Open either file directly in a browser; they share `openprism.css` and `icons.js` and aren't part of the Vite build. `tokens.css` is the source of truth if the two ever drift apart.
