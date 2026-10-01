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
    first_name: z.string().min(1, 'Укажите имя'),
    last_name: z.string().min(1, 'Укажите фамилию'),
    work_email: z.string().email('Некорректный email'),
    company_name: z.string().min(1, 'Укажите организацию'),
    password: z.string().min(8, 'Минимум 8 символов'),
    password_confirm: z.string().min(8, 'Минимум 8 символов'),
    terms_accepted: z.boolean().refine((v) => v, 'Обязательное согласие'),
    privacy_accepted: z.boolean().refine((v) => v, 'Обязательное согласие'),
    marketing_consent: z.boolean(),
  }).refine((values) => values.password === values.password_confirm, {
    message: 'Пароли не совпадают',
    path: ['password_confirm'],
  }),
)

const { handleSubmit, errors, defineField, isSubmitting } = useForm({
  validationSchema: schema,
  initialValues: {
    first_name: '',
    last_name: '',
    work_email: '',
    company_name: '',
    password: '',
    password_confirm: '',
    terms_accepted: false,
    privacy_accepted: false,
    marketing_consent: false,
  },
})

const [firstName] = defineField('first_name')
const [lastName] = defineField('last_name')
const [workEmail] = defineField('work_email')
const [companyName] = defineField('company_name')
const [password] = defineField('password')
const [passwordConfirm] = defineField('password_confirm')
const [termsAccepted] = defineField('terms_accepted')
const [privacyAccepted] = defineField('privacy_accepted')
const [marketingConsent] = defineField('marketing_consent')

const onSubmit = handleSubmit(async (values) => {
  try {
    await apiFetch('/auth/register', {
      method: 'POST',
      body: JSON.stringify(values),
    })

    const loginData = await apiFetch<AuthTokensResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({
        login_or_email: values.work_email,
        password: values.password,
      }),
    })
    auth.setSession(loginData.access_token, loginData.refresh_token, loginData.user)
    toast.add({ severity: 'success', summary: 'Готово', detail: 'Регистрация выполнена', life: 2500 })
    router.push('/')
  } catch (error) {
    toast.add({ severity: 'error', summary: 'Ошибка регистрации', detail: (error as Error).message, life: 3000 })
  }
})
</script>

<template>
  <div class="min-h-screen grid place-items-center p-6 bg-gradient-to-b from-emerald-50 via-white to-slate-50">
    <div class="w-full max-w-2xl bg-white border border-slate-200 rounded-2xl p-6 md:p-8 shadow-sm">
      <div class="mb-6">
        <h1 class="text-2xl font-semibold text-slate-800">Регистрация</h1>
        <p class="text-slate-500 mt-1 text-sm">Создайте рабочий аккаунт для платформы транскрибации</p>
      </div>

      <form class="space-y-4" @submit.prevent="onSubmit">
        <div class="grid md:grid-cols-2 gap-4">
          <div>
            <label class="block text-sm font-medium text-slate-700 mb-1">Имя</label>
            <input v-model="firstName" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" type="text" />
            <div class="text-xs text-red-600 mt-1">{{ errors.first_name }}</div>
          </div>
          <div>
            <label class="block text-sm font-medium text-slate-700 mb-1">Фамилия</label>
            <input v-model="lastName" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" type="text" />
            <div class="text-xs text-red-600 mt-1">{{ errors.last_name }}</div>
          </div>
        </div>

        <div>
          <label class="block text-sm font-medium text-slate-700 mb-1">Рабочий email</label>
          <input v-model="workEmail" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" type="email" autocomplete="email" />
          <div class="text-xs text-red-600 mt-1">{{ errors.work_email }}</div>
        </div>

        <div>
          <label class="block text-sm font-medium text-slate-700 mb-1">Название организации</label>
          <input v-model="companyName" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" type="text" />
          <div class="text-xs text-red-600 mt-1">{{ errors.company_name }}</div>
        </div>

        <div class="grid md:grid-cols-2 gap-4">
          <div>
            <label class="block text-sm font-medium text-slate-700 mb-1">Пароль</label>
            <input v-model="password" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" type="password" autocomplete="new-password" />
            <div class="text-xs text-red-600 mt-1">{{ errors.password }}</div>
          </div>
          <div>
            <label class="block text-sm font-medium text-slate-700 mb-1">Подтверждение пароля</label>
            <input v-model="passwordConfirm" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" type="password" autocomplete="new-password" />
            <div class="text-xs text-red-600 mt-1">{{ errors.password_confirm }}</div>
          </div>
        </div>

        <div class="space-y-2">
          <label class="flex items-start gap-2 text-sm text-slate-700">
            <input v-model="termsAccepted" type="checkbox" class="mt-1" />
            <span>Согласен с условиями использования сервиса</span>
          </label>
          <div class="text-xs text-red-600">{{ errors.terms_accepted }}</div>

          <label class="flex items-start gap-2 text-sm text-slate-700">
            <input v-model="privacyAccepted" type="checkbox" class="mt-1" />
            <span>Согласен на обработку персональных данных</span>
          </label>
          <div class="text-xs text-red-600">{{ errors.privacy_accepted }}</div>

          <label class="flex items-start gap-2 text-sm text-slate-700">
            <input v-model="marketingConsent" type="checkbox" class="mt-1" />
            <span>Хочу получать маркетинговые рассылки (необязательно)</span>
          </label>
        </div>

        <PButton type="submit" label="Зарегистрироваться" class="w-full" :loading="isSubmitting" />
      </form>

      <div class="mt-4 text-sm text-slate-600 text-center">
        Уже есть аккаунт?
        <NuxtLink to="/login" class="text-emerald-700 hover:underline">Войти</NuxtLink>
      </div>
    </div>
  </div>
</template>
