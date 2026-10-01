<script setup lang="ts">
import { useAuthStore } from '~/stores/auth'

const auth = useAuthStore()
</script>

<template>
  <section class="space-y-4">
    <h1 class="text-2xl font-semibold text-slate-800">Главная</h1>
    <div class="bg-white border border-slate-200 rounded-xl p-5">
      <div class="text-slate-700">Добро пожаловать, {{ auth.user?.login }}.</div>
      <p class="text-slate-500 text-sm mt-2">
        Используйте меню слева для загрузки файлов, просмотра статусов и работы с транскрипциями.
      </p>
    </div>
  </section>
</template>
