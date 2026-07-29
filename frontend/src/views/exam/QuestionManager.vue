<template>
  <div class="question-manager">
    <div class="tab-actions">
      <el-button type="primary" @click="openAddQuestionDialog">
        <el-icon><Plus /></el-icon>
        添加题目
      </el-button>
      <el-button type="success" @click="showImportQuestionDialog = true">
        <el-icon><Upload /></el-icon>
        从文件导入题目
      </el-button>
      <el-button type="info" @click="showAddExistingDialog = true">
        <el-icon><DocumentCopy /></el-icon>
        添加已录入题目
      </el-button>
      <el-button @click="fetchQuestions">
        <el-icon><Refresh /></el-icon>
        刷新
      </el-button>
    </div>

    <div style="margin-bottom: 15px;">
      <el-button 
        type="danger" 
        @click="removeBatchQuestions" 
        :disabled="selectedExamQuestions.length === 0"
      >
        <el-icon><Delete /></el-icon>
        批量移除
      </el-button>
    </div>

    <el-table 
      ref="questionTableRef"
      :data="questions" 
      style="width: 100%"
      row-key="id"
      @selection-change="handleExamQuestionSelectionChange"
      @row-dblclick="handleQuestionDblClick"
      class="question-table"
    >
      <el-table-column type="selection" width="55" />
      <el-table-column type="index" label="序号" width="80" />
      <el-table-column label="题型" width="100">
        <template #default="scope">
          <el-tag :type="getQuestionTypeColor(scope.row.type)">
            {{ getQuestionTypeText(scope.row.type) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="题目内容" min-width="200">
        <template #default="scope">
          <div class="truncate-text" :title="scope.row.content">{{ scope.row.content }}</div>
        </template>
      </el-table-column>
      <el-table-column label="分值" width="80">
        <template #default="scope">
          <span>{{ scope.row.score }}</span>
        </template>
      </el-table-column>
      <el-table-column label="参考答案" min-width="150">
        <template #default="scope">
          <div class="truncate-text" :title="scope.row.reference_answer">{{ scope.row.reference_answer }}</div>
        </template>
      </el-table-column>
      <el-table-column label="赋分规则" min-width="150">
        <template #default="scope">
          <div style="display: flex; align-items: center; justify-content: space-between;">
            <div class="truncate-text" :title="scope.row.scoring_rules">{{ scope.row.scoring_rules || '无' }}</div>
            <el-icon class="drag-handle" style="cursor: move; color: #909399;"><Rank /></el-icon>
          </div>
        </template>
      </el-table-column>
    </el-table>
    <div style="margin-top: 10px; font-size: 12px; color: #909399;">
      提示：双击任意行可编辑题目。拖动 <el-icon><Rank /></el-icon> 可调整题目顺序（序号会自动更新）。
    </div>

    <!-- 题目编辑/添加对话框 -->
    <el-dialog
      v-model="showQuestionDialog"
      :title="isEditMode ? '编辑题目' : '添加题目'"
      width="800px"
      :close-on-click-modal="false"
    >
      <el-form :model="currentQuestion" label-width="100px">
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="题型" required>
              <el-select v-model="currentQuestion.question_type" style="width: 100%">
                <el-option label="选择题" value="choice" />
                <el-option label="填空题" value="fill_blank" />
                <el-option label="判断题" value="true_false" />
                <el-option label="简答题" value="essay" />
                <el-option label="计算题" value="calculation" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="分值" required>
              <el-input-number v-model="currentQuestion.total_score" :min="0" :precision="1" />
            </el-form-item>
          </el-col>
        </el-row>
        
        <el-form-item label="题目内容" required>
          <el-input
            v-model="currentQuestion.question_title"
            type="textarea"
            :rows="4"
            placeholder="请输入题目内容"
          />
        </el-form-item>
        
        <el-form-item label="参考答案">
          <el-input
            v-model="currentQuestion.reference_answer"
            type="textarea"
            :rows="3"
            placeholder="请输入参考答案"
          />
        </el-form-item>
        
        <el-form-item label="赋分规则">
          <el-input
            v-model="currentQuestion.scoring_rules"
            type="textarea"
            :rows="3"
            placeholder="请输入赋分规则"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showQuestionDialog = false">取消</el-button>
        <el-button type="primary" @click="handleSaveQuestion">保存</el-button>
      </template>
    </el-dialog>

    <!-- 添加已录入题目对话框 -->
    <el-dialog
      v-model="showAddExistingDialog"
      title="添加已录入题目"
      width="900px"
      @open="fetchAvailableQuestions"
    >
      <div style="margin-bottom: 15px; display: flex; gap: 10px;">
        <el-input
          v-model="searchKeyword"
          placeholder="搜索题目内容/题型"
          style="width: 300px;"
          @keyup.enter="searchAvailableQuestions"
        >
          <template #append>
            <el-button @click="searchAvailableQuestions"><el-icon><Search /></el-icon></el-button>
          </template>
        </el-input>
        <el-button @click="fetchAvailableQuestions">刷新</el-button>
      </div>

      <el-table
        :data="availableQuestions"
        style="width: 100%"
        height="500"
        @selection-change="handleAvailableSelectionChange"
      >
        <el-table-column type="selection" width="55" />
        <el-table-column label="题型" width="100">
          <template #default="scope">
            <el-tag :type="getQuestionTypeColor(scope.row.type)">
              {{ getQuestionTypeText(scope.row.type) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="题目内容" min-width="300">
          <template #default="scope">
            <div class="truncate-text" :title="scope.row.content">{{ scope.row.content }}</div>
          </template>
        </el-table-column>
        <el-table-column label="分值" width="80">
          <template #default="scope">
            <span>{{ scope.row.score }}</span>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="160">
          <template #default="scope">
            <span>{{ formatDateTime(scope.row.created_at) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80" align="center">
          <template #default="scope">
             <el-button
              type="danger"
              icon="Delete"
              circle
              size="small"
              @click.stop="deleteGlobalQuestion(scope.row)"
              title="从题库中彻底删除"
            />
          </template>
        </el-table-column>
      </el-table>

      <template #footer>
        <span class="dialog-footer">
          <el-button @click="showAddExistingDialog = false">取消</el-button>
          <el-button type="primary" @click="addSelectedQuestions" :disabled="selectedAvailableQuestions.length === 0">
            添加选中题目 ({{ selectedAvailableQuestions.length }})
          </el-button>
        </span>
      </template>
    </el-dialog>

    <!-- 题目导入对话框 -->
    <el-dialog
      v-model="showImportQuestionDialog"
      title="从文件导入题目"
      width="600px"
      :close-on-click-modal="false"
    >
      <div style="text-align: center; padding: 40px;">
        <el-upload
          class="upload-demo"
          drag
          action=""
          :auto-upload="false"
          :on-change="handleQuestionFileChange"
          :show-file-list="true"
          accept=".doc,.docx,.xlsx,.xls,.txt,.csv"
          style="margin-bottom: 20px;"
        >
          <el-icon class="el-icon--upload"><upload-filled /></el-icon>
          <div class="el-upload__text">
            将文件拖到此处，或<em>点击上传</em>
          </div>
          <template #tip>
            <div class="el-upload__tip">
              支持 Word (.doc, .docx)、Excel (.xlsx, .xls)、文本文件 (.txt, .csv)
            </div>
          </template>
        </el-upload>

        <div style="margin-top: 30px; text-align: left;">
          <h4>题目导入格式说明:</h4>
          <ul style="list-style: none; padding: 0; font-size: 13px; color: #666;">
            <li>• Word/文本: 题目间换行，字段用 @@@ 分隔</li>
            <li>• 格式: (序号)@@@题型@@@内容@@@分值@@@答案@@@规则</li>
            <li>• Excel: 每行一题，列顺序对应上述字段</li>
            <li>• 序号列可忽略，系统自动处理</li>
          </ul>
        </div>
      </div>

      <template #footer>
        <span class="dialog-footer">
          <el-button @click="showImportQuestionDialog = false">取消</el-button>
          <el-button type="primary" @click="importQuestionsFromFile" :disabled="!selectedQuestionFile">
            开始导入
          </el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick, watch, defineProps, defineEmits } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Upload, UploadFilled, Rank, Plus, DocumentCopy, Refresh, Delete, Search } from '@element-plus/icons-vue'
import axios from 'axios'

const props = defineProps({
  examId: {
    type: String,
    required: true
  }
})

const emit = defineEmits(['update:questions'])

const questions = ref([])
const availableQuestions = ref([])
const selectedExamQuestions = ref([])
const selectedAvailableQuestions = ref([])
const questionTableRef = ref(null)

// Dialogs
const showQuestionDialog = ref(false)
const showImportQuestionDialog = ref(false)
const showAddExistingDialog = ref(false)

// State
const isEditMode = ref(false)
const currentQuestion = ref({
  id: null,
  question_type: 'choice',
  question_title: '',
  reference_answer: '',
  scoring_rules: '',
  total_score: 4
})
const selectedQuestionFile = ref(null)
const searchKeyword = ref('')

// 获取题目列表
const fetchQuestions = async () => {
  try {
    const response = await axios.get(`/api/exams/${props.examId}/questions`)
    questions.value = (response.data.data || []).sort((a, b) => a.question_order - b.question_order)
    emit('update:questions', questions.value)
  } catch (error) {
    console.error('获取题目列表失败:', error)
  }
}

// 获取未分配的题目
const fetchAvailableQuestions = async () => {
  try {
    const params = {}
    if (searchKeyword.value) {
      params.search = searchKeyword.value
    }
    const response = await axios.get(`/api/exams/${props.examId}/available-questions`, { params })
    availableQuestions.value = response.data.data || []
  } catch (error) {
    console.error('获取可用题目失败:', error)
    ElMessage.error('获取可用题目失败')
  }
}

const searchAvailableQuestions = () => {
  fetchAvailableQuestions()
}

// 打开添加题目对话框
const openAddQuestionDialog = () => {
  isEditMode.value = false
  currentQuestion.value = {
    id: null,
    question_type: 'choice',
    question_title: '',
    reference_answer: '',
    scoring_rules: '',
    total_score: 4
  }
  showQuestionDialog.value = true
}

// 双击题目行打开编辑
const handleQuestionDblClick = (row) => {
  isEditMode.value = true
  
  currentQuestion.value = {
    id: row.id,
    question_type: row.type,
    question_title: row.content,
    reference_answer: row.reference_answer,
    scoring_rules: row.scoring_rules,
    total_score: row.score
  }
  showQuestionDialog.value = true
}

// 保存题目
const handleSaveQuestion = async () => {
  if (!currentQuestion.value.question_title) {
    ElMessage.error('题目内容不能为空')
    return
  }

  try {
    if (isEditMode.value) {
      await axios.put(`/api/questions/${currentQuestion.value.id}`, {
        question_type: currentQuestion.value.question_type,
        content: currentQuestion.value.question_title,
        score: currentQuestion.value.total_score,
        reference_answer: currentQuestion.value.reference_answer,
        scoring_rules: currentQuestion.value.scoring_rules
      })
      ElMessage.success('更新成功')
    } else {
      await axios.post(`/api/exams/${props.examId}/questions`, {
        // question_order is optional now, backend handles it
        question_type: currentQuestion.value.question_type,
        content: currentQuestion.value.question_title,
        score: currentQuestion.value.total_score,
        reference_answer: currentQuestion.value.reference_answer,
        scoring_rules: currentQuestion.value.scoring_rules
      })
      ElMessage.success('添加成功')
    }

    showQuestionDialog.value = false
    await fetchQuestions()
  } catch (error) {
    console.error('保存题目失败:', error)
    ElMessage.error('保存题目失败')
  }
}

// 批量移除题目
const removeBatchQuestions = async () => {
  if (selectedExamQuestions.value.length === 0) return

  try {
    const confirmed = await ElMessageBox.confirm(
      '移除确认',
      `确定要从本次考试中移除选中的 ${selectedExamQuestions.value.length} 道题目吗？`,
      {
        confirmButtonText: '确定移除',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )

    if (!confirmed) return

    const questionIds = selectedExamQuestions.value.map(q => q.id)
    const response = await axios.post(`/api/exams/${props.examId}/questions/remove-batch`, questionIds, {
      headers: { 'Content-Type': 'application/json' }
    })

    if (response.data.code === 1) {
      ElMessage.success(`成功移除 ${response.data.data.removed_count} 道题目`)
      selectedExamQuestions.value = []
      await fetchQuestions()
    } else {
      ElMessage.error(response.data.msg || '移除失败')
    }
  } catch (error) {
    if (error !== 'cancel') {
        console.error('批量移除题目失败:', error)
        ElMessage.error('批量移除题目失败')
    }
  }
}

// 添加选中的题目到考试
const addSelectedQuestions = async () => {
  if (selectedAvailableQuestions.value.length === 0) {
    ElMessage.warning('请选择要添加的题目')
    return
  }

  try {
    const questionIds = selectedAvailableQuestions.value.map(q => q.id)
    const response = await axios.post(`/api/exams/${props.examId}/add-existing-questions`, questionIds, {
      headers: { 'Content-Type': 'application/json' }
    })

    if (response.data.code === 1) {
      ElMessage.success(`成功添加 ${response.data.data.added_count} 道题目`)
      showAddExistingDialog.value = false
      selectedAvailableQuestions.value = []
      await fetchQuestions()
    } else {
      ElMessage.error(response.data.msg || '添加失败')
    }
  } catch (error) {
    console.error('添加题目失败:', error)
    ElMessage.error('添加题目失败')
  }
}

// 全局删除题目
const deleteGlobalQuestion = async (question) => {
  try {
    const confirmed = await ElMessageBox.confirm(
      '彻底删除确认',
      `确定要从题库中彻底删除该题目吗？\n内容: ${question.content.substring(0, 30)}...\n警告：此操作不可恢复！`,
      {
        confirmButtonText: '确定彻底删除',
        cancelButtonText: '取消',
        type: 'error',
        confirmButtonClass: 'el-button--danger'
      }
    )

    if (!confirmed) return

    const response = await axios.delete(`/api/questions/${question.id}`)

    if (response.data.code === 1) {
      ElMessage.success('删除成功')
      await fetchAvailableQuestions()
    } else {
      ElMessage.error(response.data.msg || '删除失败')
    }
  } catch (error) {
    if (error !== 'cancel') {
        console.error('删除题目失败:', error)
        ElMessage.error('删除题目失败')
    }
  }
}

// 题目文件选择
const handleQuestionFileChange = (file) => {
  selectedQuestionFile.value = file.raw
}

// 导入题目
const importQuestionsFromFile = async () => {
  if (!selectedQuestionFile.value) {
    ElMessage.error('请选择文件')
    return
  }

  const formData = new FormData()
  formData.append('file', selectedQuestionFile.value)

  try {
    ElMessage.info('正在导入题目，请稍候...')
    const response = await axios.post(`/api/exams/${props.examId}/import-questions`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })

    if (response.data.code === 1) {
      ElMessage.success(`题目导入成功！共导入 ${response.data.data.count} 道题目`)
      showImportQuestionDialog.value = false
      selectedQuestionFile.value = null
      await fetchQuestions()
    } else {
      ElMessage.error(response.data.msg || '题目导入失败')
    }
  } catch (error) {
    console.error('题目导入失败:', error)
    if (error.response && error.response.data && error.response.data.detail) {
      ElMessage.error(`导入失败: ${error.response.data.detail}`)
    } else {
      ElMessage.error('题目导入失败')
    }
  }
}

// Selection Handlers
const handleExamQuestionSelectionChange = (selection) => {
  selectedExamQuestions.value = selection
}

const handleAvailableSelectionChange = (selection) => {
  selectedAvailableQuestions.value = selection
}

// Reorder Logic
const reorderExamQuestions = async () => {
  try {
    const questionIds = questions.value.map(q => q.id)
    await axios.post(`/api/exams/${props.examId}/questions/reorder`, questionIds)
  } catch (error) {
    console.error('更新排序失败:', error)
    ElMessage.error('更新排序失败')
  }
}

// Helpers
const getQuestionTypeColor = (type) => {
  const typeMap = {
    choice: 'primary',   // 蓝色：清新
    fill_blank: 'success', // 绿色：柔和
    essay: 'warning',    // 奶橙色：温和表达
    calculation: 'danger', // 珊瑚红：紧张感
    true_false: 'info'   // 浅灰蓝：中性判断
  }
  return typeMap[type] || 'info'
}


const getQuestionTypeText = (type) => {
  const typeMap = {
    choice: '选择题',
    fill_blank: '填空题',
    essay: '简答题',
    calculation: '计算题',
    true_false: '判断题'
  }
  return typeMap[type] || '未知'
}

const formatDateTime = (dateStr) => {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleString()
}

// Drag and Drop
const ensureRowsDraggable = () => {
  if (!questionTableRef.value) return
  const trs = questionTableRef.value.$el.querySelectorAll('.el-table__body-wrapper tbody tr')
  trs.forEach(tr => {
    tr.setAttribute('draggable', 'true')
  })
}

const initDragAndDrop = () => {
  if (!questionTableRef.value) return

  const tbody = questionTableRef.value.$el.querySelector('.el-table__body-wrapper tbody')
  if (!tbody) return

  if (tbody.getAttribute('data-dnd-initialized')) return
  tbody.setAttribute('data-dnd-initialized', 'true')

  let draggingIndex = -1

  tbody.addEventListener('dragstart', (e) => {
    const tr = e.target.closest('tr')
    if (!tr) return
    
    draggingIndex = tr.sectionRowIndex
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('text/plain', draggingIndex)
    tr.classList.add('dragging')
  })

  tbody.addEventListener('dragend', (e) => {
    const tr = e.target.closest('tr')
    if (tr) tr.classList.remove('dragging')
    draggingIndex = -1
  })

  tbody.addEventListener('dragover', (e) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
  })

  tbody.addEventListener('dragenter', (e) => {
    const destTr = e.target.closest('tr')
    if (!destTr || draggingIndex === -1 || destTr.sectionRowIndex === draggingIndex) return
    
    const destIndex = destTr.sectionRowIndex
    
    const items = [...questions.value]
    const movedItem = items[draggingIndex]
    items.splice(draggingIndex, 1)
    items.splice(destIndex, 0, movedItem)
    questions.value = items
    
    draggingIndex = destIndex
  })

  tbody.addEventListener('drop', async (e) => {
    e.preventDefault()
    if (draggingIndex !== -1) {
      await reorderExamQuestions()
    }
  })
}

watch(questions, () => {
  nextTick(() => {
    ensureRowsDraggable()
    initDragAndDrop()
  })
}, { deep: true })

onMounted(async () => {
  await fetchQuestions()
  nextTick(() => {
    initDragAndDrop()
    ensureRowsDraggable()
  })
})
</script>

<style scoped>
.tab-actions {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
}
.truncate-text {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
}
:deep(.el-table__body tr.dragging) {
  opacity: 0.5;
  background: #f0f9eb;
}
.drag-handle {
  cursor: move;
  margin-left: 8px;
}
</style>