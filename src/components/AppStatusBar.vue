<script setup lang="ts">
import { operations, operationLabels, operationStates, operationErrors, operationAlerts,
  hasClearableOperations, dismissOperationAlert, clearFinishedOperations } from '../stores/operations';
</script>

<template>
  <footer v-if="operations.length" class="app-status" aria-label="작업 상태">
    <div role="status" aria-live="polite" aria-atomic="true">
      <ul class="operation-list">
        <li v-for="operation in operations" :key="operation.id">
          <span>{{ operationLabels[operation.kind] }}: {{ operationStates[operation.state] }}</span>
          <template v-if="operation.progress">
            <progress v-if="operation.progress.total > 0" :value="operation.progress.processed" :max="operation.progress.total"
              :aria-label="`${operationLabels[operation.kind]} 처리 건수`" />
            <span>{{ operation.progress.processed }} / {{ operation.progress.total }}</span>
          </template>
        </li>
      </ul>
    </div>
    <div v-for="alert in operationAlerts" :key="alert.id" class="operation-error">
      <p role="alert">{{ operationLabels[alert.kind] }}: {{ operationErrors[alert.errorCode ?? 'COMMAND_FAILED'] }}</p>
      <button type="button" :aria-label="`${operationLabels[alert.kind]} 오류 알림 닫기`"
        @click="dismissOperationAlert(alert.id)">닫기</button>
    </div>
    <button v-if="hasClearableOperations" type="button" class="clear-operations" @click="clearFinishedOperations">
      완료된 상태 지우기
    </button>
  </footer>
</template>
