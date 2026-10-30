import {reactive,watch} from 'vue';
import {libraryUi,selectLibraryFolder} from './libraryUi';
import {collectionUi,selectGroup} from './collections';
export type NavigationMode='folders'|'groups'|'packages'|'types';
export const navigation=reactive({mode:'folders' as NavigationMode,selected:{folders:null,groups:null,packages:null,types:null} as Record<NavigationMode,string|null>,revision:0});
watch(()=>libraryUi.selectedFolderId,id=>{if(navigation.mode==='folders')navigation.selected.folders=id;});
watch(()=>collectionUi.groupId,id=>{if(navigation.mode==='groups')navigation.selected.groups=id;});
export function navigateMode(mode:NavigationMode){
 navigation.mode=mode;
 selectLibraryFolder(mode==='folders'?navigation.selected.folders:null);
 selectGroup(mode==='groups'?navigation.selected.groups:null);
}
export function selectCatalog(id:string|null){navigation.selected[navigation.mode]=id;if(navigation.mode==='groups')selectGroup(id);navigation.revision++;}
export function resetNavigation(){for(const key of Object.keys(navigation.selected) as NavigationMode[])navigation.selected[key]=null;navigateMode('folders');navigation.revision=0;}
