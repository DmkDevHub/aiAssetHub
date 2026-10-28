import { reactive, readonly } from "vue";

export type Theme = "dark" | "light";

const state = reactive<{ theme: Theme }>({ theme: "dark" });

export const appearance = readonly(state);

export function setTheme(theme: Theme) {
  state.theme = theme;
}
