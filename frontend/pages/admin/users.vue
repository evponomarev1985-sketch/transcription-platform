<script setup lang="ts">
import { useToast } from 'primevue/usetoast'
import type { User } from '~/types/auth'

const toast = useToast()
const { apiFetch } = useApi()

const users = ref<User[]>([])
const loading = ref(true)

const createDialog = ref(false)
const form = ref({ login: '', email: '', password: '', role: 'USER' as 'USER' | 'ADMIN' })

async function loadUsers() {
  loading.value = true
  try {
    const data = await apiFetch<{ items: User[]; page: number; size: number; total: number }>('/admin/users?page=1&size=100')
    users.value = data.items
  } catch (error) {
    toast.add({ severity: 'error', summary: 'Ошибка', detail: (error as Error).message, life: 3000 })
  } finally {
    loading.value = false
  }
}

onMounted(loadUsers)

async function createUser() {
  try {
    await apiFetch('/admin/users', {
      method: 'POST',
      body: JSON.stringify({
        login: form.value.login,
        email: form.value.email || null,
        password: form.value.password,
        role: form.value.role,
        is_active: true,
      }),
    })
    createDialog.value = false
    form.value = { login: '', email: '', password: '', role: 'USER' }
    toast.add({ severity: 'success', summary: 'Создано', detail: 'Пользователь добавлен', life: 2500 })
    await loadUsers()
  } catch (error) {
    toast.add({ severity: 'error', summary: 'Ошибка', detail: (error as Error).message, life: 3000 })
  }
}

async function toggleBlocked(user: User) {
  try {
    await apiFetch(`/admin/users/${user.id}`, {
      method: 'PATCH',
      body: JSON.stringify({ is_blocked: !user.is_blocked }),
    })
    await loadUsers()
  } catch (error) {
    toast.add({ severity: 'error', summary: 'Ошибка', detail: (error as Error).message, life: 3000 })
  }
}
</script>

<template>
  <section class="space-y-4">
    <div class="flex items-center justify-between">
      <h1 class="text-2xl font-semibold text-slate-800">Администрирование пользователей</h1>
      <PButton label="Добавить" icon="pi pi-plus" @click="createDialog = true" />
    </div>

    <div class="bg-white border border-slate-200 rounded-xl p-3">
      <div v-if="loading" class="space-y-2 p-2">
        <PSkeleton height="2rem" />
        <PSkeleton height="2rem" />
      </div>

      <PDataTable v-else :value="users" stripedRows>
        <PColumn field="login" header="Логин" />
        <PColumn field="email" header="Email" />
        <PColumn field="role" header="Роль" />
        <PColumn header="Статус">
          <template #body="slotProps">
            <PTag :value="slotProps.data.is_blocked ? 'BLOCKED' : 'ACTIVE'" :severity="slotProps.data.is_blocked ? 'danger' : 'success'" />
          </template>
        </PColumn>
        <PColumn header="Действия">
          <template #body="slotProps">
            <PButton
              :label="slotProps.data.is_blocked ? 'Разблокировать' : 'Блокировать'"
              size="small"
              severity="secondary"
              outlined
              @click="toggleBlocked(slotProps.data)"
            />
          </template>
        </PColumn>
      </PDataTable>
    </div>

    <PDialog v-model:visible="createDialog" modal header="Создать пользователя" :style="{ width: '32rem' }">
      <div class="space-y-3">
        <div>
          <label class="block text-sm mb-1">Логин</label>
          <PInputText v-model="form.login" class="w-full" />
        </div>
        <div>
          <label class="block text-sm mb-1">Email</label>
          <PInputText v-model="form.email" class="w-full" />
        </div>
        <div>
          <label class="block text-sm mb-1">Пароль</label>
          <PPassword v-model="form.password" class="w-full" :feedback="false" toggle-mask />
        </div>
        <div>
          <label class="block text-sm mb-1">Роль</label>
          <PInputText v-model="form.role" class="w-full" />
        </div>
      </div>

      <template #footer>
        <PButton label="Отмена" severity="secondary" text @click="createDialog = false" />
        <PButton label="Создать" @click="createUser" />
      </template>
    </PDialog>
  </section>
</template>
