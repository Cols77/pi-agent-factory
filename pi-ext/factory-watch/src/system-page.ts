// SP-B Task 5 split: `system-page.ts` is now a thin re-export of the system
// shell so `docs-server.ts` keeps importing `renderSystemPageHtml` unchanged.
// The actual page (HTML + CSS + inline client script) lives in
// `system-shell.ts`; the client script's parts live in `system-renderers.ts`
// (per-tab renderers) and `system-bootstrap.ts` (client bootstrap/controller).
export { renderSystemPageHtml } from './system-shell.js';
