import { reactive, readonly } from 'vue';
import { invoke, isTauri } from '@tauri-apps/api/core';

export interface LibraryRoot { id: string; name: string; path: string }
const state = reactive({ roots: [] as LibraryRoot[], loaded: false, loading: false, mutating: false, error: '', notice: '' });
export const libraries = readonly(state);
let epoch = 0;
const uuid = (value: unknown): value is string => typeof value === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(value);
function root(value: unknown): value is LibraryRoot {
  const record = value as LibraryRoot | null;
  return !!record && uuid(record.id) && typeof record.name === 'string' && !!record.name
    && typeof record.path === 'string' && /^[A-Za-z]:[\\/]/.test(record.path) && !record.path.includes('\0');
}
function data(response: unknown): Record<string, unknown> {
  const value = response as { ok?: unknown; data?: unknown; error?: { code?: unknown } | null } | null;
  if (value?.ok === false) throw typeof value.error?.code === 'string' ? value.error.code : 'LIBRARY_RESPONSE_INVALID';
  if (value?.ok !== true || value.error !== null || !value.data || typeof value.data !== 'object') throw 'LIBRARY_RESPONSE_INVALID';
  return value.data as Record<string, unknown>;
}
const messages: Record<string, string> = {
  LIBRARY_OVERLAP: '이미 등록된 폴더와 범위가 겹칩니다. 기존 등록을 확인하세요.',
  LIBRARY_FOLDER_UNAVAILABLE: '선택한 폴더를 읽을 수 없습니다. 위치와 권한을 확인하세요.',
  LIBRARY_LOCAL_FOLDER_REQUIRED: '로컬 드라이브의 하위 폴더를 선택하세요.',
  LIBRARY_PATH_TOO_LONG: '폴더 경로가 너무 깁니다.',
  LIBRARY_NOT_FOUND: '등록된 폴더를 찾을 수 없습니다. 목록을 새로고침하세요.',
  FOLDER_SELECTION_CHANGED: '폴더 선택이 변경되었습니다. 폴더를 다시 선택한 뒤 등록하세요.',
  DB_UNAVAILABLE: 'DB를 사용할 수 없습니다. Core 연결과 데이터 상태를 확인하세요.',
};
function fail(code: unknown) {
  state.error = typeof code === 'string' && Object.hasOwn(messages, code) ? messages[code]!
    : '처리 결과를 확인하지 못했습니다. 연결을 확인하고 등록 폴더를 새로고침하세요.';
}

export function resetLibrarySession() {
  epoch++;
  Object.assign(state, { roots: [], loaded: false, loading: false, mutating: false, error: '', notice: '' });
}

export async function refreshLibraries() {
  if (!isTauri() || state.loading || state.mutating) return false;
  const token = epoch;
  state.loading = true;
  state.error = '';
  try {
    const records: LibraryRoot[] = [];
    const seen = new Set<string>();
    let cursor: string | null = null;
    for (let page = 0; page < 200; page++) {
      const result = data(await invoke('list_libraries', { afterId: cursor }));
      if (epoch !== token) return false;
      if (!Array.isArray(result.libraries) || result.libraries.length > 50) throw 'LIBRARY_RESPONSE_INVALID';
      for (const record of result.libraries) {
        if (!root(record) || seen.has(record.id) || (cursor && record.id <= cursor)) throw 'LIBRARY_RESPONSE_INVALID';
        records.push(record);
        seen.add(record.id);
      }
      if (result.next_cursor === null) {
        if (epoch !== token) return false;
        state.roots = records;
        state.loaded = true;
        return true;
      }
      if (!uuid(result.next_cursor) || result.next_cursor !== records.at(-1)?.id || result.next_cursor === cursor) throw 'LIBRARY_RESPONSE_INVALID';
      cursor = result.next_cursor;
    }
    throw 'LIBRARY_RESPONSE_INVALID';
  } catch (code) { if (epoch === token) fail(code); return false; }
  finally { if (epoch === token) state.loading = false; }
}

export async function registerLibrary(path: string) {
  if (!isTauri() || !state.loaded || state.loading || state.mutating) return false;
  const token = epoch;
  state.mutating = true;
  state.error = state.notice = '';
  try {
    const result = data(await invoke('register_library', { path }));
    if (!root(result.library) || typeof result.created !== 'boolean') throw 'LIBRARY_RESPONSE_INVALID';
    if (epoch !== token) return false;
    const record = result.library;
    state.roots = [...state.roots.filter((item) => item.id !== record.id), record].sort((a, b) => a.id.localeCompare(b.id));
    state.notice = result.created ? '폴더를 등록했습니다.' : '기존 폴더 등록을 사용합니다.';
    return true;
  } catch (code) { if (epoch === token) fail(code); return false; }
  finally { if (epoch === token) state.mutating = false; }
}

export async function unregisterLibrary(id: string) {
  if (!isTauri() || state.loading || state.mutating || !state.roots.some((item) => item.id === id)) return false;
  const token = epoch;
  state.mutating = true;
  state.error = state.notice = '';
  try {
    const result = data(await invoke('unregister_library', { libraryId: id }));
    if (result.library_id !== id || result.enabled !== false) throw 'LIBRARY_RESPONSE_INVALID';
    if (epoch !== token) return false;
    state.roots = state.roots.filter((item) => item.id !== id);
    state.notice = '등록을 해제했습니다. 원본 파일은 유지됩니다.';
    return true;
  } catch (code) { if (epoch === token) fail(code); return false; }
  finally { if (epoch === token) state.mutating = false; }
}
