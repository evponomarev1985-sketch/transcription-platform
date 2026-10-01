<script setup lang="ts">
import { useToast } from 'primevue/usetoast'
import type {
  Checklist,
  ChecklistAnswer,
  ChecklistConditionLine,
  ChecklistConditionOperator,
  ChecklistConditionTarget,
  ChecklistLabelValuesResponse,
  ChecklistQuestion,
  LabelDefinition,
} from '~/types/calls'

const toast = useToast()
const { apiFetch } = useApi()

const loading = ref(true)
const saving = ref(false)
const editDialog = ref(false)

const checklists = ref<Checklist[]>([])
const labels = ref<LabelDefinition[]>([])
const labelValueOptions = ref<Record<string, Array<{ value: string; usage_count: number }>>>({})

const form = ref<Checklist | null>(null)

const operatorOptions: Array<{ label: string; value: ChecklistConditionOperator }> = [
  { label: 'Наличие любого', value: 'INCLUDE_ANY' },
  { label: 'Наличие полного', value: 'INCLUDE_ALL' },
  { label: 'Исключить любое', value: 'EXCLUDE_ANY' },
  { label: 'Исключить полное', value: 'EXCLUDE_ALL' },
]

function uid(prefix: string) {
  return `${prefix}_${Math.random().toString(36).slice(2, 10)}`
}

function emptyTarget(): ChecklistConditionTarget {
  return { label_id: '', values: [], value: null }
}

function emptyLine(): ChecklistConditionLine {
  return { operator: 'INCLUDE_ANY', targets: [emptyTarget()] }
}

function emptyAnswer(): ChecklistAnswer {
  return { text: '', score: 0, conditions: [emptyLine()] }
}

function emptyQuestion(): ChecklistQuestion {
  return { id: uid('q'), text: '', answers: [emptyAnswer()] }
}

function emptyChecklist(): Checklist {
  return {
    id: '',
    name: '',
    description: null,
    is_active: true,
    apply_filters: [],
    questions: [emptyQuestion()],
    created_at: '',
    updated_at: '',
  }
}

const labelOptions = computed(() => labels.value.map((l) => ({ label: l.name, value: l.id })))
const labelById = computed<Record<string, LabelDefinition>>(() => {
  const m: Record<string, LabelDefinition> = {}
  for (const l of labels.value) m[l.id] = l
  return m
})

function availableValuesForLabel(labelId: string) {
  if (!labelId) return []
  const fromApi = labelValueOptions.value[labelId] || []
  if (fromApi.length) {
    return fromApi.map((x) => ({ label: x.value, value: x.value }))
  }
  const options: Array<{ label: string; value: string }> = []
  const candidateTexts = new Set<string>()

  for (const rule of checklists.value) {
    for (const q of rule.questions || []) {
      for (const a of q.answers || []) {
        for (const line of a.conditions || []) {
          for (const t of line.targets || []) {
            if (t.label_id !== labelId) continue
            for (const v of t.values || []) {
              if (v) candidateTexts.add(v)
            }
            if (t.value) candidateTexts.add(t.value)
          }
        }
      }
    }
  }

  if (candidateTexts.size === 0) {
    const label = labelById.value[labelId]
    if (label?.kind === 'FLAG') {
      options.push({ label: label.name, value: label.name })
    }
  }

  for (const v of candidateTexts) {
    options.push({ label: v, value: v })
  }
  return options
}

function onLabelChanged(target: ChecklistConditionTarget) {
  target.values = []
  target.value = null
}

function syncLegacyValue(target: ChecklistConditionTarget) {
  target.value = target.values.length ? target.values[0] : null
}

function isValueSelectionRequired(labelId: string) {
  const label = labelById.value[labelId]
  return label?.kind === 'FLAG_VALUE'
}

function operatorLabel(op: ChecklistConditionOperator) {
  return operatorOptions.find((x) => x.value === op)?.label || op
}

async function loadData() {
  loading.value = true
  try {
    const [checklistsRes, labelsRes, valuesRes] = await Promise.all([
      apiFetch<{ items: Checklist[] }>('/checklists'),
      apiFetch<{ items: LabelDefinition[] }>('/calls/labels'),
      apiFetch<ChecklistLabelValuesResponse>('/checklists/label-values'),
    ])
    checklists.value = checklistsRes.items
    labels.value = labelsRes.items
    labelValueOptions.value = valuesRes.items || {}
  } catch (error) {
    toast.add({ severity: 'error', summary: 'Ошибка', detail: (error as Error).message, life: 3000 })
  } finally {
    loading.value = false
  }
}

onMounted(loadData)

function openCreate() {
  form.value = emptyChecklist()
  editDialog.value = true
}

function openEdit(item: Checklist) {
  const cloned = JSON.parse(JSON.stringify(item)) as Checklist
  for (const line of cloned.apply_filters || []) {
    for (const target of line.targets || []) {
      if (!Array.isArray(target.values)) {
        target.values = target.value ? [target.value] : []
      }
      target.value = target.values.length ? target.values[0] : null
    }
  }
  for (const q of cloned.questions || []) {
    for (const a of q.answers || []) {
      for (const line of a.conditions || []) {
        for (const target of line.targets || []) {
          if (!Array.isArray(target.values)) {
            target.values = target.value ? [target.value] : []
          }
          target.value = target.values.length ? target.values[0] : null
        }
      }
    }
  }
  form.value = cloned
  editDialog.value = true
}

function addFilterLine() {
  if (!form.value) return
  form.value.apply_filters.push(emptyLine())
}

function removeFilterLine(idx: number) {
  if (!form.value) return
  form.value.apply_filters.splice(idx, 1)
}

function addQuestion() {
  if (!form.value) return
  form.value.questions.push(emptyQuestion())
}

function removeQuestion(idx: number) {
  if (!form.value) return
  form.value.questions.splice(idx, 1)
}

function moveQuestionUp(idx: number) {
  if (!form.value || idx <= 0) return
  const arr = form.value.questions
  ;[arr[idx - 1], arr[idx]] = [arr[idx], arr[idx - 1]]
}

function moveQuestionDown(idx: number) {
  if (!form.value || idx >= form.value.questions.length - 1) return
  const arr = form.value.questions
  ;[arr[idx + 1], arr[idx]] = [arr[idx], arr[idx + 1]]
}

function addAnswer(qIdx: number) {
  if (!form.value) return
  form.value.questions[qIdx].answers.push(emptyAnswer())
}

function removeAnswer(qIdx: number, aIdx: number) {
  if (!form.value) return
  form.value.questions[qIdx].answers.splice(aIdx, 1)
}

function addConditionLine(qIdx: number, aIdx: number) {
  if (!form.value) return
  form.value.questions[qIdx].answers[aIdx].conditions.push(emptyLine())
}

function removeConditionLine(qIdx: number, aIdx: number, lineIdx: number) {
  if (!form.value) return
  form.value.questions[qIdx].answers[aIdx].conditions.splice(lineIdx, 1)
}

function addTarget(line: ChecklistConditionLine) {
  line.targets.push(emptyTarget())
}

function removeTarget(line: ChecklistConditionLine, idx: number) {
  line.targets.splice(idx, 1)
}

function normalizeChecklistPayload(item: Checklist) {
  const applyFilters = (item.apply_filters || [])
    .map((line) => ({
      operator: line.operator,
      targets: (line.targets || [])
        .filter((t) => t.label_id)
        .map((t) => {
          const values = (t.values || []).map((v) => v.trim()).filter(Boolean)
          return { label_id: t.label_id, values, value: values[0] || null }
        }),
    }))
    .filter((line) => line.targets.length > 0)

  const questions = (item.questions || [])
    .map((q) => ({
      id: q.id || uid('q'),
      text: q.text.trim(),
      answers: (q.answers || [])
        .map((a) => ({
          text: a.text.trim(),
          score: Number(a.score || 0),
          conditions: (a.conditions || [])
            .map((line) => ({
              operator: line.operator,
              targets: (line.targets || [])
                .filter((t) => t.label_id)
                .map((t) => {
                  const values = (t.values || []).map((v) => v.trim()).filter(Boolean)
                  return { label_id: t.label_id, values, value: values[0] || null }
                }),
            }))
            .filter((line) => line.targets.length > 0),
        }))
        .filter((a) => a.text),
    }))
    .filter((q) => q.text && q.answers.length > 0)

  return {
    name: item.name.trim(),
    description: item.description?.trim() || null,
    is_active: item.is_active,
    apply_filters: applyFilters,
    questions,
  }
}

async function saveChecklist() {
  if (!form.value) return
  const payload = normalizeChecklistPayload(form.value)
  if (!payload.name) {
    toast.add({ severity: 'warn', summary: 'Проверка', detail: 'Укажите название чек-листа', life: 2500 })
    return
  }
  if (!payload.questions.length) {
    toast.add({ severity: 'warn', summary: 'Проверка', detail: 'Добавьте хотя бы один вопрос', life: 2500 })
    return
  }

  for (const q of payload.questions) {
    for (const a of q.answers) {
      for (const line of a.conditions) {
        for (const t of line.targets) {
          if (isValueSelectionRequired(t.label_id) && (!t.values || t.values.length === 0)) {
            toast.add({ severity: 'warn', summary: 'Проверка', detail: 'Для метки-значения нужно выбрать хотя бы одно значение', life: 3000 })
            return
          }
        }
      }
    }
  }

  for (const line of payload.apply_filters) {
    for (const t of line.targets) {
      if (isValueSelectionRequired(t.label_id) && (!t.values || t.values.length === 0)) {
        toast.add({ severity: 'warn', summary: 'Проверка', detail: 'Для метки-значения нужно выбрать хотя бы одно значение', life: 3000 })
        return
      }
    }
  }

  saving.value = true
  try {
    if (form.value.id) {
      await apiFetch(`/checklists/${form.value.id}`, {
        method: 'PATCH',
        body: JSON.stringify(payload),
      })
    } else {
      await apiFetch('/checklists', {
        method: 'POST',
        body: JSON.stringify(payload),
      })
    }
    editDialog.value = false
    toast.add({ severity: 'success', summary: 'Сохранено', detail: 'Чек-лист обновлен', life: 2500 })
    await loadData()
  } catch (error) {
    toast.add({ severity: 'error', summary: 'Ошибка', detail: (error as Error).message, life: 3000 })
  } finally {
    saving.value = false
  }
}

async function removeChecklist(item: Checklist) {
  try {
    await apiFetch(`/checklists/${item.id}`, { method: 'DELETE' })
    toast.add({ severity: 'success', summary: 'Удалено', detail: 'Чек-лист удален', life: 2500 })
    await loadData()
  } catch (error) {
    toast.add({ severity: 'error', summary: 'Ошибка', detail: (error as Error).message, life: 3000 })
  }
}
</script>

<template>
  <section class="space-y-4">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-semibold text-slate-800">Чек-листы</h1>
        <p class="text-sm text-slate-500">Пункты и ответы рассчитываются автоматически по найденным меткам звонка.</p>
      </div>
      <PButton label="Новый чек-лист" icon="pi pi-plus" @click="openCreate" />
    </div>

    <div class="bg-white border border-slate-200 rounded-xl p-3">
      <div v-if="loading" class="space-y-2 p-2">
        <PSkeleton height="2rem" />
        <PSkeleton height="2rem" />
      </div>

      <PDataTable v-else :value="checklists" stripedRows>
        <PColumn field="name" header="Название" />
        <PColumn header="Вопросов">
          <template #body="slotProps">
            {{ slotProps.data.questions?.length || 0 }}
          </template>
        </PColumn>
        <PColumn header="Фильтров">
          <template #body="slotProps">
            {{ slotProps.data.apply_filters?.length || 0 }}
          </template>
        </PColumn>
        <PColumn header="Статус">
          <template #body="slotProps">
            <PTag :value="slotProps.data.is_active ? 'ACTIVE' : 'DISABLED'" :severity="slotProps.data.is_active ? 'success' : 'warning'" />
          </template>
        </PColumn>
        <PColumn header="Действия">
          <template #body="slotProps">
            <div class="flex gap-2">
              <PButton label="Редактировать" size="small" severity="secondary" text @click="openEdit(slotProps.data)" />
              <PButton label="Удалить" size="small" severity="danger" text @click="removeChecklist(slotProps.data)" />
            </div>
          </template>
        </PColumn>
      </PDataTable>
    </div>

    <PDialog v-model:visible="editDialog" modal :style="{ width: '70rem' }" header="Чек-лист">
      <div v-if="form" class="space-y-5">
        <div class="grid md:grid-cols-2 gap-3">
          <div>
            <label class="block text-sm mb-1">Название</label>
            <PInputText v-model="form.name" class="w-full" />
          </div>
          <div>
            <label class="block text-sm mb-1">Активен</label>
            <div class="h-10 flex items-center">
              <PInputSwitch v-model="form.is_active" />
            </div>
          </div>
          <div class="md:col-span-2">
            <label class="block text-sm mb-1">Описание</label>
            <PTextarea v-model="form.description" rows="2" class="w-full" />
          </div>
        </div>

        <div class="rounded-xl border border-slate-200 p-3 space-y-3">
          <div class="flex items-center justify-between">
            <h3 class="font-medium text-slate-800">Фильтры применения (И между строками)</h3>
            <PButton label="Добавить строку" size="small" text @click="addFilterLine" />
          </div>
          <div v-if="!form.apply_filters.length" class="text-sm text-slate-500">Без фильтров: чек-лист применяется ко всем звонкам.</div>
          <div v-for="(line, lIdx) in form.apply_filters" :key="`f-${lIdx}`" class="rounded-lg border border-slate-200 p-3 space-y-2">
            <div class="grid md:grid-cols-[240px_1fr_auto] gap-2 items-start">
              <PDropdown v-model="line.operator" :options="operatorOptions" optionLabel="label" optionValue="value" class="w-full" />
              <div class="space-y-2">
                <div v-for="(target, tIdx) in line.targets" :key="`ft-${tIdx}`" class="grid md:grid-cols-[1fr_1fr_auto] gap-2">
                  <PDropdown
                    v-model="target.label_id"
                    :options="labelOptions"
                    optionLabel="label"
                    optionValue="value"
                    placeholder="Метка"
                    class="w-full"
                    @update:modelValue="onLabelChanged(target)"
                  />
                  <PMultiSelect
                    v-model="target.values"
                    :options="availableValuesForLabel(target.label_id)"
                    optionLabel="label"
                    optionValue="value"
                    placeholder="Значения"
                    class="w-full"
                    :showToggleAll="false"
                    :invalid="isValueSelectionRequired(target.label_id) && target.values.length === 0"
                    @update:modelValue="syncLegacyValue(target)"
                  />
                  <PButton icon="pi pi-times" severity="secondary" text @click="removeTarget(line, tIdx)" />
                </div>
                <div
                  v-if="line.targets.some((target) => isValueSelectionRequired(target.label_id) && target.values.length === 0)"
                  class="text-xs text-amber-700"
                >
                  Для выбранных меток-значений нужно выбрать хотя бы одно значение.
                </div>
              </div>
              <div class="flex flex-col gap-1">
                <PButton icon="pi pi-plus" severity="secondary" text @click="addTarget(line)" />
                <PButton icon="pi pi-trash" severity="danger" text @click="removeFilterLine(lIdx)" />
              </div>
            </div>
          </div>
        </div>

        <div class="rounded-xl border border-slate-200 p-3 space-y-3">
          <div class="flex items-center justify-between">
            <h3 class="font-medium text-slate-800">Вопросы</h3>
            <PButton label="Добавить вопрос" size="small" text @click="addQuestion" />
          </div>

          <div v-for="(question, qIdx) in form.questions" :key="question.id || qIdx" class="rounded-lg border border-slate-200 p-3 space-y-3">
            <div class="flex items-start gap-2">
              <PInputText v-model="question.text" placeholder="Текст вопроса" class="w-full" />
              <PButton icon="pi pi-arrow-up" severity="secondary" text @click="moveQuestionUp(qIdx)" />
              <PButton icon="pi pi-arrow-down" severity="secondary" text @click="moveQuestionDown(qIdx)" />
              <PButton icon="pi pi-trash" severity="danger" text @click="removeQuestion(qIdx)" />
            </div>

            <div class="space-y-2">
              <div class="flex items-center justify-between">
                <div class="text-sm text-slate-600">Ответы</div>
                <PButton label="Добавить ответ" size="small" text @click="addAnswer(qIdx)" />
              </div>

              <div v-for="(answer, aIdx) in question.answers" :key="`a-${aIdx}`" class="rounded-lg border border-slate-100 bg-slate-50 p-3 space-y-2">
                <div class="grid md:grid-cols-[1fr_150px_auto] gap-2">
                <PInputText v-model="answer.text" placeholder="Текст ответа" class="w-full" />
                  <PInputNumber v-model="answer.score" mode="decimal" :min="0" :minFractionDigits="0" :maxFractionDigits="2" class="w-full" />
                  <PButton icon="pi pi-trash" severity="danger" text @click="removeAnswer(qIdx, aIdx)" />
                </div>

                <div class="space-y-2">
                  <div class="flex items-center justify-between">
                    <div class="text-xs text-slate-600">Условия срабатывания (И между строками)</div>
                    <PButton label="Добавить строку" size="small" text @click="addConditionLine(qIdx, aIdx)" />
                  </div>

                  <div v-for="(line, lineIdx) in answer.conditions" :key="`c-${lineIdx}`" class="rounded-lg border border-slate-200 bg-white p-2">
                    <div class="grid md:grid-cols-[240px_1fr_auto] gap-2 items-start">
                      <PDropdown v-model="line.operator" :options="operatorOptions" optionLabel="label" optionValue="value" class="w-full" />
                      <div class="space-y-2">
                        <div v-for="(target, tIdx) in line.targets" :key="`ct-${tIdx}`" class="grid md:grid-cols-[1fr_1fr_auto] gap-2">
                          <PDropdown
                            v-model="target.label_id"
                            :options="labelOptions"
                            optionLabel="label"
                            optionValue="value"
                            placeholder="Метка"
                            class="w-full"
                            @update:modelValue="onLabelChanged(target)"
                          />
                          <PMultiSelect
                            v-model="target.values"
                            :options="availableValuesForLabel(target.label_id)"
                            optionLabel="label"
                            optionValue="value"
                            placeholder="Значения"
                            class="w-full"
                            :showToggleAll="false"
                            :invalid="isValueSelectionRequired(target.label_id) && target.values.length === 0"
                            @update:modelValue="syncLegacyValue(target)"
                          />
                          <PButton icon="pi pi-times" severity="secondary" text @click="removeTarget(line, tIdx)" />
                        </div>
                        <div
                          v-if="line.targets.some((target) => isValueSelectionRequired(target.label_id) && target.values.length === 0)"
                          class="text-xs text-amber-700"
                        >
                          Для выбранных меток-значений нужно выбрать хотя бы одно значение.
                        </div>
                      </div>
                      <div class="flex flex-col gap-1">
                        <PButton icon="pi pi-plus" severity="secondary" text @click="addTarget(line)" />
                        <PButton icon="pi pi-trash" severity="danger" text @click="removeConditionLine(qIdx, aIdx, lineIdx)" />
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <template #footer>
        <PButton label="Отмена" severity="secondary" text @click="editDialog = false" />
        <PButton label="Сохранить" :loading="saving" @click="saveChecklist" />
      </template>
    </PDialog>

    <div class="bg-slate-50 border border-slate-200 rounded-xl p-4 text-sm text-slate-700 leading-6">
      <div class="font-medium mb-2">Правила операторов в строке условий:</div>
      <ul class="list-disc pl-5 space-y-1">
        <li><b>{{ operatorLabel('INCLUDE_ANY') }}</b> — есть хотя бы одно значение из строки.</li>
        <li><b>{{ operatorLabel('INCLUDE_ALL') }}</b> — есть все значения из строки одновременно.</li>
        <li><b>{{ operatorLabel('EXCLUDE_ANY') }}</b> — нет ни одного значения из строки.</li>
        <li><b>{{ operatorLabel('EXCLUDE_ALL') }}</b> — не найдены сразу все значения из строки.</li>
      </ul>
      <p class="mt-2 text-xs text-slate-500">Если значение не указано, проверяется только факт наличия метки с любым значением.</p>
    </div>
  </section>
</template>
