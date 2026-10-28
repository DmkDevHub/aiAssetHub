import { reactive, readonly } from "vue";

const state = reactive({ searchQuery: "" });

export const workspace = readonly(state);

export function setSearchQuery(query: string) {
  state.searchQuery = query;
}
