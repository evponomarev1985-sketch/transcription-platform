<script setup lang="ts">
import { useToast } from 'primevue/usetoast'
import type { CallStatus } from '~/types/calls'

interface UploadTask {
  id: string
  file: File
  title: string
  language: string
  status: CallStatus | 'NEW' | 'UPLOADING_FILE' | 'ABORTED'
  progress: number
  error: string | null
  controller: AbortController | null
  resultCallId: string | null
}

const toast = useToast()

const tasks = ref<UploadTask[]>([])

function buildTaskId() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function createTask(file: File): UploadTask {
  return {
    id: buildTaskId(),
    file,
    title: file.name.replace(/\.[^/.]+$/, ''),
    language: 'ru-RU',
    status: 'NEW',
    progress: 0,
    error: null,
    controller: null,
    resultCallId: null,
  }
}

function onFileSelect(event: Event) {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files || [])
  tasks.value.push(...files.map(createTask))
  input.value = ''
}

function onDrop(event: DragEvent) {
  event.preventDefault()
  const files = Array.from(event.dataTransfer?.files || [])
  tasks.value.push(...files.map(createTask))
}

function onDragOver(event: DragEvent) {
  event.preventDefault()
}

async function runTask(task: UploadTask) {
  task.error = null
  task.status = 'UPLOADING'
  task.progress = 5

  try {
    task.status = 'UPLOADING_FILE'
    task.progress = 15

    const complete = await directUpload(task, (p) => {
      task.progress = 15 + Math.round(p * 0.8)
    })

    task.status = complete.status
    task.resultCallId = complete.call_id
    task.progress = 100
    task.controller = null
  } catch (error) {
    const err = error as Error
    task.error = err.message
    task.status = 'FAILED'
    task.controller = null
    toast.add({ severity: 'error', summary: 'Ошибка загрузки', detail: `${task.file.name}: ${err.message}`, life: 4000 })
  }
}

async function directUpload(
  task: UploadTask,
  onProgress: (progress: number) => void,
) {
  const config = useRuntimeConfig()
  const auth = useAuthStore()

  const formData = new FormData()
  formData.append('file', task.file)
  formData.append('title', task.title)
  formData.append('language', task.language)

  const controller = new AbortController()
  task.controller = controller

  const responseText = await new Promise<string>((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${config.public.apiBase}/uploads/direct`)
    if (auth.accessToken) {
      xhr.setRequestHeader('Authorization', `Bearer ${auth.accessToken}`)
    }
    xhr.upload.onprogress = (event) => {
      if (!event.lengthComputable) return
      onProgress(event.loaded / event.total)
    }
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(xhr.responseText)
      } else {
        reject(new Error(`Upload failed with ${xhr.status}`))
      }
    }
    xhr.onerror = () => reject(new Error('Network upload error'))
    xhr.onabort = () => reject(new Error('Upload aborted'))
    controller.signal.addEventListener('abort', () => xhr.abort())
    xhr.send(formData)
  })

  return JSON.parse(responseText) as { call_id: string; status: CallStatus }
}

function runAll() {
  tasks.value.forEach((task) => {
    if (task.status === 'NEW' || task.status === 'FAILED' || task.status === 'ABORTED') {
      runTask(task)
    }
  })
}

function retryTask(task: UploadTask) {
  runTask(task)
}

async function abortTask(task: UploadTask) {
  task.controller?.abort()
  task.status = 'ABORTED'
  task.error = null
}
</script>

<template>
  <section class="space-y-5">
    <div class="flex items-center justify-between">
      <h1 class="text-2xl font-semibold text-slate-800">Загрузить звонки</h1>
      <PButton label="Запустить все" icon="pi pi-play" @click="runAll" :disabled="tasks.length === 0" />
    </div>

    <div
      class="bg-white border-2 border-dashed border-slate-300 rounded-xl p-8 text-center"
      @drop="onDrop"
      @dragover="onDragOver"
    >
      <div class="text-slate-700 font-medium">Перетащите аудиофайлы сюда</div>
      <p class="text-slate-500 text-sm mt-1">Поддерживаемые форматы: WAV, MP3, OGG, OPUS</p>
      <div class="mt-4">
        <label class="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-slate-300 cursor-pointer hover:bg-slate-50">
          <i class="pi pi-folder-open" />
          <span>Выбрать файлы</span>
          <input class="hidden" type="file" multiple accept=".wav,.mp3,.ogg,.opus,audio/*" @change="onFileSelect" />
        </label>
      </div>
    </div>

    <div v-if="tasks.length === 0" class="bg-white border border-slate-200 rounded-xl p-8 text-center text-slate-500">
      Пока нет файлов для загрузки
    </div>

    <div v-else class="space-y-3">
      <div v-for="task in tasks" :key="task.id" class="bg-white border border-slate-200 rounded-xl p-4">
        <div class="flex items-start justify-between gap-4">
          <div class="min-w-0 flex-1">
            <div class="font-medium text-slate-800 truncate">{{ task.file.name }}</div>
            <div class="text-xs text-slate-500 mt-1">
              {{ Math.round(task.file.size / 1024) }} KB
            </div>

            <div class="grid md:grid-cols-2 gap-3 mt-3">
              <div>
                <label class="block text-xs text-slate-600 mb-1">Название звонка</label>
                <PInputText v-model="task.title" class="w-full" :disabled="task.status === 'QUEUED' || task.status === 'PROCESSING' || task.status === 'COMPLETED'" />
              </div>
              <div>
                <label class="block text-xs text-slate-600 mb-1">Язык</label>
                <PInputText v-model="task.language" class="w-full" :disabled="task.status === 'QUEUED' || task.status === 'PROCESSING' || task.status === 'COMPLETED'" />
              </div>
            </div>

            <div class="mt-3">
              <PProgressBar :value="task.progress" style="height: 10px" />
            </div>

            <div class="mt-2 text-xs" :class="task.error ? 'text-red-600' : 'text-slate-600'">
              <template v-if="task.error">{{ task.error }}</template>
              <template v-else>Статус: {{ task.status }}</template>
            </div>
          </div>

          <div class="flex flex-col gap-2">
            <PButton
              v-if="task.status === 'NEW'"
              label="Загрузить"
              icon="pi pi-upload"
              size="small"
              :loading="task.status === 'UPLOADING' || task.status === 'UPLOADING_FILE'"
              @click="runTask(task)"
            />
            <PButton
              v-if="task.status === 'FAILED' || task.status === 'ABORTED'"
              label="Повторить"
              icon="pi pi-refresh"
              size="small"
              severity="secondary"
              @click="retryTask(task)"
            />
            <PButton
              v-if="task.status === 'UPLOADING' || task.status === 'UPLOADING_FILE'"
              label="Отменить"
              icon="pi pi-times"
              size="small"
              severity="danger"
              outlined
              @click="abortTask(task)"
            />
            <NuxtLink v-if="task.resultCallId" :to="`/calls/${task.resultCallId}`" class="text-xs text-brand-700 hover:underline">
              Открыть карточку
            </NuxtLink>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>
