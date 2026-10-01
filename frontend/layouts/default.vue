<script setup lang="ts">
import { useAuthStore } from '~/stores/auth'

const auth = useAuthStore()
const route = useRoute()

const isLoginPage = computed(() => route.path === '/login')

if (process.client && !auth.user) {
  auth.hydrate()
}
</script>

<template>
  <div v-if="isLoginPage" class="min-h-screen">
    <PToast />
    <slot />
  </div>
  <div v-else class="app-shell md:min-h-screen md:flex bg-slate-100">
    <PToast />
    <PConfirmDialog />
    <AppSidebar />
    <main class="flex-1 min-w-0 p-4 md:p-6 overflow-auto">
      <slot />
    </main>
  </div>
</template>
