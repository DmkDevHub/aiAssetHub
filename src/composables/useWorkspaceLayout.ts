import { computed, onBeforeUnmount, onMounted, ref, type Ref } from "vue";
import { libraryUi } from "../stores/libraryUi";

export function workspaceLayout(width: number, panelWidth: number, detailsCollapsed: boolean) {
  const galleryMinimum = 320;
  if (width < panelWidth + 10 + galleryMinimum) return "compact";
  if (width < panelWidth + 10 + galleryMinimum + (detailsCollapsed ? 120 : 290)) return "medium";
  return "wide";
}

export function useWorkspaceLayout(element: Ref<HTMLElement | undefined>) {
  const width = ref(0);
  let observer: ResizeObserver | undefined;
  function measure() {
    width.value = element.value?.getBoundingClientRect().width ?? 0;
  }
  onMounted(() => {
    measure();
    if (typeof ResizeObserver !== "undefined") {
      observer = new ResizeObserver((entries) => {
        const entry = entries.find((entry) => entry.target === element.value);
        if (entry && Number.isFinite(entry.contentRect.width)) width.value = Math.max(0, entry.contentRect.width);
      });
      if (element.value) observer.observe(element.value);
    } else window.addEventListener("resize", measure);
  });
  onBeforeUnmount(() => {
    observer?.disconnect();
    window.removeEventListener("resize", measure);
  });
  return computed(() => workspaceLayout(width.value, libraryUi.panelWidth, libraryUi.detailsCollapsed));
}
