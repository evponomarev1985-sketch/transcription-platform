<script setup lang="ts">
import { useToast } from 'primevue/usetoast'
import { useConfirm } from 'primevue/useconfirm'
import type { CallChecklistResult, CallComment, CallItem, LabelResult, TranscriptResponse } from '~/types/calls'

const route = useRoute()
const router = useRouter()
const toast = useToast()
const confirm = useConfirm()
const { apiFetch } = useApi()
const auth = useAuthStore()
const config = useRuntimeConfig()

const id = computed(() => {
  const raw = route.params.id
  return Array.isArray(raw) ? String(raw[0] || '') : String(raw || '')
})

const call = ref<CallItem | null>(null)
const transcript = ref<TranscriptResponse | null>(null)
const comments = ref<CallComment[]>([])
const audioUrl = ref('')
const audioLoading = ref(false)
const loading = ref(true)
const query = ref('')
const diagnosticsDialogVisible = ref(false)
let audioObjectUrl: string | null = null

async function loadAudio() {
  if (!id.value || !auth.accessToken) {
    audioUrl.value = ''
    return
  }

  audioLoading.value = true
  try {
    const response = await fetch(`${config.public.apiBase}/calls/${id.value}/audio`, {
      headers: {
        Authorization: `Bearer ${auth.accessToken}`,
      },
    })

    if (!response.ok) {
      throw new Error('Не удалось загрузить аудио')
    }

    const blob = await response.blob()
    if (audioObjectUrl) {
      URL.revokeObjectURL(audioObjectUrl)
    }
    audioObjectUrl = URL.createObjectURL(blob)
    audioUrl.value = audioObjectUrl
  } catch {
    audioUrl.value = ''
    toast.add({ severity: 'warn', summary: 'Внимание', detail: 'Аудио недоступно для воспроизведения', life: 2500 })
  } finally {
    audioLoading.value = false
  }
}

async function load() {
  if (!id.value) {
    loading.value = false
    toast.add({ severity: 'error', summary: 'Ошибка', detail: 'Некорректный идентификатор звонка', life: 3000 })
    return
  }

  loading.value = true
  try {
    const [callData, transcriptResult, commentsResult] = await Promise.allSettled([
      apiFetch<CallItem>(`/calls/${id.value}`),
      apiFetch<TranscriptResponse>(`/calls/${id.value}/transcript`),
      apiFetch<CallComment[]>(`/calls/${id.value}/comments`),
    ])

    if (callData.status === 'fulfilled') {
      call.value = callData.value
    } else {
      call.value = null
      toast.add({ severity: 'error', summary: 'Ошибка', detail: 'Не удалось загрузить карточку звонка', life: 3000 })
    }

    if (transcriptResult.status === 'fulfilled') {
      transcript.value = transcriptResult.value
    } else {
      transcript.value = {
        call_id: id.value,
        full_text: '',
        language: call.value?.language || 'ru-RU',
        stt_version: 'unknown',
        speaker_labeling: 'unknown',
        segments: [],
      }
    }

    if (commentsResult.status === 'fulfilled') {
      comments.value = commentsResult.value
    } else {
      comments.value = []
    }

    await loadAudio()

  } catch (error) {
    call.value = null
    transcript.value = null
    comments.value = []
    audioUrl.value = ''
    toast.add({ severity: 'error', summary: 'Ошибка', detail: (error as Error).message, life: 3000 })
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(() => route.params.id, () => { void load() })

const filteredSegments = computed(() => {
  const items = transcript.value?.segments || []
  if (!query.value.trim()) return items
  const q = query.value.toLowerCase()
  return items.filter((s) => s.text.toLowerCase().includes(q))
})

function speakerToken(raw: string | null): string {
  return raw ? raw.trim().toUpperCase() : ''
}

const speakerIndexScheme = computed<'ZERO_ONE' | 'ONE_TWO' | 'UNKNOWN'>(() => {
  const values = new Set((transcript.value?.segments || []).map((segment) => speakerToken(segment.speaker_label)).filter(Boolean))
  const has0 = values.has('0') || values.has('CH0') || values.has('CHANNEL_0')
  const has1 = values.has('1') || values.has('CH1') || values.has('CHANNEL_1')
  const has2 = values.has('2') || values.has('CH2') || values.has('CHANNEL_2')

  if (has0 && has1 && !has2) return 'ZERO_ONE'
  if (has1 && has2) return 'ONE_TWO'
  return 'UNKNOWN'
})

function normalizeSpeakerLabel(raw: string | null): 'SPEAKER_1' | 'SPEAKER_2' | 'UNKNOWN' {
  const value = speakerToken(raw)
  if (!value) return 'UNKNOWN'

  if (value.includes('OPERATOR') || value.includes('AGENT') || value === 'SPEAKER_1') {
    return 'SPEAKER_1'
  }
  if (value.includes('CLIENT') || value.includes('CUSTOMER') || value === 'SPEAKER_2') {
    return 'SPEAKER_2'
  }

  if (speakerIndexScheme.value === 'ZERO_ONE') {
    if (value === '0' || value === 'CH0' || value === 'CHANNEL_0') return 'SPEAKER_1'
    if (value === '1' || value === 'CH1' || value === 'CHANNEL_1') return 'SPEAKER_2'
  }

  if (speakerIndexScheme.value === 'ONE_TWO') {
    if (value === '1' || value === 'CH1' || value === 'CHANNEL_1') return 'SPEAKER_1'
    if (value === '2' || value === 'CH2' || value === 'CHANNEL_2') return 'SPEAKER_2'
  }

  return 'UNKNOWN'
}

const roleSplitAvailable = computed(() => {
  const labels = new Set(
    (transcript.value?.segments || [])
      .map((segment) => normalizeSpeakerLabel(segment.speaker_label))
      .filter((label) => label !== 'UNKNOWN'),
  )
  return labels.has('SPEAKER_1') && labels.has('SPEAKER_2')
})

const roleSplitUnavailableReason = computed(() => {
  const items = transcript.value?.segments || []
  if (!items.length || roleSplitAvailable.value) return ''

  const labels = new Set(items.map((segment) => normalizeSpeakerLabel(segment.speaker_label)).filter((label) => label !== 'UNKNOWN'))
  if (labels.size === 0) {
    return 'SpeechKit не вернул метки спикеров.'
  }
  return 'SpeechKit вернул только одного спикера/канал.'
})

const transcriptEngineLabel = computed(() => {
  const version = transcript.value?.stt_version || 'unknown'
  if (version === 'v3') return 'STT v3'
  if (version === 'v2') return 'STT v2'
  return 'STT ?'
})

const speakerLabelingLabel = computed(() => {
  const state = transcript.value?.speaker_labeling || 'unknown'
  if (state === 'on') return 'Speaker labeling: ON'
  if (state === 'off') return 'Speaker labeling: OFF'
  return 'Speaker labeling: ?'
})

const conversationItems = computed(() => {
  let lastKnownRole: 'SPEAKER_1' | 'SPEAKER_2' = 'SPEAKER_1'

  return filteredSegments.value.map((segment) => {
    const parsed = normalizeSpeakerLabel(segment.speaker_label)
    let role: 'SPEAKER_1' | 'SPEAKER_2'
    if (roleSplitAvailable.value) {
      role = parsed === 'UNKNOWN' ? lastKnownRole : parsed
    } else {
      role = parsed === 'SPEAKER_2' ? 'SPEAKER_2' : 'SPEAKER_1'
    }
    if (parsed !== 'UNKNOWN') {
      lastKnownRole = parsed
    }

    return {
      ...segment,
      isOperator: role === 'SPEAKER_1',
      uiLabel: roleSplitAvailable.value
        ? (role === 'SPEAKER_1' ? 'Оператор' : 'Клиент')
        : (role === 'SPEAKER_1' ? 'Канал 1' : 'Канал 2'),
    }
  })
})

const unmatchedResults = computed(() => call.value?.label_results_unmatched || [])
const needsReviewResults = computed(() => call.value?.label_results_needs_review || [])
const unmatchedDiagnosticsResults = computed(() => unmatchedResults.value)

const displayLabelResults = computed(() => call.value?.label_results || [])

const allComments = computed<CallComment[]>(() => {
  const fromApi = comments.value || []
  const extra: CallComment[] = []

  for (const result of unmatchedResults.value) {
    const body = (result.comment_text || '').trim()
    if (!body) continue

    let valueDisplay: string | null = null
    if (result.label_kind === 'FLAG_VALUE') {
      if (result.value_number !== null) {
        const n = result.value_number
        valueDisplay = n === Math.floor(n) ? String(Math.floor(n)) : String(n)
      } else if (result.value_text) {
        valueDisplay = result.value_text
      }
    }

    extra.push({
      result_id: result.id,
      rule_id: result.rule_id,
      label_id: result.label_id,
      title: unmatchedResultLabel(result),
      body,
      label_kind: result.label_kind,
      value_display: valueDisplay,
      evaluated_at: result.evaluated_at,
    })
  }

  const merged = [...fromApi, ...extra]
  merged.sort((a, b) => new Date(b.evaluated_at).getTime() - new Date(a.evaluated_at).getTime())
  return merged
})

function unmatchedResultLabel(result: LabelResult) {
  if (result.label_kind === 'FLAG_VALUE') {
    return result.label_name || result.rule_name || 'FLAG_VALUE'
  }
  if (result.label_kind === 'FLAG') {
    return result.label_name || result.rule_name || 'FLAG'
  }
  return result.comment_title_snapshot || result.rule_name || result.label_name || 'COMMENT'
}

async function retry() {
  try {
    await apiFetch(`/calls/${id.value}/retry`, { method: 'POST' })
    toast.add({ severity: 'success', summary: 'Запущено', detail: 'Задача отправлена на повторную обработку', life: 2500 })
    await load()
  } catch (error) {
    toast.add({ severity: 'error', summary: 'Ошибка', detail: (error as Error).message, life: 3000 })
  }
}

function removeCall() {
  confirm.require({
    message: 'Удалить звонок?',
    header: 'Подтверждение',
    icon: 'pi pi-exclamation-triangle',
    acceptLabel: 'Удалить',
    rejectLabel: 'Отмена',
    acceptClass: 'p-button-danger',
    accept: async () => {
      try {
        await apiFetch(`/calls/${id.value}`, { method: 'DELETE' })
        toast.add({ severity: 'success', summary: 'Удалено', detail: 'Звонок удален', life: 2500 })
        router.push('/calls')
      } catch (error) {
        toast.add({ severity: 'error', summary: 'Ошибка', detail: (error as Error).message, life: 3000 })
      }
    },
  })
}

function toTimestamp(ms: number): string {
  const totalSec = Math.floor(ms / 1000)
  const m = Math.floor(totalSec / 60)
  const s = totalSec % 60
  return `${m}:${String(s).padStart(2, '0')}`
}

function jumpTo(ms: number) {
  const player = document.getElementById('call-audio') as HTMLAudioElement | null
  if (!player) return
  player.currentTime = ms / 1000
  void player.play()
}

onBeforeUnmount(() => {
  if (audioObjectUrl) {
    URL.revokeObjectURL(audioObjectUrl)
    audioObjectUrl = null
  }
})

function labelResultBadge(result: LabelResult) {
  if (result.label_kind === 'FLAG') {
    return { class: 'border-teal-200 bg-teal-50 text-teal-700', label: result.label_name }
  }
  if (result.label_kind === 'FLAG_VALUE') {
    const val = result.value_number !== null
      ? (result.value_number === Math.floor(result.value_number) ? String(Math.floor(result.value_number)) : String(result.value_number))
      : (result.value_text || '—')
    return { class: 'border-amber-200 bg-amber-50 text-amber-700', label: `${result.label_name}: ${val}` }
  }
  return {
    class: 'border-violet-200 bg-violet-50 text-violet-700',
    label: result.comment_title_snapshot || result.label_name || 'Комментарий',
  }
}

function commentCardClass(kind: string | null) {
  if (kind === 'FLAG') return 'border-teal-200 bg-teal-50'
  if (kind === 'FLAG_VALUE') return 'border-amber-200 bg-amber-50'
  return 'border-violet-200 bg-violet-50'
}

const checklistResults = computed<CallChecklistResult[]>(() => call.value?.checklist_results || [])
</script>

<template>
  <section class="space-y-4">
    <div v-if="loading" class="space-y-3">
      <PSkeleton height="2rem" />
      <PSkeleton height="12rem" />
    </div>

    <template v-else-if="!call">
      <div class="bg-white border border-slate-200 rounded-xl p-8 text-center text-slate-500">
        Не удалось загрузить карточку звонка
      </div>
    </template>

    <template v-else-if="call">
      <!-- Header row -->
      <div class="flex flex-col md:flex-row md:items-start md:justify-between gap-3">
        <div>
          <h1 class="text-2xl font-semibold text-slate-800">{{ call.title }}</h1>
          <p class="text-sm text-slate-500">{{ call.source_file_name }}</p>
          <div v-if="displayLabelResults.length" class="mt-2 flex flex-wrap gap-1.5">
            <span
              v-for="result in displayLabelResults"
              :key="result.id"
              :class="['inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium', labelResultBadge(result).class]"
            >
              {{ labelResultBadge(result).label }}
            </span>
          </div>
        </div>
        <div class="flex flex-wrap gap-2">
          <StatusBadge :status="call.status" />
          <span class="inline-flex items-center rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-medium text-slate-700">
            {{ transcriptEngineLabel }}
          </span>
          <span class="inline-flex items-center rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-medium text-slate-700">
            {{ speakerLabelingLabel }}
          </span>
          <PButton label="Retry" icon="pi pi-refresh" severity="secondary" outlined @click="retry" />
          <PButton
            icon="pi pi-info-circle"
            severity="secondary"
            outlined
            :badge="String((needsReviewResults.length || 0) + (unmatchedDiagnosticsResults.length || 0))"
            badgeSeverity="danger"
            aria-label="Диагностика правил"
            @click="diagnosticsDialogVisible = true"
          />
          <PButton label="Delete" icon="pi pi-trash" severity="danger" outlined @click="removeCall" />
        </div>
      </div>

      <!-- Two-column layout: left = call info + dialog, right = comments -->
      <div class="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <!-- Left column (2/3 width) -->
        <div class="lg:col-span-2 space-y-4">
          <!-- Audio + info block -->
          <div class="bg-white border border-slate-200 rounded-xl p-4 space-y-4">
            <div v-if="audioLoading" class="text-sm text-slate-500">Загрузка аудио...</div>
            <audio
              v-else-if="audioUrl"
              id="call-audio"
              controls
              preload="metadata"
              :src="audioUrl"
              class="w-full"
            />
            <div v-else class="text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
              Аудио временно недоступно.
            </div>

            <div class="grid md:grid-cols-4 gap-3 text-sm">
              <div class="bg-slate-50 rounded-lg p-3">
                <div class="text-slate-500">Язык</div>
                <div class="text-slate-800 font-medium">{{ call.language }}</div>
              </div>
              <div class="bg-slate-50 rounded-lg p-3">
                <div class="text-slate-500">Прогресс</div>
                <div class="text-slate-800 font-medium">{{ call.progress }}%</div>
              </div>
              <div class="bg-slate-50 rounded-lg p-3">
                <div class="text-slate-500">Длительность</div>
                <div class="text-slate-800 font-medium">{{ call.duration_seconds ?? '-' }}</div>
              </div>
              <div class="bg-slate-50 rounded-lg p-3">
                <div class="text-slate-500">Статус</div>
                <div class="text-slate-800 font-medium">{{ call.status }}</div>
              </div>
            </div>

            <div v-if="call.error_message" class="bg-red-50 border border-red-200 rounded-lg p-3 text-sm text-red-700">
              {{ call.error_message }}
            </div>
          </div>

          <!-- Checklist block -->
          <div class="bg-white border border-slate-200 rounded-xl p-4 space-y-3">
            <h2 class="text-lg font-semibold text-slate-800">Чек-листы</h2>

            <div v-if="!checklistResults.length" class="text-sm text-slate-500">
              Нет активных чек-листов
            </div>

            <div v-else class="space-y-3">
              <div v-for="item in checklistResults" :key="item.checklist_id" class="rounded-lg border border-slate-200 p-3">
                <div class="flex flex-wrap items-center justify-between gap-2 mb-2">
                  <div>
                    <div class="font-medium text-slate-800">{{ item.checklist_name }}</div>
                    <div class="text-xs text-slate-500">
                      {{ item.is_applicable ? 'Применен' : 'Не применен (по фильтрам)' }}
                    </div>
                  </div>
                  <div class="text-right">
                    <div class="text-sm font-semibold text-slate-800">{{ item.total_score }} / {{ item.max_score }}</div>
                    <div class="text-xs text-slate-500">{{ item.completion_percent }}%</div>
                  </div>
                </div>

                <PProgressBar :value="item.completion_percent" :showValue="false" class="h-2 mb-3" />

                <div class="space-y-2">
                  <div
                    v-for="question in item.questions"
                    :key="question.question_id"
                    class="rounded-md border border-slate-100 bg-slate-50 px-3 py-2"
                  >
                    <div class="text-sm text-slate-800">{{ question.question_text }}</div>
                    <div class="text-xs text-slate-600 mt-1">
                      Ответ: {{ question.answer_text || '—' }}
                    </div>
                    <div class="text-xs text-slate-500 mt-1">
                      Балл: {{ question.score }} / {{ question.max_score }}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- Dialog block -->
          <div class="bg-white border border-slate-200 rounded-xl p-4 space-y-3">
            <div class="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
              <h2 class="text-lg font-semibold text-slate-800">Диалог</h2>
              <PInputText v-model="query" placeholder="Поиск по тексту" class="md:w-72" />
            </div>

            <div
              v-if="!roleSplitAvailable && (transcript?.segments?.length || 0) > 0"
              class="bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 text-sm text-amber-800"
            >
              Авторазделение на роли оператор/клиент недоступно. {{ roleSplitUnavailableReason }}
              Для надежного разделения нужна двухканальная запись звонка.
            </div>

            <div class="space-y-2 max-h-[450px] overflow-auto pr-1">
              <div v-if="conversationItems.length === 0" class="text-sm text-slate-500 py-6 text-center">
                Нет сегментов
              </div>
              <div
                v-for="segment in conversationItems"
                :key="segment.id"
                class="flex"
                :class="roleSplitAvailable ? (segment.isOperator ? 'justify-start' : 'justify-end') : 'justify-start'"
              >
                <div
                  class="max-w-[88%] rounded-2xl border px-4 py-3"
                  :class="roleSplitAvailable
                    ? (segment.isOperator ? 'bg-slate-50 border-slate-200 text-slate-800' : 'bg-brand-50 border-brand-200 text-slate-900')
                    : 'bg-slate-50 border-slate-200 text-slate-800'"
                >
                  <div class="flex items-center justify-between gap-3 mb-1">
                    <span
                      class="text-xs font-semibold uppercase tracking-wide"
                      :class="roleSplitAvailable ? (segment.isOperator ? 'text-slate-500' : 'text-brand-700') : 'text-slate-500'"
                    >
                      {{ segment.uiLabel }}
                    </span>
                    <button class="text-xs text-brand-700 hover:underline" @click="jumpTo(segment.start_ms)">
                      {{ toTimestamp(segment.start_ms) }} - {{ toTimestamp(segment.end_ms) }}
                    </button>
                  </div>
                  <p class="text-sm leading-relaxed">{{ segment.text }}</p>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Right column (1/3 width) — Comments -->
        <div class="space-y-3">
          <div class="bg-white border border-slate-200 rounded-xl p-4">
            <h2 class="text-lg font-semibold text-slate-800 mb-3">Комментарии</h2>

            <div v-if="allComments.length === 0" class="text-sm text-slate-500 text-center py-6">
              Нет комментариев
            </div>

            <div v-else class="space-y-3">
              <div
                v-for="comment in allComments"
                :key="comment.result_id"
                :class="['rounded-xl border p-4', commentCardClass(comment.label_kind)]"
              >
                <div class="flex items-start justify-between gap-2 mb-2">
                  <span class="text-sm font-semibold text-slate-800">{{ comment.title }}</span>
                  <span
                    v-if="comment.label_kind === 'FLAG'"
                    class="inline-flex items-center rounded-full border border-teal-300 bg-teal-100 px-2 py-0.5 text-[10px] font-medium text-teal-800"
                  >
                    FLAG
                  </span>
                  <span
                    v-else-if="comment.label_kind === 'FLAG_VALUE'"
                    class="inline-flex items-center rounded-full border border-amber-300 bg-amber-100 px-2 py-0.5 text-[10px] font-medium text-amber-800"
                  >
                    FLAG_VALUE
                  </span>
                  <span
                    v-else-if="comment.label_kind === 'COMMENT'"
                    class="inline-flex items-center rounded-full border border-violet-300 bg-violet-100 px-2 py-0.5 text-[10px] font-medium text-violet-800"
                  >
                    COMMENT
                  </span>
                </div>

                <div v-if="comment.value_display" class="mb-2">
                  <span class="text-2xl font-bold text-slate-800">{{ comment.value_display }}</span>
                </div>

                <p class="text-sm text-slate-700 leading-relaxed whitespace-pre-wrap">{{ comment.body }}</p>

                <div class="mt-2 text-xs text-slate-400">
                  {{ new Date(comment.evaluated_at).toLocaleString('ru-RU') }}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <PDialog v-model:visible="diagnosticsDialogVisible" modal header="Диагностика правил" :style="{ width: '44rem' }">
        <div class="space-y-5">
          <div>
            <h3 class="text-sm font-semibold text-amber-900 mb-2">Требует ручной проверки</h3>
            <div v-if="needsReviewResults.length" class="space-y-2">
              <div v-for="result in needsReviewResults" :key="`review-${result.id}`" class="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2">
                <div class="text-sm font-medium text-slate-800">{{ result.rule_name || unmatchedResultLabel(result) }}</div>
                <div class="text-xs text-amber-800 mt-1">{{ (result.review_reasons || []).join(' • ') || 'Низкая уверенность модели' }}</div>
                <div class="text-xs text-slate-700 mt-1">Результат модели: {{ result.value_text || '—' }}</div>
                <div v-if="result.comment_text" class="text-xs text-slate-600 mt-1">Комментарий: {{ result.comment_text }}</div>
              </div>
            </div>
            <div v-else class="text-sm text-slate-500">Нет результатов, требующих ручной проверки.</div>
          </div>

          <div>
            <h3 class="text-sm font-semibold text-slate-800 mb-2">Не сработало</h3>
            <div v-if="unmatchedDiagnosticsResults.length" class="space-y-2">
              <div v-for="result in unmatchedDiagnosticsResults" :key="`unmatched-${result.id}`" class="rounded-lg border border-slate-200 bg-white px-3 py-2">
                <div class="text-sm font-medium text-slate-800">{{ result.rule_name || unmatchedResultLabel(result) }}</div>
                <div class="text-xs text-slate-700 mt-1">Результат модели: {{ result.value_text || '—' }}</div>
                <div class="text-xs text-slate-600 mt-1">{{ result.comment_text || 'Модель не нашла подтверждения в разговоре' }}</div>
              </div>
            </div>
            <div v-else class="text-sm text-slate-500">Нет несработавших правил.</div>
          </div>
        </div>
      </PDialog>
    </template>
  </section>
</template>
