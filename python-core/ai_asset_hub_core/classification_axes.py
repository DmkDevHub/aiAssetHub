"""Independent semantic facets; no inference and no engine compatibility assertion."""
from dataclasses import dataclass,replace
from .taxonomy import normalized,TaxonomyError

VERSION='asset-facets.v1'
AXES=('role','style','genre','view','dimension','engine')


@dataclass(frozen=True)
class Term:
    axis:str
    code:str
    ko:str
    en:str
    active:bool=True
    replacement:str|None=None


class Facets:
    def __init__(self,terms,version=VERSION):
        normalized(version);self.version=version;self.terms=tuple(terms);self.index={};self.aliases={}
        for term in self.terms:
            if term.axis not in AXES or not term.code.startswith(term.axis+'.') or term.code in self.index or type(term.active) is not bool:raise TaxonomyError('INVALID_FACET')
            normalized(term.code);self.index[term.code]=term
            for value in (term.code,term.ko,term.en):
                key=(term.axis,normalized(value))
                if key in self.aliases and self.aliases[key]!=term.code:raise TaxonomyError('AMBIGUOUS_FACET')
                self.aliases[key]=term.code
        for term in self.terms:
            if term.replacement:
                target=self.index.get(term.replacement)
                if term.active or not target or target.axis!=term.axis or not target.active or target.code==term.code:raise TaxonomyError('INVALID_REPLACEMENT')

    def assignment(self,values,*,version):
        if version!=self.version:raise TaxonomyError('FACET_VERSION_MISMATCH')
        if not isinstance(values,dict) or set(values)-set(AXES):raise TaxonomyError('INVALID_FACET')
        result={}
        for axis in AXES:
            items=values.get(axis,[])
            if not isinstance(items,list) or len(items)>16:raise TaxonomyError('INVALID_FACET')
            codes=[]
            for value in items:
                code=self.aliases.get((axis,normalized(value)))
                if not code or not self.index[code].active:raise TaxonomyError('FACET_UNAVAILABLE')
                codes.append(code)
            result[axis]=sorted(set(codes))
        return {'version':version,'values':result}

    def retire(self,code,*,new_version,used=False,replacement=None,confirmed=False):
        if code not in self.index or new_version==self.version or not self.index[code].active:raise TaxonomyError('INVALID_REPLACEMENT')
        if type(used) is not bool or type(confirmed) is not bool or used and (not confirmed or replacement is None):raise TaxonomyError('CLASSIFICATION_IN_USE')
        nodes=[replace(t,active=False,replacement=replacement) if t.code==code else t for t in self.terms]
        return Facets(nodes,new_version)

    def contract(self):
        from dataclasses import asdict
        return {'version':self.version,'terms':[asdict(t) for t in self.terms]}


def default_facets():
    seed={
     'role':[('player','플레이어','Player'),('monster','몬스터','Monster'),('npc','NPC','Non-Player Character'),('weapon','무기','Weapon'),('item','아이템','Item'),('environment','환경','Environment'),('card','카드','Card')],
     'style':[('pixel','픽셀아트','Pixel Art'),('anime','애니메풍','Anime'),('cartoon','카툰','Cartoon'),('realistic','실사풍','Realistic'),('low_poly','로우폴리','Low Poly')],
     'genre':[('fantasy','판타지','Fantasy'),('sci_fi','SF','Sci-Fi'),('modern','현대','Modern'),('horror','공포','Horror')],
     'view':[('top_down','탑다운','Top-Down'),('side','측면','Side-View'),('isometric','아이소메트릭','Isometric'),('first_person','1인칭','First-Person')],
     'dimension':[('2d','2D','2D'),('2_5d','2.5D','2.5D'),('3d','3D','3D')],
     'engine':[('unity','Unity','Unity'),('godot','Godot','Godot'),('unreal','Unreal','Unreal'),('generic','범용','Generic')]}
    return Facets(Term(axis,axis+'.'+code,ko,en) for axis,terms in seed.items() for code,ko,en in terms)
