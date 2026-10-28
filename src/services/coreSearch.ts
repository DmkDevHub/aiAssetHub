import { invoke } from '@tauri-apps/api/core';
export async function coreSearch(query: string, isCurrent: () => boolean = () => true): Promise<Set<string>> {
  const ids = new Set<string>();
  let cursor: string | null = null;
  do {
    if(!isCurrent()) throw new Error('SEARCH_CANCELLED');
    const result: {ok:boolean;data:{ids:string[];next_cursor:string|null}} = await invoke('search_assets', {query,afterId:cursor});
    if(!isCurrent()) throw new Error('SEARCH_CANCELLED');
    if(!result.ok || !Array.isArray(result.data?.ids)) throw new Error('SEARCH_FAILED');
    for(const id of result.data.ids) {
      if(typeof id !== 'string' || ids.has(id)) throw new Error('SEARCH_FAILED');
      ids.add(id);
    }
    cursor=result.data.next_cursor;
    if(cursor !== null && (typeof cursor!=='string' || cursor!==result.data.ids.at(-1) || ids.size>100000)) throw new Error('SEARCH_FAILED');
  } while(cursor);
  return ids;
}
