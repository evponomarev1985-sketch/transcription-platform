<script setup lang="ts">
import { useForm } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/zod'
import { z } from 'zod'
import { useToast } from 'primevue/usetoast'
import { useAuthStore } from '~/stores/auth'
import type { AuthTokensResponse } from '~/types/auth'

const toast = useToast()
const auth = useAuthStore()
const { apiFetch } = useApi()
const router = useRouter()

const schema = toTypedSchema(
  z.object({
    login_or_email: z.string().min(3, 'Минимум 3 символа'),
    password: z.string().min(8, 'Минимум 8 символов'),
  }),
)

const { handleSubmit, errors, defineField, isSubmitting } = useForm({
  validationSchema: schema,
  initialValues: {
    login_or_email: '',
    password: '',
  },
})

const [login] = defineField('login_or_email')
const [password] = defineField('password')

const onSubmit = handleSubmit(async (values) => {
  try {
    const data = await apiFetch<AuthTokensResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify(values),
    })
    auth.setSession(data.access_token, data.refresh_token, data.user)
    router.push('/')
  } catch (error) {
    toast.add({ severity: 'error', summary: 'Ошибка входа', detail: (error as Error).message, life: 3000 })
  }
})
</script>

<template>
  <div class="min-h-screen grid place-items-center p-6">
    <div class="w-full max-w-md bg-white border border-slate-200 rounded-2xl p-6 md:p-8 shadow-sm">
      <div class="mb-6">
        <h1 class="text-2xl font-semibold text-slate-800">Вход в систему</h1>
        <p class="text-slate-500 mt-1 text-sm">Корпоративная платформа транскрибации</p>
      </div>

      <form class="space-y-4" @submit.prevent="onSubmit">
        <div>
          <label for="login" class="block text-sm font-medium text-slate-700 mb-1">Логин или email</label>
          <input
            id="login"
            v-model="login"
            autocomplete="username"
            class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none transition focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
            type="text"
          />
          <div class="text-xs text-red-600 mt-1">{{ errors.login_or_email }}</div>
        </div>

        <div>
          <label for="password" class="block text-sm font-medium text-slate-700 mb-1">Пароль</label>
          <input
            id="password"
            v-model="password"
            autocomplete="current-password"
            class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none transition focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
            type="password"
          />
          <div class="text-xs text-red-600 mt-1">{{ errors.password }}</div>
        </div>

        <PButton type="submit" label="Войти" class="w-full" :loading="isSubmitting" />
      </form>

      <div class="mt-4 text-sm text-slate-600 text-center">
        Нет аккаунта?
        <NuxtLink to="/register" class="text-brand-700 hover:underline">Зарегистрироваться</NuxtLink>
      </div>
    </div>
  </div>
</template>
