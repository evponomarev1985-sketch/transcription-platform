<script setup lang="ts">
import { useToast } from 'primevue/usetoast'
import type { CallListResponse, TranscriptResponse, LabelDefinition, LabelRule, RuleKind, ValidatePromptResponse } from '~/types/calls'

const toast = useToast()
const { apiFetch } = useApi()

const rules = ref<LabelRule[]>([])
const labels = ref<LabelDefinition[]>([])
const loading = ref(true)
const labelsLoading = ref(true)

const createDialog = ref(false)
const editDialog = ref(false)
const createLabelDialog = ref(false)

const form = ref({
  name: '',
  kind: 'FLAG' as RuleKind,
  rule_type: 'KEYWORD' as 'KEYWORD' | 'LLM',
  is_enabled: true,
  label_ids: [] as string[],
  keyword_query: '',
  keyword_search_part: 'ANY' as 'ANY' | 'OPENING' | 'MIDDLE' | 'CLOSING',
  llm_prompt: '',
})

const editForm = ref({
  id: '',
  name: '',
  kind: 'FLAG' as RuleKind,
  rule_type: 'KEYWORD' as 'KEYWORD' | 'LLM',
  is_enabled: true,
  label_ids: [] as string[],
  keyword_query: '',
  keyword_search_part: 'ANY' as 'ANY' | 'OPENING' | 'MIDDLE' | 'CLOSING',
  llm_prompt: '',
})

const validationCalls = ref<{ id: string, title: string, source_file_name: string }[]>([])
const validationCallsLoading = ref(false)

const createValidation = ref({
  call_id: '',
  validating: false,
  result: null as ValidatePromptResponse | null,
})

const editValidation = ref({
  call_id: '',
  validating: false,
  result: null as ValidatePromptResponse | null,
})

const newLabelForm = ref({
  name: '',
  kind: 'FLAG' as LabelDefinition['kind'],
})

const ruleTypeOptions = [
  { label: 'Поиск по словам', value: 'KEYWORD' },
  { label: 'LLM промпт', value: 'LLM' },
]

const searchPartOptions = [
  { label: 'Весь диалог', value: 'ANY' },
  { label: 'Начало', value: 'OPENING' },
  { label: 'Середина', value: 'MIDDLE' },
  { label: 'Конец', value: 'CLOSING' },
]

const kindOptions = [
  { label: 'FLAG — флаг (да/нет)', value: 'FLAG' },
  { label: 'FLAG_VALUE — значение', value: 'FLAG_VALUE' },
  { label: 'COMMENT — комментарий', value: 'COMMENT' },
]

const validationCallOptions = computed(() =>
  validationCalls.value.map((call) => ({
    label: `${call.title} (${call.source_file_name})`,
    value: call.id,
  }))
)

const canValidateCreatePrompt = computed(
  () => !!form.value.llm_prompt
    && !!createValidation.value.call_id
    && (form.value.kind === 'COMMENT' || form.value.label_ids.length > 0)
)

const canValidateEditPrompt = computed(
  () => !!editForm.value.llm_prompt
    && !!editValidation.value.call_id
    && (editForm.value.kind === 'COMMENT' || editForm.value.label_ids.length > 0)
)

const canCreateRule = computed(() => {
  if (!form.value.name.trim()) return false
  if (form.value.kind !== 'COMMENT' && !form.value.label_ids.length) return false
  if (form.value.rule_type === 'KEYWORD') {
    return !!form.value.keyword_query.trim()
  }
  return !!form.value.llm_prompt.trim()
})

const canUpdateRule = computed(() => {
  if (!editForm.value.name.trim()) return false
  if (editForm.value.kind !== 'COMMENT' && !editForm.value.label_ids.length) return false
  if (editForm.value.rule_type === 'KEYWORD') {
    return !!editForm.value.keyword_query.trim()
  }
  return !!editForm.value.llm_prompt.trim()
})

function transliterateRu(value: string): string {
  const map: Record<string, string> = {
    а: 'a', б: 'b', в: 'v', г: 'g', д: 'd', е: 'e', ё: 'e', ж: 'zh', з: 'z', и: 'i', й: 'y',
    к: 'k', л: 'l', м: 'm', н: 'n', о: 'o', п: 'p', р: 'r', с: 's', т: 't', у: 'u', ф: 'f',
    х: 'h', ц: 'ts', ч: 'ch', ш: 'sh', щ: 'sch', ъ: '', ы: 'y', ь: '', э: 'e', ю: 'yu', я: 'ya',
  }

  return value
    .split('')
    .map((char) => map[char] ?? char)
    .join('')
}

function generateLabelCode(name: string): string {
  const base = transliterateRu(name.trim().toLowerCase())
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .replace(/_+/g, '_')

  if (base) return base.slice(0, 128)
  return `label_${Date.now()}`
}

function openCreateLabelDialog(kind: LabelDefinition['kind'] = 'FLAG') {
  newLabelForm.value.kind = kind
  createLabelDialog.value = true
}

const createSingleLabelId = computed({
  get: () => form.value.label_ids[0] || '',
  set: (value: string) => {
    form.value.label_ids = value ? [value] : []
  },
})

const editSingleLabelId = computed({
  get: () => editForm.value.label_ids[0] || '',
  set: (value: string) => {
    editForm.value.label_ids = value ? [value] : []
  },
})

async function loadLabels() {
  labelsLoading.value = true
  try {
    const data = await apiFetch<{ items: LabelDefinition[] }>('/calls/labels')
    labels.value = data.items.filter((l) => l.is_active)
  } catch (error) {
    toast.add({ severity: 'error', summary: 'Ошибка', detail: 'Не удалось загрузить метки', life: 3000 })
  } finally {
    labelsLoading.value = false
  }
}

async function loadRules() {
  loading.value = true
  try {
    const data = await apiFetch<{ items: LabelRule[] }>('/calls/label-rules')
    rules.value = data.items
  } catch (error) {
    toast.add({ severity: 'error', summary: 'Ошибка', detail: (error as Error).message, life: 3000 })
  } finally {
    loading.value = false
  }
}

async function loadValidationCalls() {
  validationCallsLoading.value = true
  try {
    const data = await apiFetch<CallListResponse>('/calls?page=1&size=100&sort_by=uploaded_at&sort_order=desc')
    validationCalls.value = data.items.map((call) => ({
      id: call.id,
      title: call.title,
      source_file_name: call.source_file_name,
    }))
    if (!createValidation.value.call_id && validationCalls.value.length) {
      createValidation.value.call_id = validationCalls.value[0].id
    }
    if (!editValidation.value.call_id && validationCalls.value.length) {
      editValidation.value.call_id = validationCalls.value[0].id
    }
  } catch {
    toast.add({ severity: 'warn', summary: 'Внимание', detail: 'Не удалось загрузить список звонков для проверки промпта', life: 3000 })
  } finally {
    validationCallsLoading.value = false
  }
}

onMounted(async () => {
  await Promise.all([loadLabels(), loadRules(), loadValidationCalls()])
})

function labelsForEditKind(kind: RuleKind) {
  return labels.value.filter((l) => l.kind === kind && l.is_active)
}

function kindBadge(kind: RuleKind) {
  const map: Record<string, string> = { FLAG: 'info', FLAG_VALUE: 'warning', COMMENT: 'success' }
  return map[kind] || 'secondary'
}

function kindLabel(kind: RuleKind | null) {
  if (!kind) return '—'
  const map: Record<string, string> = { FLAG: 'FLAG', FLAG_VALUE: 'FLAG_VALUE', COMMENT: 'COMMENT' }
  return map[kind] || kind
}

function resetForm() {
  form.value = {
    name: '',
    kind: 'FLAG',
    rule_type: 'KEYWORD',
    is_enabled: true,
    label_ids: [],
    keyword_query: '',
    keyword_search_part: 'ANY',
    llm_prompt: '',
  }
}

watch(
  () => form.value.kind,
  (kind) => {
    if (kind === 'FLAG') return
    if (kind === 'COMMENT') {
      form.value.label_ids = []
      return
    }
    form.value.label_ids = form.value.label_ids.length ? [form.value.label_ids[0]] : []
  }
)

watch(
  () => editForm.value.kind,
  (kind) => {
    if (kind === 'FLAG') return
    if (kind === 'COMMENT') {
      editForm.value.label_ids = []
      return
    }
    editForm.value.label_ids = editForm.value.label_ids.length ? [editForm.value.label_ids[0]] : []
  }
)

async function createRule() {
  try {
    const normalizedLabelIds = form.value.kind === 'FLAG'
      ? form.value.label_ids
      : (form.value.kind === 'COMMENT' ? [] : form.value.label_ids.slice(0, 1))
    const payload: Record<string, unknown> = {
      name: form.value.name,
      kind: form.value.kind,
      rule_type: form.value.rule_type,
      is_enabled: form.value.is_enabled,
      label_ids: normalizedLabelIds,
    }
    if (form.value.rule_type === 'KEYWORD') {
      payload.keyword_query = form.value.keyword_query
      payload.keyword_search_part = form.value.keyword_search_part
    } else {
      payload.llm_prompt = form.value.llm_prompt
    }
    await apiFetch('/calls/label-rules', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
    createDialog.value = false
    resetForm()
    toast.add({ severity: 'success', summary: 'Создано', detail: 'Правило добавлено', life: 2500 })
    await loadRules()
  } catch (error) {
    toast.add({ severity: 'error', summary: 'Ошибка', detail: (error as Error).message, life: 3000 })
  }
}

function openEditDialog(rule: LabelRule) {
  editForm.value = {
    id: rule.id,
    name: rule.name,
    kind: rule.kind,
    rule_type: rule.rule_type,
    is_enabled: rule.is_enabled,
    label_ids: rule.label_ids || [],
    keyword_query: rule.keyword_query || '',
    keyword_search_part: (rule.keyword_search_part || 'ANY') as 'ANY' | 'OPENING' | 'MIDDLE' | 'CLOSING',
    llm_prompt: rule.llm_prompt || '',
  }
  editValidation.value.result = null
  if (!editValidation.value.call_id && validationCalls.value.length) {
    editValidation.value.call_id = validationCalls.value[0].id
  }
  editDialog.value = true
}

function closeEditDialog() {
  editDialog.value = false
}

async function updateRule() {
  try {
    const normalizedLabelIds = editForm.value.kind === 'FLAG'
      ? editForm.value.label_ids
      : (editForm.value.kind === 'COMMENT' ? [] : editForm.value.label_ids.slice(0, 1))
    const payload: Record<string, unknown> = {
      name: editForm.value.name,
      is_enabled: editForm.value.is_enabled,
      label_ids: normalizedLabelIds,
    }
    if (editForm.value.rule_type === 'KEYWORD') {
      payload.keyword_query = editForm.value.keyword_query
      payload.keyword_search_part = editForm.value.keyword_search_part
    } else {
      payload.llm_prompt = editForm.value.llm_prompt
    }
    await apiFetch(`/calls/label-rules/${editForm.value.id}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    })
    closeEditDialog()
    toast.add({ severity: 'success', summary: 'Сохранено', detail: 'Правило обновлено', life: 2500 })
    await loadRules()
  } catch (error) {
    toast.add({ severity: 'error', summary: 'Ошибка', detail: (error as Error).message, life: 3000 })
  }
}

async function toggleEnabled(rule: LabelRule) {
  try {
    await apiFetch(`/calls/label-rules/${rule.id}`, {
      method: 'PATCH',
      body: JSON.stringify({ is_enabled: !rule.is_enabled }),
    })
    await loadRules()
  } catch (error) {
    toast.add({ severity: 'error', summary: 'Ошибка', detail: (error as Error).message, life: 3000 })
  }
}

async function deleteRule(rule: LabelRule) {
  try {
    await apiFetch(`/calls/label-rules/${rule.id}`, { method: 'DELETE' })
    toast.add({ severity: 'success', summary: 'Удалено', detail: 'Правило удалено', life: 2500 })
    await loadRules()
  } catch (error) {
    toast.add({ severity: 'error', summary: 'Ошибка', detail: (error as Error).message, life: 3000 })
  }
}

async function loadCallTranscriptText(callId: string): Promise<string> {
  const transcript = await apiFetch<TranscriptResponse>(`/calls/${callId}/transcript`)
  const fullText = (transcript.full_text || '').trim()
  if (fullText) return fullText
  return transcript.segments.map((segment) => segment.text).join(' ').trim()
}

async function validateRulePrompt(kind: RuleKind, promptText: string, labelIds: string[], callId: string) {
  const labelId = labelIds[0] || null
  if (kind !== 'COMMENT' && !labelId) throw new Error('Выберите метку для проверки промпта')
  if (!callId) throw new Error('Выберите звонок для проверки промпта')

  const testText = await loadCallTranscriptText(callId)
  if (!testText) throw new Error('У выбранного звонка нет текста транскрипта')

  return apiFetch<ValidatePromptResponse>('/calls/label-rules/validate-prompt', {
    method: 'POST',
    body: JSON.stringify({
      prompt_text: promptText,
      test_text: testText,
      kind,
      label_id: labelId,
      label_ids: labelIds,
    }),
  })
}

async function validateCreatePrompt() {
  createValidation.value.validating = true
  createValidation.value.result = null
  try {
    createValidation.value.result = await validateRulePrompt(
      form.value.kind,
      form.value.llm_prompt,
      form.value.label_ids,
      createValidation.value.call_id,
    )
  } catch (error) {
    toast.add({ severity: 'error', summary: 'Ошибка', detail: (error as Error).message, life: 3000 })
  } finally {
    createValidation.value.validating = false
  }
}

async function validateEditPrompt() {
  editValidation.value.validating = true
  editValidation.value.result = null
  try {
    editValidation.value.result = await validateRulePrompt(
      editForm.value.kind,
      editForm.value.llm_prompt,
      editForm.value.label_ids,
      editValidation.value.call_id,
    )
  } catch (error) {
    toast.add({ severity: 'error', summary: 'Ошибка', detail: (error as Error).message, life: 3000 })
  } finally {
    editValidation.value.validating = false
  }
}

async function createLabel() {
  try {
    const name = newLabelForm.value.name.trim()
    const code = generateLabelCode(name)
    await apiFetch('/calls/labels', {
      method: 'POST',
      body: JSON.stringify({
        code,
        name,
        kind: newLabelForm.value.kind,
      }),
    })
    createLabelDialog.value = false
    newLabelForm.value = { name: '', kind: 'FLAG' }
    toast.add({ severity: 'success', summary: 'Метка создана', detail: 'Можно использовать при создании правила', life: 2500 })
    await loadLabels()
  } catch (error) {
    toast.add({ severity: 'error', summary: 'Ошибка', detail: (error as Error).message, life: 3000 })
  }
}

function labelNames(labelIds: string[], kind?: RuleKind): string {
  if (kind === 'COMMENT') return 'Не требуется'
  if (!labelIds?.length) return '—'
  return labelIds
    .map((id) => labels.value.find((l) => l.id === id)?.name)
    .filter(Boolean)
    .join(', ') || '—'
}

</script>

<template>
  <section class="space-y-4">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-semibold text-slate-800">Правила меток</h1>
        <p class="text-sm text-slate-500">Активные правила применяются автоматически после распознавания звонка.</p>
      </div>
      <div class="flex gap-2">
        <PButton label="Добавить правило" icon="pi pi-plus" @click="createDialog = true" />
      </div>
    </div>

    <div class="bg-white border border-slate-200 rounded-xl p-3">
      <div v-if="loading" class="space-y-2 p-2">
        <PSkeleton height="2rem" />
        <PSkeleton height="2rem" />
      </div>

      <PDataTable v-else :value="rules" stripedRows>
        <PColumn field="name" header="Название" />
        <PColumn header="Вид">
          <template #body="slotProps">
            <PTag :value="kindLabel(slotProps.data.kind)" :severity="kindBadge(slotProps.data.kind)" />
          </template>
        </PColumn>
        <PColumn field="rule_type" header="Тип" />
        <PColumn header="Метки">
          <template #body="slotProps">
            <span class="text-sm">{{ labelNames(slotProps.data.label_ids, slotProps.data.kind) }}</span>
          </template>
        </PColumn>
        <PColumn header="Условие">
          <template #body="slotProps">
            <span v-if="slotProps.data.rule_type === 'KEYWORD'" class="text-sm">
              {{ slotProps.data.keyword_query || '—' }}
              <span v-if="slotProps.data.keyword_search_part && slotProps.data.keyword_search_part !== 'ANY'" class="text-slate-500">
                ({{ slotProps.data.keyword_search_part }})
              </span>
            </span>
            <span v-else class="text-sm line-clamp-2">{{ slotProps.data.llm_prompt || '—' }}</span>
          </template>
        </PColumn>
        <PColumn header="Состояние">
          <template #body="slotProps">
            <PTag :value="slotProps.data.is_enabled ? 'ENABLED' : 'DISABLED'" :severity="slotProps.data.is_enabled ? 'success' : 'warning'" />
          </template>
        </PColumn>
        <PColumn header="Действия">
          <template #body="slotProps">
            <div class="flex gap-2">
              <PButton label="Редактировать" size="small" severity="secondary" text @click="openEditDialog(slotProps.data)" />
              <PButton
                v-if="slotProps.data.rule_type === 'LLM'"
                label="Проверить"
                size="small"
                severity="secondary"
                text
                @click="openEditDialog(slotProps.data)"
              />
              <PButton
                :label="slotProps.data.is_enabled ? 'Выключить' : 'Включить'"
                size="small"
                severity="secondary"
                outlined
                @click="toggleEnabled(slotProps.data)"
              />
              <PButton label="Удалить" size="small" severity="danger" outlined @click="deleteRule(slotProps.data)" />
            </div>
          </template>
        </PColumn>
      </PDataTable>
    </div>

    <!-- Create Label dialog -->
    <PDialog v-model:visible="createLabelDialog" modal header="Новая метка" :style="{ width: '30rem' }">
      <div class="space-y-3">
        <div>
          <label class="block text-sm mb-1">Название</label>
          <PInputText v-model="newLabelForm.name" class="w-full" placeholder="напр. Целевой звонок" />
          <p class="text-xs text-slate-500 mt-1">Код сгенерируется автоматически из названия.</p>
        </div>
      </div>
      <template #footer>
        <PButton label="Отмена" severity="secondary" text @click="createLabelDialog = false" />
        <PButton label="Создать" @click="createLabel" />
      </template>
    </PDialog>

    <!-- Create Rule dialog -->
    <PDialog v-model:visible="createDialog" modal header="Новое правило" :style="{ width: '48rem' }">
      <div class="space-y-3">
        <div class="grid md:grid-cols-2 gap-3">
          <div>
            <label class="block text-sm mb-1">Название правила</label>
            <PInputText v-model="form.name" class="w-full" />
          </div>
          <div>
            <label class="block text-sm mb-1">Вид метки</label>
            <PDropdown v-model="form.kind" :options="kindOptions" optionLabel="label" optionValue="value" class="w-full" />
          </div>
        </div>

        <div>
          <div class="flex items-center justify-between mb-1">
            <label class="block text-sm">Метки</label>
            <PButton
              label="+ создать"
              size="small"
              severity="secondary"
              text
              @click="openCreateLabelDialog(form.kind)"
            />
          </div>
          <div v-if="form.kind === 'COMMENT'" class="text-xs text-slate-500 border border-slate-200 bg-slate-50 rounded-lg px-3 py-2">
            Для COMMENT метка не требуется. Название правила будет использоваться как заголовок комментария.
          </div>
          <PMultiSelect
            v-else-if="form.kind === 'FLAG'"
            v-model="form.label_ids"
            :options="labelsForEditKind('FLAG')"
            optionLabel="name"
            optionValue="id"
            :maxSelectedLabels="10"
            placeholder="Выберите метки"
            class="w-full"
          />
          <PDropdown
            v-else
            v-model="createSingleLabelId"
            :options="labelsForEditKind(form.kind as 'FLAG_VALUE' | 'COMMENT')"
            optionLabel="name"
            optionValue="id"
            placeholder="Выберите метку"
            class="w-full"
          />
          <div v-if="labelsLoading" class="text-xs text-slate-500 mt-1">Загрузка меток...</div>
        </div>

        <div>
          <label class="block text-sm mb-1">Тип правила</label>
          <PDropdown v-model="form.rule_type" :options="ruleTypeOptions" optionLabel="label" optionValue="value" class="w-full" />
        </div>

        <template v-if="form.rule_type === 'KEYWORD'">
          <div>
            <label class="block text-sm mb-1">Слова/фразы для поиска</label>
            <PTextarea v-model="form.keyword_query" rows="3" class="w-full" placeholder="через запятую или с новой строки" />
          </div>
          <div>
            <label class="block text-sm mb-1">Часть диалога</label>
            <PDropdown v-model="form.keyword_search_part" :options="searchPartOptions" optionLabel="label" optionValue="value" class="w-full" />
          </div>
        </template>

        <template v-else>
          <div>
            <label class="block text-sm mb-1">Промпт для LLM</label>
            <PTextarea
              v-model="form.llm_prompt"
              rows="6"
              class="w-full"
              placeholder="Опиши условие, при котором нужно поставить метку..."
            />
          </div>
          <div>
            <PButton
              label="Проверить промпт"
              icon="pi pi-check-circle"
              severity="secondary"
              outlined
              size="small"
              :disabled="!canValidateCreatePrompt"
              @click="validateCreatePrompt"
            />
          </div>
          <div>
            <label class="block text-sm mb-1">Звонок для проверки</label>
            <PDropdown
              v-model="createValidation.call_id"
              :options="validationCallOptions"
              optionLabel="label"
              optionValue="value"
              placeholder="Выберите звонок"
              class="w-full"
              :loading="validationCallsLoading"
            />
          </div>
          <div v-if="createValidation.result" class="mt-1">
            <div v-if="createValidation.result.valid" class="bg-green-50 border border-green-200 rounded-lg p-3 text-sm text-green-800">
              <strong>Валидный ответ:</strong> {{ createValidation.result.message }}
              <div v-if="createValidation.result.parsed" class="mt-2 text-xs">
                <div>kind={{ createValidation.result.parsed.kind }}, matched={{ createValidation.result.parsed.matched }}</div>
                <div v-if="createValidation.result.parsed.value_text">value_text={{ createValidation.result.parsed.value_text }}</div>
                <div v-if="createValidation.result.parsed.comment">comment={{ createValidation.result.parsed.comment }}</div>
              </div>
            </div>
            <div v-else class="bg-red-50 border border-red-200 rounded-lg p-3 text-sm text-red-800">
              <strong>Ошибка:</strong> {{ createValidation.result.message }}
            </div>
          </div>
        </template>

        <div class="flex items-center gap-2">
          <input id="rule-enabled" v-model="form.is_enabled" type="checkbox" />
          <label for="rule-enabled" class="text-sm text-slate-700">Сразу включить правило</label>
        </div>
      </div>

      <template #footer>
        <PButton label="Отмена" severity="secondary" text @click="createDialog = false" />
        <PButton label="Создать" :disabled="!canCreateRule" @click="createRule" />
      </template>
    </PDialog>

    <!-- Edit Rule dialog -->
    <PDialog v-model:visible="editDialog" modal header="Редактирование правила" :style="{ width: '48rem' }" @hide="closeEditDialog">
      <div class="space-y-3">
        <div class="grid md:grid-cols-2 gap-3">
          <div>
            <label class="block text-sm mb-1">Название</label>
            <PInputText v-model="editForm.name" class="w-full" />
          </div>
          <div>
            <label class="block text-sm mb-1">Вид метки</label>
            <PDropdown v-model="editForm.kind" :options="kindOptions" optionLabel="label" optionValue="value" class="w-full" disabled />
          </div>
        </div>

        <div>
          <div class="flex items-center justify-between mb-1">
            <label class="block text-sm">Метки</label>
            <PButton
              label="+ создать"
              size="small"
              severity="secondary"
              text
              @click="openCreateLabelDialog(editForm.kind)"
            />
          </div>
          <div v-if="editForm.kind === 'COMMENT'" class="text-xs text-slate-500 border border-slate-200 bg-slate-50 rounded-lg px-3 py-2">
            Для COMMENT метка не требуется. Название правила используется как заголовок комментария.
          </div>
          <PMultiSelect
            v-else-if="editForm.kind === 'FLAG'"
            v-model="editForm.label_ids"
            :options="labelsForEditKind('FLAG')"
            optionLabel="name"
            optionValue="id"
            :maxSelectedLabels="10"
            placeholder="Выберите метки"
            class="w-full"
          />
          <PDropdown
            v-else
            v-model="editSingleLabelId"
            :options="labelsForEditKind(editForm.kind as 'FLAG_VALUE' | 'COMMENT')"
            optionLabel="name"
            optionValue="id"
            placeholder="Выберите метку"
            class="w-full"
          />
        </div>

        <div>
          <label class="block text-sm mb-1">Тип правила</label>
          <PInputText :model-value="editForm.rule_type" class="w-full" disabled />
        </div>

        <template v-if="editForm.rule_type === 'KEYWORD'">
          <div>
            <label class="block text-sm mb-1">Слова/фразы для поиска</label>
            <PTextarea v-model="editForm.keyword_query" rows="3" class="w-full" />
          </div>
          <div>
            <label class="block text-sm mb-1">Часть диалога</label>
            <PDropdown v-model="editForm.keyword_search_part" :options="searchPartOptions" optionLabel="label" optionValue="value" class="w-full" />
          </div>
        </template>

        <template v-else>
          <div>
            <label class="block text-sm mb-1">Промпт для LLM</label>
            <PTextarea v-model="editForm.llm_prompt" rows="6" class="w-full" />
          </div>
          <div>
            <PButton
              label="Проверить промпт"
              icon="pi pi-check-circle"
              severity="secondary"
              outlined
              size="small"
              :disabled="!canValidateEditPrompt"
              @click="validateEditPrompt"
            />
          </div>
          <div>
            <label class="block text-sm mb-1">Звонок для проверки</label>
            <PDropdown
              v-model="editValidation.call_id"
              :options="validationCallOptions"
              optionLabel="label"
              optionValue="value"
              placeholder="Выберите звонок"
              class="w-full"
              :loading="validationCallsLoading"
            />
          </div>
          <div v-if="editValidation.result" class="mt-1">
            <div v-if="editValidation.result.valid" class="bg-green-50 border border-green-200 rounded-lg p-3 text-sm text-green-800">
              <strong>Валидный ответ:</strong> {{ editValidation.result.message }}
              <div v-if="editValidation.result.parsed" class="mt-2 text-xs">
                <div>kind={{ editValidation.result.parsed.kind }}, matched={{ editValidation.result.parsed.matched }}</div>
                <div v-if="editValidation.result.parsed.value_text">value_text={{ editValidation.result.parsed.value_text }}</div>
                <div v-if="editValidation.result.parsed.comment">comment={{ editValidation.result.parsed.comment }}</div>
              </div>
            </div>
            <div v-else class="bg-red-50 border border-red-200 rounded-lg p-3 text-sm text-red-800">
              <strong>Ошибка:</strong> {{ editValidation.result.message }}
            </div>
          </div>
        </template>

        <div class="flex items-center gap-2">
          <input id="rule-edit-enabled" v-model="editForm.is_enabled" type="checkbox" />
          <label for="rule-edit-enabled" class="text-sm text-slate-700">Правило включено</label>
        </div>
      </div>

      <template #footer>
        <PButton label="Отмена" severity="secondary" text @click="closeEditDialog" />
        <PButton label="Сохранить" :disabled="!canUpdateRule" @click="updateRule" />
      </template>
    </PDialog>

  </section>
</template>
