import { reactive, readonly } from 'vue';

const state = reactive<{ path: string | null }>({ path: null });
export const folderDraft = readonly(state);

/** A session-only selection, not a registered library or asset ID. */
export function setPickedFolderPath(path: string | null) {
  state.path = path;
}
