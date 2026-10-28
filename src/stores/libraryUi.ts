import { reactive, readonly } from "vue";

export const LIBRARY_PANEL_WIDTH = { min: 200, max: 360, initial: 240 } as const;
export type GalleryViewMode = "grid" | "list";

const state = reactive({
  panelWidth: Number(LIBRARY_PANEL_WIDTH.initial),
  selectedFolderId: null as string | null,
  galleryViewMode: "grid" as GalleryViewMode,
});

export const libraryUi = readonly(state);

export function setLibraryPanelWidth(width: number) {
  if (!Number.isFinite(width)) return;
  state.panelWidth = Math.min(LIBRARY_PANEL_WIDTH.max, Math.max(LIBRARY_PANEL_WIDTH.min, Math.round(width)));
}

export function selectLibraryFolder(id: string | null) {
  state.selectedFolderId = id;
}

export function setGalleryViewMode(mode: GalleryViewMode) {
  if (mode === "grid" || mode === "list") state.galleryViewMode = mode;
}
