import {reactive} from 'vue';
export const smartUi=reactive({groupId:null as string|null,revision:0});
export function resetSmartGroups(){smartUi.groupId=null;smartUi.revision=0;}
