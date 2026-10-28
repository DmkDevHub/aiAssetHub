import type { AssetSummary } from '../types/assets';
export const normalizeSearch = (value: string) => value.normalize('NFKC').toLocaleLowerCase('ko');
export function keywordFilter(items: readonly AssetSummary[], query: string, tag = '') {
  const terms = normalizeSearch(query).trim().split(/\s+/).filter(Boolean);
  return items.filter(item => {
    const tags = (item.userTags ?? []).map(normalizeSearch);
    const text = normalizeSearch([item.name, item.relativePath ?? '', ...tags].join(' '));
    return (!tag || tags.includes(normalizeSearch(tag))) && terms.every(term => text.includes(term));
  });
}

export function stateFilter(items: readonly AssetSummary[], kind: string, analysis: string) {
  return items.filter(item => (!kind || item.kind===kind) &&
    (analysis==='' || (analysis==='completed' && item.hasActiveResult===true) ||
      (analysis==='unanalyzed' && item.hasActiveResult!==true) ||
      (analysis==='failed' && item.lastAttemptState==='failed')));
}
export function sortAssets(items: readonly AssetSummary[], sort: string) {
  const result=[...items];
  const byName=(a:AssetSummary,b:AssetSummary)=>a.name.localeCompare(b.name,'ko') || a.id.localeCompare(b.id);
  if(sort==='name')result.sort(byName);
  if(sort==='kind')result.sort((a,b)=>a.kind.localeCompare(b.kind) || byName(a,b));
  if(sort==='modified')result.sort((a,b)=>{
    const left=BigInt(a.mtimeNs ?? 0), right=BigInt(b.mtimeNs ?? 0);
    return left===right?byName(a,b):left>right?-1:1;
  });
  if(sort==='analysis')result.sort((a,b)=>(b.lastAnalysisAt ?? '').localeCompare(a.lastAnalysisAt ?? '') || byName(a,b));
  return result;
}
