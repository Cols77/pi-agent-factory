import type { ExtCommandCtx, ModelInfo, NativeModelCatalogEntry } from "./pi-types.js";

export type { NativeModelCatalogEntry } from "./pi-types.js";

export function modelKey(entry: Pick<ModelInfo, "provider" | "id">): string {
  return `${entry.provider}:${entry.id}`;
}

/** Return only policy keys present in the host's native catalog, in catalog order. */
export function intersectModelCatalog(
  catalog: readonly NativeModelCatalogEntry[],
  policyKeys: readonly string[],
): NativeModelCatalogEntry[] {
  const allowed = new Set(policyKeys);
  return catalog.filter((entry) => allowed.has(modelKey(entry)));
}

/** Native catalog is deliberately optional: absent means unavailable, never active-model fallback. */
export function nativeModelCatalog(ctx: Pick<ExtCommandCtx, "modelCatalog">): readonly NativeModelCatalogEntry[] {
  return ctx.modelCatalog?.() ?? [];
}
