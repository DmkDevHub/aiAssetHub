"""Library registration only: no file enumeration, scanning, models or asset writes."""
import json
import os
from pathlib import Path
from uuid import UUID, uuid4


class LibraryError(Exception):
    pass


def valid_id(value):
    try:
        return isinstance(value, str) and len(value) == 36 and str(UUID(value)) == value
    except ValueError:
        return False


def _local_path(path):
    if not path.is_absolute() or '..' in path.parts or path == Path(path.anchor):
        raise LibraryError('LIBRARY_LOCAL_FOLDER_REQUIRED')
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        drive = path.drive
        if drive.startswith('\\\\?\\'):
            drive = drive[4:]
        if len(drive) != 2 or not drive[0].isascii() or not drive[0].isalpha() or drive[1] != ':':
            raise LibraryError('LIBRARY_LOCAL_FOLDER_REQUIRED')
        function = ctypes.WinDLL('kernel32', use_last_error=True).GetDriveTypeW
        function.argtypes, function.restype = [wintypes.LPCWSTR], wintypes.UINT
        if function(drive + '\\') not in (2, 3, 5, 6):
            raise LibraryError('LIBRARY_LOCAL_FOLDER_REQUIRED')


def registration_path(value):
    if not isinstance(value, str) or not value or '\0' in value or len(value) > 4096:
        raise LibraryError('INVALID_PARAMS')
    path = Path(value)
    _local_path(path)
    try:
        path = path.resolve(strict=True)
        _local_path(path)
        if not path.is_dir():
            raise LibraryError('LIBRARY_FOLDER_UNAVAILABLE')
        # Check directory read permission without iterating or collecting any files.
        with os.scandir(path):
            pass
    except (OSError, ValueError):
        raise LibraryError('LIBRARY_FOLDER_UNAVAILABLE') from None
    text = str(path)
    if os.name == 'nt' and text.startswith('\\\\?\\'):
        text = text[4:]
    name = path.name
    if len(json.dumps({'name': name, 'path': text}, ensure_ascii=True).encode('ascii')) + 50 > 6000:
        raise LibraryError('LIBRARY_PATH_TOO_LONG')
    return text, name


class LibraryService:
    def __init__(self, database):
        if database is None or getattr(database, 'connection', None) is None:
            raise LibraryError('DB_UNAVAILABLE')
        self.connection = database.connection

    @staticmethod
    def _record(row):
        return {'id': row[0], 'name': row[1], 'path': row[2]}

    def register(self, params):
        if not isinstance(params, dict) or set(params) != {'path'}:
            raise LibraryError('INVALID_PARAMS')
        path, name = registration_path(params['path'])
        key = os.path.normcase(path)
        self.connection.execute('BEGIN IMMEDIATE')
        try:
            rows = self.connection.execute('SELECT id,display_name,absolute_path,enabled FROM library_roots').fetchall()
            existing = None
            for row in rows:
                other = os.path.normcase(row[2])
                if key == other:
                    existing = row
                    continue
                if row[3]:
                    try:
                        if os.path.commonpath([key, other]) in (key, other):
                            raise LibraryError('LIBRARY_OVERLAP')
                    except ValueError:
                        pass # Different drives cannot overlap.
            if existing:
                self.connection.execute('UPDATE library_roots SET enabled=1 WHERE id=?', (existing[0],))
                record, created = self._record(existing), False
            else:
                record, created = {'id': str(uuid4()), 'name': name, 'path': path}, True
                self.connection.execute('INSERT INTO library_roots(id,display_name,absolute_path) VALUES (?,?,?)',
                                        (record['id'], name, path))
            self.connection.execute('COMMIT')
            return {'library': record, 'created': created}
        except Exception:
            self.connection.execute('ROLLBACK')
            raise

    def unregister(self, params):
        if not isinstance(params, dict) or set(params) != {'library_id'} or not valid_id(params['library_id']):
            raise LibraryError('INVALID_PARAMS')
        cursor = self.connection.execute('UPDATE library_roots SET enabled=0 WHERE id=?', (params['library_id'],))
        if cursor.rowcount != 1:
            raise LibraryError('LIBRARY_NOT_FOUND')
        return {'library_id': params['library_id'], 'enabled': False}

    def list(self, params):
        if not isinstance(params, dict) or set(params) - {'after_id'}:
            raise LibraryError('INVALID_PARAMS')
        after = params.get('after_id')
        if after is not None and not valid_id(after):
            raise LibraryError('INVALID_PARAMS')
        rows = self.connection.execute('SELECT id,display_name,absolute_path FROM library_roots WHERE enabled=1 AND id>? ORDER BY id LIMIT 51',
                                       (after or '',)).fetchall()
        items, size = [], 0
        for row in rows[:50]:
            item = self._record(row)
            length = len(json.dumps(item, ensure_ascii=True).encode('ascii'))
            if length > 6000:
                raise LibraryError('LIBRARY_PATH_TOO_LONG')
            if size + length > 12000:
                break
            items.append(item)
            size += length
        return {'libraries': items, 'next_cursor': items[-1]['id'] if len(rows) > len(items) else None}


ERROR_MESSAGES = {
    'BULK_LIMIT': '일괄 작업 크기 또는 응답 한도를 초과했습니다. 대상·필드를 줄이세요.',
    'CATALOG_LIMIT': '조회 한도를 초과했습니다. 폴더나 필터 범위를 줄이세요.',
    'METADATA_CONFLICT': '다른 변경이 저장되었습니다. 정보를 다시 불러온 후 저장하세요.',
    'EMBEDDING_LIMIT': '임베딩 처리 범위 또는 텍스트 한도를 초과했습니다.',
    'EMBEDDING_RESULT_CHANGED': '현재 활성 분석 결과가 변경되었거나 원본 재확인이 필요합니다.',
    'EMBEDDING_FAILED': '로컬 임베딩 요청에 실패했습니다.',
    'EMBEDDING_INVALID_VECTOR': '임베딩 차원 또는 벡터 값이 올바르지 않습니다.',
    'EMBEDDING_MODEL_UNAVAILABLE': '로컬 임베딩 모델을 확인할 수 없습니다.',
    'EMBEDDING_PROFILE_CHANGED': '임베딩 모델 또는 버전이 변경되었습니다.',
    'EMBEDDING_NOT_READY': '현재 버전의 준비된 임베딩이 없습니다.',
    'EMBEDDING_BUSY': '실행 중인 임베딩 작업이 있습니다.',
    'FILE_PERMISSION_DENIED': '원본 파일의 읽기 권한이 없습니다.',
    'ANALYSIS_NO_SUPPORTED_INPUT': '현재 분석 경로에서 처리할 이미지 후보가 없습니다.',
    'CORE_INTERRUPTED': 'Core 종료로 중단된 작업을 사용자가 정리했습니다.',
    'UNSUPPORTED_FORMAT': '현재 분석 경로에서 지원하지 않는 파일 형식입니다.',
    'INPUT_TOO_LARGE': '분석 입력 크기 또는 픽셀 한도를 초과했습니다.',
    'INVALID_IMAGE': '이미지를 해석할 수 없습니다.',
    'FILE_CHANGED': '확인 이후 원본이 변경되었습니다.',
    'MODEL_CHANGED': '확인 이후 모델 또는 가격이 변경되었습니다.',
    'API_TIMEOUT': '모델 응답 시간이 초과되었습니다.',
    'API_RATE_LIMIT': '공급자 호출 한도에 도달했습니다.',
    'API_AUTHENTICATION': '공급자 인증을 확인하세요.',
    'API_FAILED': '모델 호출에 실패했습니다.',
    'INVALID_MODEL_OUTPUT': '모델 응답 형식이 올바르지 않습니다.',
    'MODEL_OUTPUT_LIMIT': '모델이 출력 한도 내에 최종 응답을 완료하지 못했습니다. 자동 재시도하지 않습니다.',
    'USER_CANCELED': '사용자가 분석을 취소했습니다.',
    'ANALYSIS_NOT_FOUND': '분석 작업을 찾을 수 없습니다.',
    'COST_ESTIMATE_UNAVAILABLE': '안전한 비용 상한을 계산할 수 없습니다.',
    'ANALYSIS_PLAN_CHANGED': '대상·모델·비용이 변경되었습니다. 다시 확인하세요.',
    'ANALYSIS_EMPTY': '분석할 대상이 없습니다.',
    'ANALYSIS_BUSY': '대기 또는 실행 중인 분석을 먼저 종료하세요.',
    'FILE_MISSING': '원본 파일이 없습니다.',
    'FILE_UNAVAILABLE': '원본 파일에 접근할 수 없습니다.',
    'ANALYSIS_TARGET_LIMIT': '한 번에 최대 1000개 에셋을 분석할 수 있습니다.',
    'MODEL_UNAVAILABLE': '모델이 비활성 또는 미확인 상태입니다.',
    'MODEL_CAPABILITY_MISMATCH': '선택한 입력 유형을 지원하지 않는 모델입니다.',
    'MODEL_POLICY_DENIED': '모델 상태·인증·외부 전송 및 유료 사용 승인을 확인하세요.',
    'BUDGET_EXCEEDED': '예산 또는 호출 한도를 초과합니다.',
    'INVALID_PARAMS': '폴더 요청 형식이 올바르지 않습니다.',
    'LIBRARY_LOCAL_FOLDER_REQUIRED': '로컬 드라이브의 하위 폴더를 선택해야 합니다.',
    'LIBRARY_FOLDER_UNAVAILABLE': '폴더를 확인할 수 없습니다.',
    'LIBRARY_PATH_TOO_LONG': '폴더 경로가 너무 깁니다.',
    'LIBRARY_OVERLAP': '이미 등록된 폴더와 범위가 중첩됩니다.',
    'LIBRARY_NOT_FOUND': '등록된 폴더를 찾을 수 없습니다.',
    'DB_UNAVAILABLE': 'DB를 사용할 수 없습니다.',
}
