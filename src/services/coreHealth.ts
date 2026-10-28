export interface CoreHealth {
  ok: true;
  error: null;
  request_id: string;
  timestamp: string;
  data: {
    core: { status: 'ready'; version: string; pid: number; uptime_ms: number };
    database: { status: 'ready'; schema_version: number; sqlite_version: string; journal_mode: string }
      | { status: 'error'; error_code: string } | { status: 'not_configured' };
  };
}

export function validCoreHealth(value: unknown): value is CoreHealth {
  if (!value || typeof value !== 'object') return false;
  const response = value as CoreHealth;
  const core = response.data?.core;
  const database = response.data?.database;
  if (response.ok !== true || response.error !== null || typeof response.request_id !== 'string'
    || !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(response.request_id)
    || typeof response.timestamp !== 'string' || !Number.isFinite(Date.parse(response.timestamp))
    || core?.status !== 'ready' || typeof core.version !== 'string' || core.version.length > 32
    || !Number.isSafeInteger(core.pid) || core.pid <= 0 || !Number.isSafeInteger(core.uptime_ms) || core.uptime_ms < 0) return false;
  if (database?.status === 'ready') return Number.isSafeInteger(database.schema_version) && database.schema_version > 0
    && typeof database.sqlite_version === 'string' && database.sqlite_version.length < 32 && database.journal_mode === 'wal';
  return database?.status === 'not_configured' || (database?.status === 'error' && typeof database.error_code === 'string');
}

const messages: Record<string, string> = {
  CORE_START_FAILED: 'Core를 시작하지 못했습니다. 설치 파일과 실행 환경을 확인한 뒤 다시 연결하세요.',
  CORE_EXITED: 'Core가 종료되었습니다. 다시 연결하면 새 프로세스를 시작합니다.',
  CORE_TIMEOUT: 'Core 응답 시간이 초과되었습니다. 다시 연결하세요.',
  CORE_PROTOCOL_ERROR: 'Core 응답을 확인할 수 없습니다. 앱 버전을 확인하고 다시 연결하세요.',
  DATA_IN_USE: '다른 Core가 이 데이터를 사용 중입니다. 해당 앱을 종료한 뒤 다시 연결하세요.',
  DATA_ENV_MISMATCH: '데이터의 실행 환경이 다릅니다. 개발용·운영용 데이터 위치를 확인하세요.',
  DB_SCHEMA_INCOMPATIBLE: '이 앱 버전과 DB가 호환되지 않습니다. 기존 DB와 백업을 보존하고 앱 버전을 확인하세요.',
  DB_SCHEMA_UNKNOWN: '이 DB는 앱 데이터로 확인되지 않습니다. 기존 파일을 보존하고 데이터 위치를 확인하세요.',
  DB_UNAVAILABLE: 'DB를 열 수 없습니다. 기존 파일을 보존하고 권한과 디스크 상태를 확인한 뒤 다시 연결하세요.',
};

export function coreErrorMessage(code: unknown) {
  return typeof code === 'string' && Object.hasOwn(messages, code) ? messages[code]!
    : 'Core에 연결할 수 없습니다. 실행 환경을 확인한 뒤 다시 연결하세요.';
}
