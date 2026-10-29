"""Observable claims and explicit user decisions; proposals never override decisions."""
import copy
import json
from dataclasses import dataclass
from .libraries import valid_id


class MetadataError(ValueError):pass


def json_value(value):
    try:
        raw=json.dumps(value,ensure_ascii=False,allow_nan=False)
        if len(raw.encode())>16384:raise ValueError()
        return json.loads(raw)
    except (ValueError,TypeError,RecursionError):raise MetadataError('INVALID_METADATA') from None


@dataclass(frozen=True)
class Claim:
    id:str
    source:str
    value:object
    evidence:str
    schema_version:str


class FieldState:
    def __init__(self):self._claims=[];self._decision=None;self._history=[];self.revision=0

    def propose(self,claim):
        if not isinstance(claim,Claim) or not valid_id(claim.id) or claim.source not in ('file','parser','ai') or not isinstance(claim.evidence,str) or not 1<=len(claim.evidence)<=256 or not isinstance(claim.schema_version,str) or not 1<=len(claim.schema_version)<=64 or any(c.id==claim.id for c in self._claims):raise MetadataError('INVALID_METADATA')
        self._claims.append(Claim(claim.id,claim.source,json_value(claim.value),claim.evidence,claim.schema_version))

    def selected(self):
        if self._decision is not None:return copy.deepcopy(self._decision)
        # File/parser observations have priority over AI proposals until a user decides.
        for sources in (('file','parser'),('ai',)):
            for claim in reversed(self._claims):
                if claim.source in sources:return {'value':json_value(claim.value),'source':claim.source,'status':'observed' if claim.source!='ai' else 'proposed','claimId':claim.id}
        return {'value':None,'source':None,'status':'unknown','claimId':None}

    def decide(self,action,*,expected_revision,confirmed,value=None,claim_id=None):
        if type(expected_revision) is not int or expected_revision!=self.revision:raise MetadataError('METADATA_CONFLICT')
        if confirmed is not True or action not in ('set','clear','adopt'):raise MetadataError('CONFIRMATION_REQUIRED')
        before=self.selected();selected=None
        if action=='adopt':
            selected=next((c for c in self._claims if c.id==claim_id),None)
            if selected is None:raise MetadataError('CLAIM_UNAVAILABLE')
            value=selected.value
        elif claim_id is not None:raise MetadataError('INVALID_METADATA')
        if action=='clear':value=None
        after={'value':json_value(value),'source':'user','status':'cleared' if action=='clear' else 'confirmed','claimId':selected.id if selected else None}
        self._decision=after;self.revision+=1
        self._history.append({'revision':self.revision,'action':action,'before':before,'after':copy.deepcopy(after)})
        return self.selected()

    def history(self):return copy.deepcopy(self._history)
