import { computed, reactive, readonly } from "vue";

export const operationLabels = {
  'appearance.change': '테마 변경',
  'gallery.view': '갤러리 보기 변경',
  'library.scan': '파일 스캔',
  'analysis.run': 'AI 분석',
  'unity.apply': 'Unity 적용',
} as const;
export const operationStates = { running: '진행 중', succeeded: '완료', failed: '실패', cancelled: '취소됨' } as const;
export const operationErrors = {
  PERMISSION_DENIED: '접근 권한을 확인하세요.',
  CORE_UNAVAILABLE: 'Core에 연결할 수 없습니다.',
  COMMAND_FAILED: '작업을 완료하지 못했습니다.',
} as const;
export type OperationKind = keyof typeof operationLabels;
export type OperationState = keyof typeof operationStates;
export interface OperationEvent {
  id: string;
  kind: OperationKind;
  state: OperationState;
  progress?: { processed: number; total: number };
  errorCode?: string;
}
interface OperationRecord extends Omit<OperationEvent, 'errorCode'> {
  errorCode?: keyof typeof operationErrors;
  dismissed: boolean;
}

const records = reactive<OperationRecord[]>([]);
export const operations = readonly(records);
export const operationAlerts = computed(() => operations.filter((record) => record.state === 'failed' && !record.dismissed));
export const hasClearableOperations = computed(() => records.some((record) => record.state !== 'running'
  && (record.state !== 'failed' || record.dismissed)));
export const MAX_OPERATIONS = 20;
let sequence = 0;

/** Receives measured command results only. It never starts or retries a command. */
export function receiveOperation(event: OperationEvent): boolean {
  if (!event || typeof event.id !== 'string' || !event.id.trim() || event.id.length > 200
    || !Object.hasOwn(operationLabels, event.kind) || !Object.hasOwn(operationStates, event.state)) return false;
  const progress = event.progress;
  if (progress && (!Number.isSafeInteger(progress.processed) || !Number.isSafeInteger(progress.total)
    || progress.processed < 0 || progress.total < 0 || progress.processed > progress.total
    || (event.state === 'succeeded' && progress.processed !== progress.total))) return false;
  const index = records.findIndex((record) => record.id === event.id);
  const previous = records[index];
  if (previous && (previous.state !== 'running' || previous.kind !== event.kind)) return false;
  if (previous?.progress && progress && (progress.total !== previous.progress.total
    || progress.processed < previous.progress.processed)) return false;
  // Completed events must carry their own complete counts, rather than inheriting partial progress.
  if (previous?.progress && event.state === 'succeeded' && !progress) return false;
  if (!previous && records.length >= MAX_OPERATIONS) {
    const removable = records.findIndex((record) => record.state !== 'running'
      && (record.state !== 'failed' || record.dismissed));
    if (removable < 0) return false;
    records.splice(removable, 1);
  }
  const record: OperationRecord = {
    id: event.id, kind: event.kind, state: event.state,
    progress: progress ? { processed: progress.processed, total: progress.total }
      : previous?.progress ? { ...previous.progress } : undefined,
    errorCode: event.state === 'failed' ? (Object.hasOwn(operationErrors, event.errorCode ?? '')
      ? event.errorCode as keyof typeof operationErrors : 'COMMAND_FAILED') : undefined,
    dismissed: false,
  };
  if (previous) records[index] = record;
  else records.push(record);
  return true;
}

export function dismissOperationAlert(id: string) {
  const record = records.find((record) => record.id === id && record.state === 'failed');
  if (record) record.dismissed = true;
}

export function clearFinishedOperations() {
  for (let index = records.length - 1; index >= 0; index--) {
    const record = records[index]!;
    if (record.state !== 'running' && (record.state !== 'failed' || record.dismissed)) records.splice(index, 1);
  }
}

/** Wraps real local UI commands. Exception messages/paths/keys are never retained or logged. */
export async function executeUiCommand(kind: 'appearance.change' | 'gallery.view', action: () => void | Promise<void>) {
  const id = `ui-command-${++sequence}`;
  if (!receiveOperation({ id, kind, state: 'running' })) return false;
  try {
    await action();
    receiveOperation({ id, kind, state: 'succeeded' });
    return true;
  } catch {
    receiveOperation({ id, kind, state: 'failed', errorCode: 'COMMAND_FAILED' });
    return false;
  }
}
