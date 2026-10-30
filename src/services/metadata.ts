import {invoke,isTauri} from '@tauri-apps/api/core';
export type JsonObject=Record<string,unknown>;
export async function metadata<T>(method:string,params:JsonObject):Promise<T>{
 if(!isTauri())throw new Error('DESKTOP_REQUIRED');
 const r=await invoke<{ok:boolean;data:T;error?:{code:string}}>('metadata_request',{method,params});
 if(!r.ok)throw new Error(r.error?.code==='METADATA_CONFLICT'?'METADATA_CONFLICT':'METADATA_FAILED');
 return r.data;
}
export type CatalogOption={id:string;name:string;parentId?:string|null;axis?:string};
export async function catalogOptions(kind:string,version?:string):Promise<CatalogOption[]>{
 const items:CatalogOption[]=[];let cursor:string|null=null;
 do{const page: {items:CatalogOption[];next_cursor:string|null}=await metadata('catalog.options',{kind,after_id:cursor,...(version?{version}:{})});
  if(!Array.isArray(page.items))throw new Error('INVALID_PAGE');
  for(const item of page.items){if(typeof item.id!=='string'||typeof item.name!=='string'||items.some(i=>i.id===item.id))throw new Error('INVALID_PAGE');items.push(item);}
  cursor=page.next_cursor;if(cursor!==null&&(cursor!==page.items.at(-1)?.id||items.length>100000))throw new Error('INVALID_PAGE');
 }while(cursor);return items;
}
