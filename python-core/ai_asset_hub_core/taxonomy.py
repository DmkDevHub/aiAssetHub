"""Versioned type contract only. No DB, filesystem, model or automatic classification."""
from dataclasses import dataclass
import re
import unicodedata

VERSION='asset-types.v1'


class TaxonomyError(ValueError):pass


def normalized(value):
    if not isinstance(value,str) or not value.strip() or len(value)>128 or any(unicodedata.category(c).startswith('C') for c in value):raise TaxonomyError('INVALID_CATEGORY')
    return ' '.join(unicodedata.normalize('NFKC',value).casefold().split())


@dataclass(frozen=True)
class Category:
    code:str
    parent:str|None
    ko:str
    en:str
    aliases:tuple[str,...]=()
    active:bool=True


class Taxonomy:
    def __init__(self,nodes,version=VERSION):
        normalized(version);self.version=version;self._nodes={};self._aliases={}
        for node in nodes:
            if not isinstance(node,Category) or not re.fullmatch(r'A(?:0[1-9]|1[0-4])(?:\.[0-9]{2}){0,2}',node.code) or node.code in self._nodes or type(node.active) is not bool or not isinstance(node.aliases,tuple):raise TaxonomyError('INVALID_CATEGORY')
            self._nodes[node.code]=node
            for label in (node.code,node.ko,node.en,*node.aliases):
                key=normalized(label)
                if key in self._aliases and self._aliases[key]!=node.code:raise TaxonomyError('AMBIGUOUS_CATEGORY')
                self._aliases[key]=node.code
        for node in self._nodes.values():
            expected=node.code.rpartition('.')[0] or None
            if node.parent!=expected or expected and expected not in self._nodes:raise TaxonomyError('INVALID_PARENT')

    def resolve(self,value):
        code=self._aliases.get(normalized(value))
        if code is None or not self._nodes[code].active:raise TaxonomyError('CATEGORY_UNAVAILABLE')
        return code

    def path(self,value):
        code=self.resolve(value);parts=code.split('.')
        path=['.'.join(parts[:i]) for i in range(1,len(parts)+1)]
        if any(not self._nodes[p].active for p in path):raise TaxonomyError('CATEGORY_UNAVAILABLE')
        return path

    def contract(self):
        return {'version':self.version,'categories':[{'code':n.code,'parent':n.parent,'labels':{'ko':n.ko,'en':n.en},'aliases':list(n.aliases),'active':n.active,'depth':n.code.count('.')+1} for n in sorted(self._nodes.values(),key=lambda n:n.code)]}

    def assignment(self,primary=None,navigation=(),*,version):
        if version!=self.version:raise TaxonomyError('TAXONOMY_VERSION_MISMATCH')
        if not isinstance(navigation,(list,tuple)) or len(navigation)>32:raise TaxonomyError('INVALID_CLASSIFICATION')
        primary_path=self.path(primary) if primary is not None else []
        codes=list(dict.fromkeys(self.path(c)[-1] for c in navigation))
        def related(a,b):return a==b or a.startswith(b+'.') or b.startswith(a+'.')
        codes=[c for c in codes if not primary_path or not related(c,primary_path[-1])]
        codes=[c for c in codes if not any(other.startswith(c+'.') for other in codes)]
        return {'version':version,'primary':primary_path[-1] if primary_path else None,'primaryPath':primary_path,'navigation':sorted(codes)}


# IDs are stable published contract values, not inferred from a file extension.
_SEED=(
 ('2D 그래픽','2D Graphics','스프라이트|배경 이미지|일러스트|아이콘|아틀라스','Sprite|Background Image|Illustration|Icon|Atlas'),
 ('3D 모델','3D Model','캐릭터 모델|무기 모델|건축물 모델|소품 모델|탈것 모델','Character Model|Weapon Model|Building Model|Prop Model|Vehicle Model'),
 ('애니메이션','Animation','2D 애니메이션|3D 모션|리깅|표정 애니메이션','2D Animation|3D Motion|Rigging|Facial Animation'),
 ('텍스처·머티리얼','Textures and Materials','PBR 맵|표면 텍스처|머티리얼|셰이더','PBR Map|Surface Texture|Material|Shader'),
 ('시각 효과(VFX)','Visual Effects','파티클|마법 효과|폭발 효과|날씨 효과|상태 효과','Particle|Magic Effect|Explosion Effect|Weather Effect|Status Effect'),
 ('오디오','Audio','BGM|효과음|음성|환경음','Background Music|Sound Effect|Voice|Ambience'),
 ('UI·UX','UI and UX','버튼|패널|HUD|인벤토리 UI|메뉴','Button|Panel|Heads-Up Display|Inventory UI|Menu'),
 ('환경·월드','Environment and World','타일셋|지형|맵|스카이박스','Tileset|Terrain|Map|Skybox'),
 ('캐릭터·아바타','Characters and Avatars','캐릭터 세트|외형|의상|장비 구성','Character Set|Appearance|Clothing|Equipment Set'),
 ('게임플레이 데이터','Gameplay Data','카드 데이터|아이템 데이터|스킬 데이터|능력치|퀘스트','Card Data|Item Data|Skill Data|Stats|Quest'),
 ('폰트·텍스트','Fonts and Text','폰트|대사|자막|다국어 데이터','Font|Dialogue|Subtitle|Localization Data'),
 ('코드·기능','Code and Functionality','스크립트|플러그인|게임 시스템','Script|Plugin|Game System'),
 ('씬·프리팹','Scenes and Prefabs','씬|프리팹|재사용 오브젝트|템플릿','Scene|Prefab|Reusable Object|Template'),
 ('패키지·프로젝트','Packages and Projects','에셋 팩|Unity 패키지|프로젝트','Asset Pack|Unity Package|Project'),
)


def default_taxonomy():
    nodes=[]
    for index,(ko,en,children_ko,children_en) in enumerate(_SEED,1):
        code=f'A{index:02}';nodes.append(Category(code,None,ko,en))
        for child,(label_ko,label_en) in enumerate(zip(children_ko.split('|'),children_en.split('|'),strict=True),1):
            nodes.append(Category(f'{code}.{child:02}',code,label_ko,label_en))
    nodes.extend((Category('A02.01.01','A02.01','인간 캐릭터 모델','Human Character Model',('humanoid character model',)),
                  Category('A03.02.01','A03.02','걷기 모션','Walk Motion',('walking animation','보행 모션')),
                  Category('A06.02.01','A06.02','금속 충돌 효과음','Metal Impact Sound',('metal hit','금속 타격음'))))
    return Taxonomy(nodes)
