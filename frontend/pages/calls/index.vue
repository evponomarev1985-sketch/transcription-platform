<script setup lang="ts">
import { useToast } from 'primevue/usetoast'
import type { CallItem, CallListResponse, CallStatus, LabelResult } from '~/types/calls'

const route = useRoute()
const router = useRouter()
const toast = useToast()
const { apiFetch } = useApi()
const auth = useAuthStore()
const config = useRuntimeConfig()

const page = ref(Number(route.query.page || 1))
const size = ref(Number(route.query.size || 20))
const search = ref(String(route.query.search || ''))
const status = ref(String(route.query.status || ''))
const uploadInputRef = ref<HTMLInputElement | null>(null)
const uploadPanelRef = ref<HTMLElement | null>(null)

const data = ref<CallListResponse | null>(null)
const loading = ref(false)
const selectedCallIds = ref<string[]>([])
const retryingBulk = ref(false)

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

function enqueueFiles(files: File[]) {
  if (!files.length) return
  const newTasks = files.map(createTask)
  tasks.value.unshift(...newTasks)
  newTasks.forEach((task) => {
    void runTask(task)
  })
}

function onFileSelect(event: Event) {
  const input = event.target as HTMLInputElement
  enqueueFiles(Array.from(input.files || []))
  input.value = ''
}

function onDrop(event: DragEvent) {
  event.preventDefault()
  enqueueFiles(Array.from(event.dataTransfer?.files || []))
}

function onDragOver(event: DragEvent) {
  event.preventDefault()
}

async function directUpload(task: UploadTask, onProgress: (progress: number) => void) {
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
    toast.add({ severity: 'success', summary: 'Загружено', detail: `${task.file.name} добавлен в очередь`, life: 2200 })
    if (page.value === 1) {
      void loadCalls()
    }
  } catch (error) {
    const err = error as Error
    task.error = err.message
    task.status = 'FAILED'
    task.controller = null
    toast.add({ severity: 'error', summary: 'Ошибка загрузки', detail: `${task.file.name}: ${err.message}`, life: 4000 })
  }
}

function retryTask(task: UploadTask) {
  void runTask(task)
}

function removeTask(taskId: string) {
  tasks.value = tasks.value.filter((task) => task.id !== taskId)
}

function abortTask(task: UploadTask) {
  task.controller?.abort()
  task.status = 'ABORTED'
  task.error = null
}

function openFileDialog() {
  uploadInputRef.value?.click()
}

function scrollToUpload() {
  uploadPanelRef.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

const statusOptions = [
  { label: 'Все статусы', value: '' },
  { label: 'UPLOADING', value: 'UPLOADING' },
  { label: 'QUEUED', value: 'QUEUED' },
  { label: 'PROCESSING', value: 'PROCESSING' },
  { label: 'COMPLETED', value: 'COMPLETED' },
  { label: 'FAILED', value: 'FAILED' },
]

function mapStatusLabel(raw: string) {
  const map: Record<string, string> = {
    UPLOADING: 'Загрузка',
    QUEUED: 'В очереди',
    PROCESSING: 'Обработка',
    COMPLETED: 'Готово',
    FAILED: 'Ошибка',
  }
  return map[raw] || raw
}

function statusSeverity(call: CallItem) {
  if (call.status === 'COMPLETED') return 'success'
  if (call.status === 'FAILED') return 'danger'
  if (call.status === 'PROCESSING') return 'info'
  return 'warning'
}

function progressClass(call: CallItem) {
  if (call.status === 'COMPLETED') return 'bg-emerald-500'
  if (call.status === 'FAILED') return 'bg-rose-500'
  if (call.status === 'PROCESSING') return 'bg-sky-500'
  return 'bg-amber-500'
}

function asDate(value: string) {
  return new Date(value).toLocaleString('ru-RU')
}

function labelBadgeClass(result: LabelResult) {
  if (result.label_kind === 'FLAG') return 'border-teal-200 bg-teal-50 text-teal-700'
  if (result.label_kind === 'FLAG_VALUE') return 'border-amber-200 bg-amber-50 text-amber-700'
  return 'border-violet-200 bg-violet-50 text-violet-700'
}

function labelBadgeText(result: LabelResult) {
  if (result.label_kind === 'FLAG_VALUE') {
    const val = result.value_number !== null
      ? (result.value_number === Math.floor(result.value_number) ? String(Math.floor(result.value_number)) : String(result.value_number))
      : (result.value_text || '—')
    return `${result.label_name}: ${val}`
  }
  return result.comment_title_snapshot || result.label_name || 'Комментарий'
}

async function loadCalls() {
  loading.value = true
  try {
    const params = new URLSearchParams()
    params.set('page', String(page.value))
    params.set('size', String(size.value))
    if (search.value.trim()) params.set('search', search.value.trim())
    if (status.value) params.set('status', status.value)

    data.value = await apiFetch<CallListResponse>(`/calls?${params.toString()}`)
    const ids = new Set((data.value?.items || []).map((x) => x.id))
    selectedCallIds.value = selectedCallIds.value.filter((id) => ids.has(id))
    router.replace({ query: { ...Object.fromEntries(params.entries()) } })
  } catch (error) {
    toast.add({ severity: 'error', summary: 'Ошибка', detail: (error as Error).message, life: 3000 })
  } finally {
    loading.value = false
  }
}

const allVisibleSelected = computed(() => {
  if (!items.value.length) return false
  return items.value.every((call) => selectedCallIds.value.includes(call.id))
})

const selectedCount = computed(() => selectedCallIds.value.length)

function toggleSelectAllVisible(checked: boolean) {
  if (checked) {
    selectedCallIds.value = Array.from(new Set([...selectedCallIds.value, ...items.value.map((x) => x.id)]))
  } else {
    const visible = new Set(items.value.map((x) => x.id))
    selectedCallIds.value = selectedCallIds.value.filter((id) => !visible.has(id))
  }
}

function onSelectAllChange(event: Event) {
  const target = event.target as HTMLInputElement | null
  toggleSelectAllVisible(Boolean(target?.checked))
}

async function retrySelectedCalls() {
  if (!selectedCallIds.value.length) return
  retryingBulk.value = true
  let ok = 0
  let failed = 0
  for (const callId of selectedCallIds.value) {
    try {
      await apiFetch(`/calls/${callId}/retry`, { method: 'POST' })
      ok += 1
    } catch {
      failed += 1
    }
  }
  if (ok > 0) {
    toast.add({ severity: 'success', summary: 'Повтор запущен', detail: `Запущено: ${ok}`, life: 2500 })
  }
  if (failed > 0) {
    toast.add({ severity: 'warn', summary: 'Частично', detail: `Ошибок: ${failed}`, life: 3000 })
  }
  retryingBulk.value = false
  await loadCalls()
}

function applyFilters() {
  page.value = 1
  void loadCalls()
}

function resetFilters() {
  search.value = ''
  status.value = ''
  page.value = 1
  void loadCalls()
}

watch([page, size], () => {
  void loadCalls()
})

onMounted(() => {
  void loadCalls()
})

const total = computed(() => data.value?.total || 0)
const items = computed(() => data.value?.items || [])
const fromRow = computed(() => (total.value === 0 ? 0 : (page.value - 1) * size.value + 1))
const toRow = computed(() => Math.min(page.value * size.value, total.value))
const activeTasks = computed(() => tasks.value.filter((task) => task.status === 'UPLOADING' || task.status === 'UPLOADING_FILE').length)
</script>

<template>
  <section class="space-y-5">
    <header class="flex flex-col gap-2">
      <div class="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 class="text-2xl font-semibold text-slate-800">Звонки и загрузка</h1>
          <p class="text-sm text-slate-500">Загружайте новые файлы и сразу контролируйте статусы транскрибации.</p>
        </div>
        <div class="flex items-center gap-2">
          <PButton label="Загрузить файлы" icon="pi pi-upload" @click="openFileDialog" />
          <PButton label="К панели" icon="pi pi-arrow-down" severity="secondary" outlined @click="scrollToUpload" />
        </div>
      </div>
    </header>

    <div
      ref="uploadPanelRef"
      class="rounded-xl border border-slate-200 bg-white p-4 md:p-5 space-y-4"
      @drop="onDrop"
      @dragover="onDragOver"
    >
      <div class="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <div>
          <h2 class="text-lg font-semibold text-slate-800">Загрузка звонков</h2>
          <p class="text-sm text-slate-500">Выберите файлы или перетащите их в этот блок. Загрузка стартует автоматически.</p>
        </div>
        <div class="text-xs text-slate-500">Активных загрузок: {{ activeTasks }}</div>
      </div>

      <div class="rounded-lg border-2 border-dashed border-slate-300 bg-slate-50/50 p-5 text-center">
        <div class="text-slate-700 font-medium">Перетащите аудиофайлы сюда</div>
        <p class="text-slate-500 text-sm mt-1">Поддерживаемые форматы: WAV, MP3, OGG, OPUS</p>
        <div class="mt-4">
          <PButton label="Выбрать файлы" icon="pi pi-folder-open" outlined @click="openFileDialog" />
          <input
            ref="uploadInputRef"
            class="hidden"
            type="file"
            multiple
            accept=".wav,.mp3,.ogg,.opus,audio/*"
            @change="onFileSelect"
          />
        </div>
      </div>

      <div v-if="tasks.length > 0" class="space-y-3">
        <div
          v-for="task in tasks"
          :key="task.id"
          class="rounded-lg border border-slate-200 bg-white p-3"
        >
          <div class="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
            <div class="min-w-0 flex-1">
              <div class="font-medium text-slate-800 truncate">{{ task.file.name }}</div>
              <div class="mt-1 text-xs text-slate-500">{{ Math.round(task.file.size / 1024) }} KB</div>
              <div class="mt-2">
                <PProgressBar :value="task.progress" style="height: 12px" />
              </div>
              <div class="mt-2 text-xs" :class="task.error ? 'text-red-600' : 'text-slate-600'">
                <template v-if="task.error">{{ task.error }}</template>
                <template v-else>Статус: {{ task.status }}</template>
              </div>
            </div>

            <div class="flex items-center gap-2">
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
              <PButton
                v-if="task.status === 'COMPLETED' || task.status === 'FAILED' || task.status === 'ABORTED'"
                icon="pi pi-trash"
                text
                severity="secondary"
                size="small"
                @click="removeTask(task.id)"
              />
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="rounded-xl border border-slate-200 bg-white p-4 md:p-5 space-y-4">
      <div class="calls-filters grid grid-cols-1 lg:grid-cols-[1fr,220px,auto] gap-3">
        <div>
          <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-500">Поиск</label>
          <PInputText
            v-model="search"
            placeholder="Название звонка или имя файла"
            class="w-full filter-control"
            @keyup.enter="applyFilters"
          />
        </div>

        <div>
          <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-500">Статус</label>
          <PDropdown
            v-model="status"
            :options="statusOptions"
            optionLabel="label"
            optionValue="value"
            class="w-full filter-control"
          />
        </div>

        <div class="flex items-end gap-2">
          <PButton label="Применить" icon="pi pi-filter" @click="applyFilters" />
          <PButton label="Сброс" severity="secondary" text @click="resetFilters" />
        </div>
      </div>
    </div>

    <div class="rounded-xl border border-slate-200 bg-white overflow-hidden">
      <div class="border-b border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600 flex items-center justify-between">
        <div>
          <span class="font-medium text-slate-700">{{ total }}</span>
          <span class="ml-1">записей</span>
        </div>
        <div class="flex items-center gap-3">
          <PButton
            label="Повторить выбранные"
            icon="pi pi-refresh"
            size="small"
            severity="secondary"
            outlined
            :disabled="selectedCount === 0 || retryingBulk"
            :loading="retryingBulk"
            @click="retrySelectedCalls"
          />
          <div v-if="selectedCount > 0" class="text-xs text-slate-600">Выбрано: {{ selectedCount }}</div>
          <div v-if="total > 0" class="text-xs text-slate-500">{{ fromRow }}-{{ toRow }}</div>
        </div>
      </div>

      <div v-if="loading" class="p-4 space-y-3">
        <PSkeleton height="42px" />
        <PSkeleton height="42px" />
        <PSkeleton height="42px" />
      </div>

      <div v-else-if="items.length === 0" class="p-10 text-center">
        <div class="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-slate-100 text-slate-400">
          <i class="pi pi-inbox text-lg" />
        </div>
        <h2 class="text-base font-medium text-slate-700">Нет звонков</h2>
        <p class="mt-1 text-sm text-slate-500">Попробуй изменить фильтры или загрузить новый файл.</p>
      </div>

      <div v-else class="overflow-x-auto">
        <table class="min-w-full border-collapse">
          <thead>
            <tr class="border-b border-slate-200 bg-white text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
              <th class="px-4 py-3 w-12">
                <input
                  type="checkbox"
                  :checked="allVisibleSelected"
                  @change="onSelectAllChange"
                >
              </th>
              <th class="px-4 py-3">Звонок</th>
              <th class="px-4 py-3">Файл</th>
              <th v-if="auth.isAdmin" class="px-4 py-3">Владелец</th>
              <th class="px-4 py-3">Загружен</th>
              <th class="px-4 py-3">Язык</th>
              <th class="px-4 py-3">Статус</th>
              <th class="px-4 py-3">Прогресс</th>
              <th class="px-4 py-3 text-right">Действия</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="call in items"
              :key="call.id"
              class="border-b border-slate-100 last:border-b-0 hover:bg-slate-50/70 transition"
            >
              <td class="px-4 py-3 align-top">
                <input
                  :value="call.id"
                  v-model="selectedCallIds"
                  type="checkbox"
                >
              </td>
              <td class="px-4 py-3 align-top">
                <div class="font-medium text-slate-800">{{ call.title }}</div>
                <div v-if="call.label_results?.length" class="mt-1 flex flex-wrap gap-1.5">
                  <span
                    v-for="result in call.label_results"
                    :key="result.id"
                    class="inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium"
                    :class="labelBadgeClass(result)"
                    :title="result.comment_text || ''"
                  >
                    {{ labelBadgeText(result) }}
                  </span>
                </div>
                <div v-if="call.error_message" class="mt-1 text-xs text-red-600">{{ call.error_message }}</div>
              </td>
              <td class="px-4 py-3 text-sm text-slate-600 align-top max-w-[240px] truncate">{{ call.source_file_name }}</td>
              <td v-if="auth.isAdmin" class="px-4 py-3 text-sm text-slate-600 align-top">{{ call.owner_login }}</td>
              <td class="px-4 py-3 text-sm text-slate-600 align-top">{{ asDate(call.uploaded_at) }}</td>
              <td class="px-4 py-3 text-sm text-slate-600 align-top">{{ call.language }}</td>
              <td class="px-4 py-3 align-top">
                <PTag :value="mapStatusLabel(call.status)" :severity="statusSeverity(call)" rounded />
              </td>
              <td class="px-4 py-3 align-top">
                <div class="w-48 max-w-full space-y-1">
                  <div class="h-2.5 w-full rounded-full bg-slate-200 overflow-hidden">
                    <div
                      class="h-full transition-all duration-300"
                      :class="progressClass(call)"
                      :style="{ width: `${Math.min(100, Math.max(0, call.progress))}%` }"
                    />
                  </div>
                  <div class="text-xs text-slate-500">{{ call.progress }}%</div>
                </div>
              </td>
              <td class="px-4 py-3 align-top text-right">
                <NuxtLink :to="`/calls/${call.id}`" class="text-sm font-medium text-brand-700 hover:underline">
                  Открыть
                </NuxtLink>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="border-t border-slate-200 bg-white px-4 py-3 flex items-center justify-between">
        <div class="text-xs text-slate-500">Страница {{ page }}</div>
        <div class="flex items-center gap-2">
          <PButton
            label="Назад"
            size="small"
            outlined
            :disabled="page <= 1"
            @click="page = Math.max(1, page - 1)"
          />
          <PButton
            label="Вперёд"
            size="small"
            outlined
            :disabled="items.length < size"
            @click="page = page + 1"
          />
        </div>
      </div>
    </div>
  </section>
</template>
