import {reactive} from 'vue';
export const collectionUi=reactive({groupId:null as string|null,revision:0});
export function selectGroup(id:string|null){collectionUi.groupId=id;}
export function collectionsChanged(){collectionUi.revision++;}
export function resetCollections(){collectionUi.groupId=null;collectionUi.revision=0;}
