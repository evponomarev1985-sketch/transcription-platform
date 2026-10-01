<script setup lang="ts">
import type { CallStatus } from '~/types/calls'

const props = defineProps<{
  status: CallStatus
}>()

const severity = computed(() => {
  switch (props.status) {
    case 'COMPLETED':
      return 'success'
    case 'FAILED':
      return 'danger'
    case 'PROCESSING':
      return 'info'
    default:
      return 'warning'
  }
})
</script>

<template>
  <PTag :value="status" :severity="severity" rounded />
</template>
