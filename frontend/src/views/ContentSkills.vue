<template>
  <div class="crm-page">
    <el-card class="crm-card">
      <template #header>
        <div class="crm-card__header">
          <span class="crm-card__title">Skills 管理中心</span>
          <div class="crm-card__actions">
            <el-button
              type="primary"
              class="crm-btn"
              @click="openCreate"
            >
              新增 Skill
            </el-button>
          </div>
        </div>
      </template>

      <el-alert
        type="info"
        :closable="false"
        title="仅管理员可访问。停用的 Skill 不会出现在选题页与生成表单的选用列表中。"
        class="crm-alert"
      />

      <el-table
        v-loading="loading"
        :data="visibleSkills"
        :span-method="spanDnaSource"
        class="crm-table"
      >
        <el-table-column
          prop="name"
          label="名称"
          min-width="160"
        />
        <el-table-column
          prop="code"
          label="标识"
          min-width="140"
        />
        <el-table-column
          prop="source_dna"
          label="DNA 来源"
          min-width="130"
        >
          <template #default="{ row }">
            {{ row.source_dna_label || '兼容旧 Skill' }}
          </template>
        </el-table-column>
        <el-table-column
          label="类型"
          min-width="100"
        >
          <template #default="{ row }">
            <el-tag :type="row.skill_type === 'topic' ? 'warning' : 'success'">
              {{ row.skill_type === 'topic' ? '选题' : '内容' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column
          label="状态"
          min-width="100"
        >
          <template #default="{ row }">
            <el-tag :type="row.enabled ? 'success' : 'info'">
              {{ row.enabled ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column
          prop="prompt_version"
          label="版本"
          min-width="90"
        />
        <el-table-column
          prop="sort_order"
          label="排序"
          min-width="80"
        />
        <el-table-column
          label="操作"
          min-width="180"
          fixed="right"
        >
          <template #default="{ row }">
            <el-button
              size="small"
              @click="openEdit(row)"
            >
              编辑
            </el-button>
            <el-button
              size="small"
              :type="row.enabled ? 'warning' : 'success'"
              @click="handleToggle(row)"
            >
              {{ row.enabled ? '停用' : '启用' }}
            </el-button>
            <el-button
              size="small"
              type="danger"
              @click="handleDelete(row)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog
      v-model="dialogVisible"
      :title="editing ? '编辑 Skill' : '新增 Skill'"
      width="640px"
    >
      <el-form
        :model="form"
        label-width="88px"
      >
        <el-form-item
          v-if="!editing"
          label="标识"
          required
        >
          <el-input
            v-model="form.code"
            placeholder="唯一标识，如 content-default"
          />
        </el-form-item>
        <el-form-item
          label="名称"
          required
        >
          <el-input
            v-model="form.name"
            placeholder="展示名"
          />
        </el-form-item>
        <el-form-item
          v-if="!editing"
          label="类型"
          required
        >
          <el-select v-model="form.skill_type">
            <el-option
              label="选题"
              value="topic"
            />
            <el-option
              label="内容"
              value="content"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="描述">
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="2"
          />
        </el-form-item>
        <el-form-item label="提示词模板">
          <el-input
            v-model="form.prompt_template"
            type="textarea"
            :rows="6"
            placeholder="支持 {topic}/{platform}/{tone}/{product_facts}/{output_schema} 占位符"
          />
        </el-form-item>
        <el-form-item label="支持平台">
          <el-select
            v-model="form.supported_platforms"
            multiple
          >
            <el-option
              v-for="(label, value) in PLATFORM_MAP"
              :key="value"
              :label="label"
              :value="value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="版本">
          <el-input
            v-model="form.prompt_version"
            placeholder="v1"
          />
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number
            v-model="form.sort_order"
            :min="0"
          />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">
          取消
        </el-button>
        <el-button
          type="primary"
          :loading="saving"
          @click="handleSave"
        >
          保存
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { contentApi, type ContentSkill } from '@/api/content'

const PLATFORM_MAP: Record<string, string> = {
  xhs: '小红书',
  douyin: '抖音',
  moments: '朋友圈',
  seo: 'SEO/官网',
  other: '其他',
}

const loading = ref(false)
const saving = ref(false)
const skills = ref<ContentSkill[]>([])
const visibleSkills = computed(() => {
  return skills.value.filter((skill) => ['yuc', 'yanye'].includes(skill.source_dna || ''))
})

function spanDnaSource({ column, rowIndex }: { column: { property?: string }; rowIndex: number }) {
  if (column.property !== 'source_dna') return [1, 1]
  const source = visibleSkills.value[rowIndex]?.source_dna
  if (rowIndex > 0 && visibleSkills.value[rowIndex - 1]?.source_dna === source) return [0, 0]
  let rowspan = 1
  while (visibleSkills.value[rowIndex + rowspan]?.source_dna === source) rowspan += 1
  return [rowspan, 1]
}
const dialogVisible = ref(false)
const editing = ref<ContentSkill | null>(null)

const form = reactive({
  code: '',
  name: '',
  skill_type: 'content' as 'topic' | 'content',
  description: '',
  prompt_template: '',
  supported_platforms: [] as string[],
  prompt_version: 'v1',
  sort_order: 0,
  enabled: true,
})

async function loadSkills() {
  loading.value = true
  try {
    const res = await contentApi.listSkillsForManage()
    skills.value = res.data || []
  } catch (error: unknown) {
    const detail = (error as { response?: { data?: { detail?: { msg?: string } } } })?.response
      ?.data?.detail
    ElMessage.error(detail?.msg || '加载失败：需要管理员权限')
    skills.value = []
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editing.value = null
  form.code = ''
  form.name = ''
  form.skill_type = 'content'
  form.description = ''
  form.prompt_template = ''
  form.supported_platforms = []
  form.prompt_version = 'v1'
  form.sort_order = 0
  form.enabled = true
  dialogVisible.value = true
}

function openEdit(skill: ContentSkill) {
  editing.value = skill
  form.code = skill.code
  form.name = skill.name
  form.skill_type = skill.skill_type
  form.description = skill.description || ''
  form.prompt_template = skill.prompt_template || ''
  form.supported_platforms = skill.supported_platforms || []
  form.prompt_version = skill.prompt_version
  form.sort_order = skill.sort_order
  form.enabled = skill.enabled
  dialogVisible.value = true
}

async function handleSave() {
  if (!form.name.trim()) {
    ElMessage.warning('请填写名称')
    return
  }
  if (!editing.value && !form.code.trim()) {
    ElMessage.warning('请填写标识')
    return
  }
  saving.value = true
  try {
    if (editing.value) {
      const res = await contentApi.updateSkill(editing.value.id, {
        name: form.name.trim(),
        description: form.description || null,
        prompt_template: form.prompt_template || null,
        supported_platforms: form.supported_platforms,
        prompt_version: form.prompt_version,
        sort_order: form.sort_order,
        enabled: form.enabled,
      })
      skills.value = skills.value.map((s) => (s.id === editing.value!.id ? res.data : s))
      ElMessage.success('已保存')
    } else {
      const res = await contentApi.createSkill({
        code: form.code.trim(),
        name: form.name.trim(),
        skill_type: form.skill_type,
        description: form.description || null,
        prompt_template: form.prompt_template || null,
        supported_platforms: form.supported_platforms,
        prompt_version: form.prompt_version,
        sort_order: form.sort_order,
        enabled: form.enabled,
      })
      skills.value = [...skills.value, res.data]
      ElMessage.success('已创建')
    }
    dialogVisible.value = false
  } catch (error: unknown) {
    const detail = (error as { response?: { data?: { detail?: { msg?: string } } } })?.response
      ?.data?.detail
    ElMessage.error(detail?.msg || '保存失败：需要管理员权限')
  } finally {
    saving.value = false
  }
}

async function handleToggle(row: ContentSkill) {
  try {
    const res = await contentApi.toggleSkill(row.id, !row.enabled)
    skills.value = skills.value.map((s) => (s.id === row.id ? res.data : s))
    ElMessage.success(res.data.enabled ? '已启用' : '已停用')
  } catch (error: unknown) {
    const detail = (error as { response?: { data?: { detail?: { msg?: string } } } })?.response
      ?.data?.detail
    ElMessage.error(detail?.msg || '操作失败：需要管理员权限')
  }
}

async function handleDelete(row: ContentSkill) {
  try {
    await ElMessageBox.confirm(`确认删除 Skill「${row.name}」？`, '删除确认', {
      type: 'warning',
    })
    await contentApi.deleteSkill(row.id)
    skills.value = skills.value.filter((s) => s.id !== row.id)
    ElMessage.success('已删除')
  } catch {
    // 用户取消
  }
}

onMounted(loadSkills)
</script>
