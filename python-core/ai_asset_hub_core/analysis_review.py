"""Review an actual immutable AI result before changing user classification."""
import copy
import json
from .analysis_contract import digest
from .analysis_features import suggestions
from .catalog import Catalog
from .libraries import LibraryError,valid_id
from .metadata_values import MetadataError
from .taxonomy import TaxonomyError


class AnalysisReview(Catalog):
    def preview(self,params):
        self.keys(params,'asset_id result_id');self.require_asset(params['asset_id'])
        if not valid_id(params['result_id']):raise LibraryError('INVALID_PARAMS')
        row=self.db.execute('SELECT features_json FROM analysis_results WHERE id=? AND asset_id=?',(params['result_id'],params['asset_id'])).fetchone()
        if not row:raise LibraryError('INVALID_PARAMS')
        proposal=suggestions(json.loads(row[0]).get('suggestions',{}))
        before=self.classification({'asset_id':params['asset_id']});after=copy.deepcopy(before['value'])
        if proposal.get('primary'):after['primary']=proposal['primary']
        for key,axis in (('roles','role'),('styles','style')):
            if proposal[key]:after['facets'][axis]=proposal[key]
        try:
            types=self.metadata.dictionary(after['type_version'],'type');axes=self.metadata.dictionary(after['facet_version'],'facet')
            types.assignment(after['primary'],after['navigation'],version=types.version)
            axes.assignment(after['facets'],version=axes.version)
        except (MetadataError,TaxonomyError):raise LibraryError('INVALID_PARAMS') from None
        result={'assetId':params['asset_id'],'resultId':params['result_id'],'before':before['value'],
            'after':after,'expectedRevision':before['revision'],'hasChanges':before['value']!=after,
            'inferenceCalled':False}
        result['planToken']=digest(result)
        return result

    def apply(self,params):
        self.keys(params,'asset_id result_id plan_token expected_revision confirmed')
        if params['confirmed'] is not True or type(params['expected_revision']) is not int:raise LibraryError('INVALID_PARAMS')
        preview=self.preview({k:params[k] for k in ('asset_id','result_id')})
        if params['plan_token']!=preview['planToken'] or params['expected_revision']!=preview['expectedRevision']:raise LibraryError('METADATA_CONFLICT')
        if not preview['hasChanges']:raise LibraryError('INVALID_PARAMS')
        return self.save_classification({'asset_id':params['asset_id'],'value':preview['after'],
            'expected_revision':params['expected_revision'],'confirmed':True})
