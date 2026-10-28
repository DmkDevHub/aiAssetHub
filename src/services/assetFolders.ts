import type { AssetSummary } from '../types/assets';
export interface FolderNode { id: string; name: string; children?: FolderNode[] }
export function folderNodes(roots: readonly {id:string;name:string}[], items: readonly AssetSummary[]) {
  return roots.map((root) => {
    const node: FolderNode = { id:root.id, name:root.name, children:[] };
    for (const item of items.filter((item) => item.libraryId === root.id)) {
      const parts = (item.relativePath ?? '').split(/[\\/]/).slice(0,-1);
      let current = node;
      const path: string[] = [];
      for (const part of parts) {
        if (!part || part === '.' || part === '..') continue;
        path.push(part);
        const id = 'folder:' + JSON.stringify([root.id, ...path]);
        current.children ??= [];
        let child = current.children.find((child) => child.id === id);
        if (!child) { child = {id, name:part, children:[]}; current.children.push(child); }
        current = child;
      }
    }
    return node;
  });
}
export function filterFolder(items: readonly AssetSummary[], selected: string | null) {
  if (!selected) return items;
  if (!selected.startsWith('folder:')) return items.filter((item) => item.libraryId === selected);
  try {
    const [library, ...parts] = JSON.parse(selected.slice(7)) as string[];
    return items.filter((item) => item.libraryId === library && parts.every((part, index) => item.relativePath?.split(/[\\/]/)[index] === part));
  } catch { return []; }
}
