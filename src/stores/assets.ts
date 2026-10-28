import { reactive, readonly } from 'vue';
import { invoke, isTauri } from '@tauri-apps/api/core';
import type { AssetSummary } from '../types/assets';
const state = reactive({ items: [] as AssetSummary[], busy: false, error: '', notice: '' });
export const assets = readonly(state);
let epoch=0;
let refreshQueued=false;
export function resetAssets() { epoch++; refreshQueued=false; Object.assign(state,{items:[],busy:false,error:'',notice:''}); }
export async function refreshAssets() {
  if (!isTauri()) return;
  if (state.busy) { refreshQueued=true; return; }
  refreshQueued=false;
  state.busy = true;
  const token=epoch;
  state.error = '';
  try {
    const items: AssetSummary[] = [];
    let cursor: string | null = null;
    const seen = new Set<string>();
    do {
      const response: {ok:boolean; data:{items:AssetSummary[]; next_cursor:string|null}} = await invoke('list_assets', { afterId: cursor });
      if(token!==epoch)return;
      if (!response.ok || !Array.isArray(response.data?.items)) throw new Error();
      for (const item of response.data.items) {
        if (typeof item.id !== 'string' || seen.has(item.id) || typeof item.name !== 'string' || typeof item.kind !== 'string') throw new Error();
        seen.add(item.id); items.push(item);
      }
      cursor = response.data.next_cursor;
      if (cursor !== null && (typeof cursor !== 'string' || cursor !== items.at(-1)?.id || items.length > 100000)) throw new Error();
    } while (cursor);
    state.items = items;
  } catch { if(token===epoch)state.error = '파일 목록을 확인하지 못했습니다. 연결과 폴더 권한을 확인하세요.'; }
  finally {
    if(token===epoch) {
      state.busy = false;
      if(refreshQueued) { refreshQueued=false; await refreshAssets(); }
    }
  }
}
export async function scanLibrary(id: string) {
  if (state.busy) return;
  state.busy = true;
  const token=epoch;
  state.error = state.notice = '';
  try {
    const result = await invoke<{ok:boolean; data:{processed:number;errors:number;complete:boolean;new:number;changed:number;missing:number}}>('scan_library', {libraryId:id});
    if(token!==epoch)return;
    if (!result.ok || !Number.isSafeInteger(result.data?.processed)) throw new Error();
    state.notice = `${result.data.processed}개 파일 확인 · 신규 ${result.data.new} · 변경 ${result.data.changed} · 누락 ${result.data.missing} · 오류 ${result.data.errors}건`;
  } catch { if(token===epoch)state.error = '폴더 확인을 완료하지 못했습니다. 연결과 권한을 확인하세요.'; }
  finally { if(token===epoch)state.busy = false; }
  if(token===epoch)await refreshAssets();
}
