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
