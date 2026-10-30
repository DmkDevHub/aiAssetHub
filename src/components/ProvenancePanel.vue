<script setup lang="ts">
import {ref,computed,watch,onBeforeUnmount} from 'vue';
import {invoke,isTauri} from '@tauri-apps/api/core';
import CreatorLinks from './CreatorLinks.vue';
import ProvenanceRecords from './ProvenanceRecords.vue';
const props=defineProps<{assetId:string;area:'source'|'license'}>();const packageId=ref(''),packages=ref<{id:string;name:string}[]>([]),error=ref('');let epoch=0;onBeforeUnmount(()=>epoch++);
const subject=computed(()=>({kind:packageId.value?'package':'asset',id:packageId.value||props.assetId}));
watch(()=>props.assetId,async()=>{const token=++epoch;packageId.value='';packages.value=[];error.value='';if(!isTauri())return;try{const r=await invoke<{ok:boolean;data:{items:{id:string;name:string}[]}}>('package_membership',{assetId:props.assetId});if(token!==epoch)return;if(!r.ok)throw new Error();packages.value=r.data.items;}catch{if(token===epoch)error.value='패키지 적용 범위를 확인하지 못했습니다.';}},{immediate:true});
</script>
<template><section aria-label="제작·권리 적용 범위"><label>편집 적용 범위<select v-model="packageId"><option value="">선택한 에셋</option><option v-for="p in packages" :key="p.id" :value="p.id">공유 패키지: {{p.name}}</option></select></label><p v-if="packageId">이 패키지의 공유 기록을 수정합니다. 소속된 다른 에셋에도 같은 기록이 조회됩니다.</p><p v-if="error" role="alert">{{error}}</p><CreatorLinks v-if="area==='source'" :subject="subject" /><ProvenanceRecords :subject="subject" :area="area" /></section></template>
