export type PaneId = "context" | "tree" | "diff" | "comments";

export const PANE_ORDER: readonly PaneId[] = ["context", "tree", "diff", "comments"];

export interface LayoutState {
  collapsed: PaneId[];
  zoomed: PaneId | null;
  /** Whether the review-guidance strip is expanded. Defaults to collapsed:
   * the diff is the review; guidance is consulted on demand. */
  guide: boolean;
}

export const DEFAULT_LAYOUT: LayoutState = { collapsed: [], zoomed: null, guide: false };

const RAIL = "28px";
const NATURAL: Record<PaneId, string> = {
  context: "1.2fr",
  tree: "240px",
  diff: "2fr",
  comments: "320px",
};

function isPaneId(value: unknown): value is PaneId {
  return typeof value === "string" && (PANE_ORDER as readonly string[]).includes(value);
}

export function togglePane(state: LayoutState, pane: PaneId): LayoutState {
  const collapsed = state.collapsed.includes(pane)
    ? state.collapsed.filter((each) => each !== pane)
    : [...state.collapsed, pane];
  return { ...state, collapsed };
}

/** Zooming the already-zoomed pane restores, so the same key both enters and
 * leaves focus. Collapse state is kept, not cleared: leaving zoom must return
 * the reviewer to the layout they built, not to the default. */
export function zoomPane(state: LayoutState, pane: PaneId): LayoutState {
  return { ...state, zoomed: state.zoomed === pane ? null : pane };
}

export function restoreLayout(state: LayoutState): LayoutState {
  return { ...state, zoomed: null };
}

export function columnTemplate(state: LayoutState): string {
  if (state.zoomed !== null) {
    return PANE_ORDER.map((pane) => (pane === state.zoomed ? "1fr" : "0px")).join(" ");
  }
  return PANE_ORDER.map((pane) => (state.collapsed.includes(pane) ? RAIL : NATURAL[pane])).join(" ");
}

/** Coerce a persisted or posted layout into a valid one. The stored file is
 * hand-editable and the POST body is client input; neither may put an unknown
 * pane id into a CSS template. */
export function normalizeLayout(raw: unknown): LayoutState {
  if (raw === null || typeof raw !== "object") return DEFAULT_LAYOUT;
  const value = raw as { collapsed?: unknown; zoomed?: unknown; guide?: unknown };
  if (value.collapsed !== undefined && !Array.isArray(value.collapsed)) return DEFAULT_LAYOUT;
  return {
    collapsed: (value.collapsed ?? []).filter(isPaneId),
    zoomed: isPaneId(value.zoomed) ? value.zoomed : null,
    guide: value.guide === true,
  };
}
