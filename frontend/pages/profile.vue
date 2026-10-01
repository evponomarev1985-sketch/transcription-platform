<script setup lang="ts">
import { useForm } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/zod'
import { z } from 'zod'
import { useToast } from 'primevue/usetoast'
import { useAuthStore } from '~/stores/auth'
import type { User } from '~/types/auth'

const auth = useAuthStore()
const toast = useToast()
const { apiFetch } = useApi()

const profileForm = reactive({
  first_name: '',
  last_name: '',
  work_email: '',
  company_name: '',
  marketing_consent: false,
})

watch(
  () => auth.user,
  (user) => {
    if (!user) return
    profileForm.first_name = user.first_name || ''
    profileForm.last_name = user.last_name || ''
    profileForm.work_email = user.email || ''
    profileForm.company_name = user.company_name || ''
    profileForm.marketing_consent = user.marketing_consent || false
  },
  { immediate: true },
)

const profileSaving = ref(false)

async function saveProfile() {
  try {
    profileSaving.value = true
    const user = await apiFetch<User>('/auth/me', {
      method: 'PATCH',
      body: JSON.stringify(profileForm),
    })
    if (auth.accessToken && auth.refreshToken) {
      auth.setSession(auth.accessToken, auth.refreshToken, user)
    }
    toast.add({ severity: 'success', summary: 'Готово', detail: 'Профиль обновлен', life: 2500 })
  } catch (error) {
    toast.add({ severity: 'error', summary: 'Ошибка', detail: (error as Error).message, life: 3000 })
  } finally {
    profileSaving.value = false
  }
}

const schema = toTypedSchema(
  z.object({
    old_password: z.string().min(8),
    new_password: z.string().min(8),
  }),
)

const { handleSubmit, defineField, errors, isSubmitting, resetForm } = useForm({
  validationSchema: schema,
})

const [oldPassword] = defineField('old_password')
const [newPassword] = defineField('new_password')

const onSubmit = handleSubmit(async (values) => {
  try {
    await apiFetch('/auth/password', {
      method: 'PATCH',
      body: JSON.stringify(values),
    })
    resetForm()
    toast.add({ severity: 'success', summary: 'Готово', detail: 'Пароль обновлён', life: 2500 })
  } catch (error) {
    toast.add({ severity: 'error', summary: 'Ошибка', detail: (error as Error).message, life: 3000 })
  }
})
</script>

<template>
  <section class="space-y-5 max-w-2xl">
    <h1 class="text-2xl font-semibold text-slate-800">Профиль</h1>

    <div class="bg-white border border-slate-200 rounded-xl p-5 space-y-2">
      <div class="text-slate-800 font-medium">{{ auth.user?.login }}</div>
      <div class="text-slate-500 text-sm">Роль: {{ auth.user?.role }}</div>
      <div class="text-slate-500 text-sm">Email: {{ auth.user?.email || 'не указан' }}</div>
    </div>

    <form class="bg-white border border-slate-200 rounded-xl p-5 space-y-4" @submit.prevent="saveProfile">
      <h2 class="text-lg font-semibold text-slate-800">Данные профиля</h2>

      <div class="grid md:grid-cols-2 gap-4">
        <div>
          <label class="block text-sm text-slate-700 mb-1">Имя</label>
          <PInputText v-model="profileForm.first_name" class="w-full" />
        </div>
        <div>
          <label class="block text-sm text-slate-700 mb-1">Фамилия</label>
          <PInputText v-model="profileForm.last_name" class="w-full" />
        </div>
      </div>

      <div>
        <label class="block text-sm text-slate-700 mb-1">Рабочий email</label>
        <PInputText v-model="profileForm.work_email" class="w-full" />
      </div>

      <div>
        <label class="block text-sm text-slate-700 mb-1">Организация</label>
        <PInputText v-model="profileForm.company_name" class="w-full" />
      </div>

      <label class="flex items-center gap-2 text-sm text-slate-700">
        <input v-model="profileForm.marketing_consent" type="checkbox" />
        <span>Получать маркетинговые рассылки</span>
      </label>

      <PButton type="submit" label="Сохранить профиль" :loading="profileSaving" />
    </form>

    <form class="bg-white border border-slate-200 rounded-xl p-5 space-y-4" @submit.prevent="onSubmit">
      <h2 class="text-lg font-semibold text-slate-800">Смена пароля</h2>

      <div>
        <label class="block text-sm text-slate-700 mb-1">Текущий пароль</label>
        <PPassword v-model="oldPassword" class="w-full" :feedback="false" toggle-mask />
        <div class="text-xs text-red-600 mt-1">{{ errors.old_password }}</div>
      </div>

      <div>
        <label class="block text-sm text-slate-700 mb-1">Новый пароль</label>
        <PPassword v-model="newPassword" class="w-full" :feedback="false" toggle-mask />
        <div class="text-xs text-red-600 mt-1">{{ errors.new_password }}</div>
      </div>

      <PButton type="submit" label="Обновить пароль" :loading="isSubmitting" />
    </form>
  </section>
</template>
