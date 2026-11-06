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
  let scanError='';
  try {
    type ScanResult={processed:number;errors:number;complete:boolean;new:number;changed:number;missing:number};
    const started = await invoke<{ok:boolean; data:ScanResult|{jobId:string}}>('scan_library', {libraryId:id});
    if(token!==epoch)return;
    if(!started.ok)throw new Error();
    let result:{ok:boolean;data:ScanResult};
    if('jobId' in started.data){
      const jobId=started.data.jobId;if(typeof jobId!=='string')throw new Error();
      state.notice=`스캔 작업 ${jobId} 실행 중`;
      let completed:ScanResult|null=null;
      for(let attempt=0;attempt<600;attempt++){
        if(token!==epoch)return;
        const status=await invoke<{ok:boolean;data:{status:string;result:ScanResult|null}}>('metadata_request',{method:'library.scan.status',params:{job_id:jobId}});
        if(token!==epoch)return;
        if(!status.ok)throw new Error();
        if(status.data.status==='completed'){completed=status.data.result;break;}
        if(!['queued','running'].includes(status.data.status))throw new Error();
        await new Promise(resolve=>setTimeout(resolve,500));
      }
      if(!completed)throw new Error();result={ok:true,data:completed};
    }else result={ok:true,data:started.data}; // Legacy responses remain readable during an app update.
    if (!result.ok || !Number.isSafeInteger(result.data?.processed)) throw new Error();
    state.notice = `${result.data.processed}개 파일 확인 · 신규 ${result.data.new} · 변경 ${result.data.changed} · 누락 ${result.data.missing} · 오류 ${result.data.errors}건`;
  } catch { if(token===epoch){scanError='폴더 확인을 완료하지 못했습니다. 연결과 권한을 확인하세요.';state.error=scanError;state.notice='';} }
  finally { if(token===epoch)state.busy = false; }
  if(token===epoch){
    await refreshAssets();
    if(token===epoch&&scanError)state.error=state.error?`${scanError} ${state.error}`:scanError;
  }
}
