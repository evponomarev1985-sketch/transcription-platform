<script setup lang="ts">
import { computed, ref } from 'vue'
import { useAuthStore } from '~/stores/auth'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const { apiFetch } = useApi()

const collapsed = ref(false)
const mobileOpen = ref(false)

const userInitials = computed(() => {
  const login = auth.user?.login?.trim() || ''
  if (!login) return 'U'
  return login.slice(0, 2).toUpperCase()
})

const items = computed(() => {
  const base = [
    { to: '/', label: 'Главная', icon: 'pi pi-home' },
    { to: '/calls', label: 'Звонки', icon: 'pi pi-phone' },
  ]
  if (auth.isAdmin) {
    base.push({ to: '/admin/users', label: 'Администрирование', icon: 'pi pi-cog' })
    base.push({ to: '/admin/label-rules', label: 'Правила меток', icon: 'pi pi-tags' })
    base.push({ to: '/admin/checklists', label: 'Чек-листы', icon: 'pi pi-check-square' })
  }
  return base
})

function isActive(path: string) {
  return route.path === path || route.path.startsWith(`${path}/`)
}

function openProfile() {
  mobileOpen.value = false
  router.push('/profile')
}

async function logout() {
  try {
    if (auth.refreshToken) {
      await apiFetch('/auth/logout', {
        method: 'POST',
        body: JSON.stringify({ refresh_token: auth.refreshToken }),
      })
    }
  } finally {
    auth.clearSession()
    router.push('/login')
  }
}
</script>

<template>
  <div class="md:h-screen md:sticky md:top-0 md:shrink-0">
    <div class="md:hidden p-3 border-b border-slate-200 bg-white flex items-center justify-between">
      <div class="font-semibold text-slate-800">Transcription</div>
      <PButton icon="pi pi-bars" text @click="mobileOpen = true" aria-label="Open menu" />
    </div>

    <aside
      class="hidden md:flex h-screen flex-col bg-white border-r border-slate-200 transition-all duration-200"
      :class="collapsed ? 'w-[76px]' : 'w-[236px]'"
    >
      <div class="h-16 flex items-center px-4 border-b border-slate-200 gap-3">
        <div class="w-9 h-9 rounded-lg bg-brand-600 text-white flex items-center justify-center font-semibold">T</div>
        <div v-if="!collapsed" class="font-semibold text-slate-800">Transcription Platform</div>
      </div>

      <nav class="p-3 space-y-1 flex-1">
        <NuxtLink
          v-for="item in items"
          :key="item.to"
          :to="item.to"
          class="flex items-center gap-3 rounded-lg px-3 py-2 text-sm"
          :class="isActive(item.to) ? 'bg-brand-50 text-brand-700' : 'text-slate-700 hover:bg-slate-100'"
          :aria-current="isActive(item.to) ? 'page' : undefined"
        >
          <i :class="item.icon" />
          <span v-if="!collapsed">{{ item.label }}</span>
        </NuxtLink>
      </nav>

      <div class="p-3 border-t border-slate-200 space-y-2 mt-auto">
        <div class="flex items-center gap-3 px-2 py-1">
          <button
            type="button"
            class="w-8 h-8 rounded-full bg-slate-200 flex items-center justify-center text-slate-600 text-xs font-semibold hover:bg-slate-300 transition"
            @click="openProfile"
          >
            {{ userInitials }}
          </button>
          <button
            v-if="!collapsed"
            type="button"
            class="min-w-0 text-left rounded-md px-1 py-0.5 hover:bg-slate-100 transition"
            @click="openProfile"
          >
            <div class="text-sm text-slate-800 truncate">{{ auth.user?.login }}</div>
            <div class="text-xs text-slate-500">{{ auth.user?.role }}</div>
          </button>
        </div>

        <div class="flex items-center gap-1">
          <button
            type="button"
            class="flex-1 inline-flex items-center gap-2 rounded-lg px-2.5 py-2 text-sm text-slate-600 hover:bg-slate-100 hover:text-slate-900 transition"
            @click="logout"
          >
            <i class="pi pi-sign-out" />
            <span v-if="!collapsed">Выход</span>
          </button>
          <button
            type="button"
            class="inline-flex h-9 w-9 items-center justify-center rounded-lg text-slate-500 hover:bg-slate-100 hover:text-slate-900 transition"
            @click="collapsed = !collapsed"
            :aria-label="collapsed ? 'Expand menu' : 'Collapse menu'"
          >
            <i :class="collapsed ? 'pi pi-angle-right' : 'pi pi-angle-left'" />
          </button>
        </div>
      </div>
    </aside>

    <PSidebar v-model:visible="mobileOpen" position="left" class="w-[260px]">
      <div class="font-semibold text-slate-800 mb-4">Transcription Platform</div>
      <nav class="space-y-1">
        <NuxtLink
          v-for="item in items"
          :key="item.to"
          :to="item.to"
          class="flex items-center gap-3 rounded-lg px-3 py-2 text-sm"
          :class="isActive(item.to) ? 'bg-brand-50 text-brand-700' : 'text-slate-700 hover:bg-slate-100'"
          :aria-current="isActive(item.to) ? 'page' : undefined"
          @click="mobileOpen = false"
        >
          <i :class="item.icon" />
          <span>{{ item.label }}</span>
        </NuxtLink>
      </nav>
      <div class="mt-5">
        <PButton
          :label="auth.user?.login || 'Профиль'"
          icon="pi pi-user"
          class="w-full mb-2"
          severity="secondary"
          text
          @click="openProfile"
        />
        <PButton label="Выход" icon="pi pi-sign-out" class="w-full" severity="secondary" text @click="logout" />
      </div>
    </PSidebar>
  </div>
</template>
