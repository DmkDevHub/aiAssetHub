"""Transport-independent allowlisted Core command dispatch."""

from datetime import datetime, timezone
import os
import platform
import time
from uuid import UUID

from . import __version__


class CoreApplication:
    def __init__(self, database=None):
        self._started_at = time.monotonic_ns()
        self.database = database
        self._analysis = None
        self._embedding = None
        self._broker = None

    def start_analysis(self, params):
        from .analysis_jobs import AnalysisJobs
        result=AnalysisJobs(self.database).start(params)
        if not result['reused']:
            from .analysis_engine import AnalysisEngine
            if self._analysis is None:self._analysis=AnalysisEngine(self.database)
            self._analysis.launch(result['jobId'])
        return result

    def cancel_analysis(self, params):
        from .analysis_jobs import AnalysisJobs
        jobs=AnalysisJobs(self.database);status=jobs.status(params)
        if status['status'] in ('queued','running') and self._analysis and self._analysis.cancel(params['job_id']):
            return {'cancelRequested':True,'status':status['status']}
        return jobs.cancel_orphan(params)

    def analysis_status(self, params):
        from .analysis_jobs import AnalysisJobs
        active=self._analysis.active(params.get('job_id')) if self._analysis and isinstance(params,dict) else False
        return AnalysisJobs(self.database).status(params,active)

    def start_embedding(self, params):
        from .embedding_engine import EmbeddingEngine
        if self._embedding is None:self._embedding=EmbeddingEngine(self.database)
        return self._embedding.start(self.database,params)

    def rebuild_embedding(self, params):
        from .embedding_engine import EmbeddingEngine
        if self._embedding is None:self._embedding=EmbeddingEngine(self.database)
        return self._embedding.rebuild(self.database,params)

    def query_embedding(self, params):
        from .embedding_engine import EmbeddingEngine
        if self._embedding is None:self._embedding=EmbeddingEngine(self.database)
        return self._embedding.query(self.database,params)

    def embedding_work(self, params):
        from .embedding_engine import work_status
        result=work_status(self.database,params)
        if result['status'] in ('queued','running') and not (self._embedding and self._embedding.active(params['job_id'])):result['status']='interrupted'
        return result

    def close(self):
        if self._analysis:self._analysis.close()
        if self._embedding:self._embedding.close()

    def health(self):
        """Measure this live process without opening a database or starting jobs."""
        return {
            "core": {
                "status": "ready",
                "version": __version__,
                "pid": os.getpid(),
                "python_version": platform.python_version(),
                "uptime_ms": max(0, (time.monotonic_ns() - self._started_at) // 1_000_000),
            },
            "database": self.database.health() if self.database is not None else {"status": "not_configured"},
        }

    def handle(self, request):
        """Return a safe envelope. Only explicitly allowlisted methods can run."""
        request_id = None
        try:
            if not isinstance(request, dict):
                return self.error(None, "INVALID_REQUEST", "요청 형식이 올바르지 않습니다.")
            candidate = request.get("request_id")
            if not isinstance(candidate, str) or len(candidate) != 36:
                return self.error(None, "INVALID_REQUEST", "요청 ID가 올바르지 않습니다.")
            try:
                if str(UUID(candidate)) != candidate.lower():
                    raise ValueError
            except ValueError:
                return self.error(None, "INVALID_REQUEST", "요청 ID가 올바르지 않습니다.")
            request_id = candidate
            if set(request) - {"request_id", "method", "params"}:
                return self.error(request_id, "INVALID_REQUEST", "지원하지 않는 요청 필드입니다.")
            method = request.get("method")
            if not isinstance(method, str) or not method:
                return self.error(request_id, "INVALID_REQUEST", "명령 형식이 올바르지 않습니다.")
            if method in ('mcp.audit','mcp.connection'):
                from .libraries import LibraryError,ERROR_MESSAGES
                from .mcp_audit import read
                from .mcp_admin import connection
                try:
                    data=read(self.database,request.get('params',{})) if method=='mcp.audit' else connection(self.database,self._broker,request.get('params',{}))
                    return self._response(request_id,data=data)
                except LibraryError as error:
                    code=str(error) if str(error) in ERROR_MESSAGES else 'DB_UNAVAILABLE'
                    return self.error(request_id,code,ERROR_MESSAGES[code])
            if method not in {"catalog.classification", "catalog.classification.save", "catalog.evidence_candidates", "catalog.options", "catalog.scope", "creator.delete.preview", "creator.delete", "source.delete.preview", "license.delete.preview", "provenance.history", "provenance.export", "license.list", "license.get", "license.create", "license.update", "license.delete", "license.evidence.save", "source.list", "source.get", "source.create", "source.update", "source.delete", "creator.links", "creator.links.save", "creator.list", "creator.get", "creator.create", "creator.update", "creator.set_enabled", "health.get", "library.register", "library.unregister", "library.list", "library.scan", "asset.list", "asset.thumbnail", "asset.get", "asset.management", "asset.management.save", "asset.composition", "asset.composition.save", "asset.link.candidates", "asset.relations", "asset.relations.save", "asset.metadata.history", "asset.groups.list", "asset.groups.create", "asset.groups.update", "asset.groups.delete", "asset.groups.membership", "asset.groups.assign", "asset.groups.move", "asset.groups.query", "asset.groups.batch_preview", "asset.groups.batch_apply", "asset.packages.list", "asset.packages.create", "asset.packages.update", "asset.packages.delete", "asset.packages.membership", "asset.packages.assign", "asset.packages.defaults", "asset.packages.effective", "asset.packages.override", "asset.annotations", "asset.tags", "asset.annotate", "asset.tags.batch", "asset.search", "model.register", "model.list", "model.inspect", "model.credential", "model.policy", "model.validate", "model.select", "analysis.preview", "analysis.start", "analysis.status", "asset.analysis", "analysis.jobs", "analysis.cancel", "analysis.retry_plan", "asset.analysis.history", "embedding.configure", "embedding.status", "embedding.start", "embedding.work", "embedding.query", "embedding.rebuild"}:
                return self.error(request_id, "METHOD_NOT_FOUND", "지원하지 않는 명령입니다.")
            if method=='analysis.start' and (not isinstance(request.get('params'),dict) or request['params'].get('confirmed') is not True):
                return self.error(request_id,'INVALID_PARAMS','명시적 분석 시작 승인이 필요합니다.')
            if method.startswith(('catalog.', 'provenance.', 'license.', 'source.', 'creator.', 'library.', 'asset.', 'model.', 'analysis.', 'embedding.')):
                from .libraries import LibraryService, LibraryError, ERROR_MESSAGES
                import sqlite3
                try:
                    service = LibraryService(self.database)
                    from .assets import AssetService
                    from .thumbnails import thumbnail
                    from .annotations import AnnotationService
                    from .asset_management import AssetManagement
                    from .collections import Collections
                    from .packages import Packages
                    from .creators import Creators
                    from .provenance import Provenance
                    from .source_records import Sources
                    from .license_records import Licenses
                    from .provenance_policy import ProvenancePolicy
                    from .catalog import Catalog
                    from .search import SearchService
                    from .models import ModelService
                    from .analysis_plan import AnalysisPlan
                    from .analysis_jobs import AnalysisJobs
                    from .analysis_results import AssetAnalysis
                    from .embeddings import Embeddings
                    action = {'catalog.classification': Catalog(self.database).classification, 'catalog.classification.save': Catalog(self.database).save_classification, 'catalog.evidence_candidates': Catalog(self.database).evidence_candidates, 'catalog.options': Catalog(self.database).options, 'catalog.scope': Catalog(self.database).scope, 'creator.delete.preview': ProvenancePolicy(self.database).delete_creator_preview, 'creator.delete': ProvenancePolicy(self.database).delete_creator, 'source.delete.preview': Sources(self.database).delete_preview, 'license.delete.preview': Licenses(self.database).delete_preview, 'provenance.history': ProvenancePolicy(self.database).history, 'provenance.export': ProvenancePolicy(self.database).export, 'license.list': Licenses(self.database).list_records, 'license.get': Licenses(self.database).get_record, 'license.create': Licenses(self.database).create_record, 'license.update': Licenses(self.database).update_record, 'license.delete': Licenses(self.database).delete_record, 'license.evidence.save': Licenses(self.database).save_evidence, 'source.list': Sources(self.database).list_records, 'source.get': Sources(self.database).get_record, 'source.create': Sources(self.database).create_record, 'source.update': Sources(self.database).update_record, 'source.delete': Sources(self.database).delete_record, 'creator.links': Provenance(self.database).links, 'creator.links.save': Provenance(self.database).save_links, 'creator.list': Creators(self.database).list, 'creator.get': Creators(self.database).get, 'creator.create': Creators(self.database).create, 'creator.update': Creators(self.database).update, 'creator.set_enabled': Creators(self.database).set_enabled, 'asset.packages.override': Packages(self.database).package_override, 'asset.packages.effective': Packages(self.database).package_effective, 'asset.packages.defaults': Packages(self.database).package_defaults, 'asset.packages.assign': Packages(self.database).package_assign, 'asset.packages.membership': Packages(self.database).package_membership, 'asset.packages.delete': Packages(self.database).package_delete, 'asset.packages.update': Packages(self.database).package_update, 'asset.packages.create': Packages(self.database).package_create, 'asset.packages.list': Packages(self.database).package_list, 'asset.groups.batch_apply': Collections(self.database).group_batch_apply, 'asset.groups.batch_preview': Collections(self.database).group_batch_preview, 'asset.groups.query': Collections(self.database).group_query, 'asset.groups.move': Collections(self.database).group_move, 'asset.groups.assign': Collections(self.database).group_assign, 'asset.groups.membership': Collections(self.database).group_membership, 'asset.groups.delete': Collections(self.database).group_delete, 'asset.groups.update': Collections(self.database).group_update, 'asset.groups.create': Collections(self.database).group_create, 'asset.groups.list': Collections(self.database).group_list, 'asset.metadata.history': AssetManagement(self.database).history, 'asset.relations.save': AssetManagement(self.database).save_relations, 'asset.relations': AssetManagement(self.database).relations, 'asset.link.candidates': AssetManagement(self.database).candidates, 'asset.composition.save': AssetManagement(self.database).save_composition, 'asset.composition': AssetManagement(self.database).composition, 'asset.management': AssetManagement(self.database).read, 'asset.management.save': AssetManagement(self.database).save_management, 'embedding.rebuild': self.rebuild_embedding, 'embedding.query': self.query_embedding, 'embedding.start': self.start_embedding, 'embedding.work': self.embedding_work, 'embedding.configure': Embeddings(self.database).configure, 'embedding.status': Embeddings(self.database).status, 'asset.analysis.history': AssetAnalysis(self.database).history, 'analysis.cancel': self.cancel_analysis, 'analysis.retry_plan': AnalysisJobs(self.database).retry_plan, 'analysis.jobs': AnalysisJobs(self.database).list, 'analysis.start': self.start_analysis, 'analysis.status': self.analysis_status, 'asset.analysis': AssetAnalysis(self.database).get, 'analysis.preview': AnalysisPlan(self.database).preview, 'model.validate': ModelService(self.database).validate, 'model.select': ModelService(self.database).select, 'model.policy': ModelService(self.database).policy, 'model.credential': ModelService(self.database).credential, 'model.inspect': ModelService(self.database).inspect, 'model.register': ModelService(self.database).register, 'model.list': ModelService(self.database).list, 'asset.search': SearchService(self.database).search, 'asset.tags.batch': AnnotationService(self.database).batch, 'asset.annotate': AnnotationService(self.database).save, 'asset.annotations': AnnotationService(self.database).get, 'asset.tags': AnnotationService(self.database).tags, 'library.register': service.register, 'library.unregister': service.unregister,
                              'library.list': service.list, 'library.scan': AssetService(self.database).scan,
                              'asset.list': AssetService(self.database).list, 'asset.get': AssetService(self.database).get,
                              'asset.thumbnail': lambda params: thumbnail(self.database, params)}[method]
                    result = action(request.get('params', {}))
                    if method in ('creator.create', 'creator.update', 'creator.set_enabled'): result = Creators.public(result)
                    return self._response(request_id, data=result)
                except LibraryError as error:
                    code = str(error) if str(error) in ERROR_MESSAGES else 'DB_UNAVAILABLE'
                    return self.error(request_id, code, ERROR_MESSAGES[code])
                except sqlite3.Error:
                    return self.error(request_id, 'DB_UNAVAILABLE', ERROR_MESSAGES['DB_UNAVAILABLE'])
            if request.get("params", {}) != {}:
                return self.error(request_id, "INVALID_PARAMS", "이 명령은 입력 매개변수를 받지 않습니다.")
            return self._response(request_id, data=self.health())
        except Exception:
            # Never expose exception messages, arguments, paths, environment, or tracebacks.
            return self.error(request_id, "INTERNAL_ERROR", "Core 상태를 확인하지 못했습니다.", retryable=True)

    @staticmethod
    def _response(request_id, *, data=None, error=None):
        return {
            "request_id": request_id,
            "ok": error is None,
            "data": data,
            "error": error,
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        }

    @classmethod
    def error(cls, request_id, code, message, *, retryable=False):
        return cls._response(request_id, error={"code": code, "message": message, "retryable": retryable})
