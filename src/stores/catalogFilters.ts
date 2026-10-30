import {reactive} from 'vue';
export const catalogFilters=reactive({value:{} as Record<string,unknown>,revision:0,active:false,tag:'',kind:'',analysis:'',searchMode:'keyword',sort:'source'});
export function applyCatalogFilters(value:Record<string,unknown>){catalogFilters.value=JSON.parse(JSON.stringify(value));catalogFilters.active=Object.keys(value).length>0;catalogFilters.revision++;}
export function resetCatalogFilters(){applyCatalogFilters({});catalogFilters.tag='';catalogFilters.kind='';catalogFilters.analysis='';catalogFilters.searchMode='keyword';catalogFilters.sort='source';}
