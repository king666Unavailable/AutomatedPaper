<template>
  <div class="exam-management-container">
    <header class="main-header">
      <div class="title">考试管理系统</div>
      <div class="user-info">
        <span>欢迎，教师</span>
        <button @click="logout">退出</button>
      </div>
    </header>

    <div class="main-content">
      <!-- 操作按钮区域 -->
      <div class="action-buttons">
        <button @click="showCreateExamDialog = true" class="action-btn create-exam-btn">
           创建考试
        </button>
      </div>

      <!-- 考试列表区域 -->
      <div class="exam-list-section">
        <h2>考试列表</h2>
        <div v-if="exams.length === 0" class="no-exams">
          <p>暂无考试数据</p>
          <p class="hint">请创建新考试开始使用系统</p>
        </div>
        <div v-else class="exam-grid">
          <div
            v-for="exam in exams"
            :key="exam.exam_id"
            class="exam-card"
          >
            <!-- 第一排：考试名称 -->
            <div class="exam-row">
              <h3 class="exam-title">{{ exam.exam_name }}</h3>
            </div>

            <!-- 第二排：备注 -->
            <div class="exam-row">
              <div class="exam-description">
                {{ exam.description || '暂无备注' }}
              </div>
            </div>

            <!-- 第三排：开考时间 -->
            <div class="exam-row">
              <div class="exam-time-info" :class="getExamTimeClass(exam.exam_date)">
                开考时间: {{ calculateExamTime(exam.exam_date).text || calculateExamTime(exam.exam_date) }}
              </div>
            </div>

            <!-- 第四排：操作按钮 -->
            <div class="exam-row">
              <div class="exam-actions">
                <button @click="manageGrades(exam)" class="exam-action-btn grades-btn">
                  管理
                </button>
                <button @click="editExam(exam)" class="exam-action-btn edit-btn">
                  信息编辑
                </button>
                <button @click="confirmDeleteExam(exam)" class="exam-action-btn delete-btn">
                  删除
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 弹窗：创建/编辑考试 -->
    <div v-if="showCreateExamDialog" class="upload-dialog">
      <div class="dialog-content">
        <h3>{{ isEditMode ? '编辑考试' : '创建考试' }}</h3>
        <label>考试名称：</label>
        <input v-model="examForm.exam_name" placeholder="请输入考试名称" />
        <label>备注：</label>
        <textarea v-model="examForm.description" placeholder="请输入考试备注（可选）" rows="3"></textarea>
        <label>开考时间：</label>
        <div class="datetime-input-wrapper">
          <input
            v-model="examForm.exam_date"
            type="datetime-local"
            :class="{ 'has-value': examForm.exam_date }"
          />
        </div>
        <div class="dialog-actions">
          <button @click="saveExam" :disabled="!examForm.exam_name" class="primary-btn">
            {{ isEditMode ? '保存' : '创建' }}
          </button>
          <button @click="closeCreateExamDialog" class="secondary-btn">取消</button>
        </div>
        <div v-if="examSaving" class="saving-message">
          {{ isEditMode ? '保存中...' : '创建中...' }}
        </div>
        <div v-if="examMsg" :class="['message', examMsg.includes('成功') ? 'success' : 'error']">
          {{ examMsg }}
        </div>
      </div>
    </div>

    <!-- 删除确认弹窗 -->
    <div v-if="showDeleteConfirm" class="upload-dialog">
      <div class="dialog-content delete-dialog">
        <h3>⚠️ 确认删除</h3>
        <div class="delete-warning">
          <p>您确定要删除考试 <strong>"{{ examToDelete?.exam_name }}"</strong> 吗？</p>
          <p class="warning-text">删除后将无法恢复，相关的试卷和成绩数据也会被永久删除。</p>
        </div>
        <div class="dialog-actions">
          <button @click="deleteExam" class="danger-btn">确认删除</button>
          <button @click="closeDeleteConfirm" class="secondary-btn">取消</button>
        </div>
      </div>
    </div>

    <!-- 成绩管理弹窗（暂时留空） -->
    <div v-if="showGradesDialog" class="upload-dialog">
      <div class="dialog-content">
        <h3>📊 成绩管理</h3>
        <div class="grades-placeholder">
          <p>🚧 成绩管理功能开发中...</p>
          <p>敬请期待后续功能更新！</p>
        </div>
        <div class="dialog-actions">
          <button @click="closeGradesDialog" class="secondary-btn">关闭</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import axios from 'axios'

const router = useRouter()
const exams = ref([])

// 考试创建/编辑相关
const showCreateExamDialog = ref(false)
const isEditMode = ref(false)
const examSaving = ref(false)
const examMsg = ref('')
const examForm = ref({
  exam_id: null,
  exam_name: '',
  description: '',
  exam_date: '',
  status: 'created'
})

// 删除确认相关
const showDeleteConfirm = ref(false)
const examToDelete = ref(null)
const deletingExam = ref(false)
const deleteMsg = ref('')

// 成绩管理相关
const showGradesDialog = ref(false)
const selectedExam = ref(null)

// 格式化日期
const formatDate = (dateString) => {
  if (!dateString) return ''
  const date = new Date(dateString)
  return date.toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit'
  })
}

// 计算考试时间显示
const calculateExamTime = (examDateTime) => {
  if (!examDateTime) return '未设置开考时间'

  const examDate = new Date(examDateTime)
  const now = new Date()

  // 比较是否是同一天
  const isSameDay = examDate.toDateString() === now.toDateString()
  const isExamPassed = examDate.getTime() < now.getTime()

  const diffTime = examDate.getTime() - now.getTime()
  const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24))

  const formattedDate = examDate.toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit'
  })

  const formattedTime = examDate.toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit'
  })

  // 如果考试时间已过
  if (isExamPassed) {
    return {
      text: `${formattedDate} ${formattedTime} (已考完)`,
      status: 'finished'
    }
  }
  // 如果是同一天且未过时
  else if (isSameDay) {
    return {
      text: `${formattedDate} ${formattedTime} (今天开考)`,
      status: 'today'
    }
  }
  // 如果是明天
  else if (diffDays === 1) {
    return {
      text: `${formattedDate} ${formattedTime} (明天开考)`,
      status: 'tomorrow'
    }
  }
  // 其他未来天数
  else {
    return {
      text: `${formattedDate} ${formattedTime} (距离${diffDays}天)`,
      status: 'upcoming'
    }
  }
}

// 获取考试时间的CSS类名
const getExamTimeClass = (examDateTime) => {
  if (!examDateTime) return ''

  const examDate = new Date(examDateTime)
  const now = new Date()

  // 比较是否是同一天
  const isSameDay = examDate.toDateString() === now.toDateString()
  const isExamPassed = examDate.getTime() < now.getTime()
  const diffTime = examDate.getTime() - now.getTime()
  const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24))

  // 如果考试时间已过
  if (isExamPassed) {
    return 'time-finished'
  }
  // 如果是同一天且未过时
  else if (isSameDay) {
    return 'time-today'
  }
  // 如果是明天
  else if (diffDays === 1) {
    return 'time-tomorrow'
  }
  // 其他未来天数
  else {
    return 'time-upcoming'
  }
}

// 获取状态文本
const getStatusText = (status) => {
  const statusMap = {
    'created': '已创建',
    'active': '进行中',
    'completed': '已完成'
  }
  return statusMap[status] || '已创建'
}

// 成绩管理函数
const manageGrades = (exam) => {
  // 跳转到考试详情页面（成绩管理标签页）
  router.push(`/exam/${exam.exam_id}`)
}

const closeGradesDialog = () => {
  showGradesDialog.value = false
}

// 确认删除考试
const confirmDeleteExam = (exam) => {
  examToDelete.value = exam
  showDeleteConfirm.value = true
  deleteMsg.value = ''
}

const closeDeleteConfirm = () => {
  showDeleteConfirm.value = false
  examToDelete.value = null
  deleteMsg.value = ''
}

const deleteExam = async () => {
  if (!examToDelete.value) return

  try {
    const response = await axios.delete(`/api/exams/${examToDelete.value.exam_id}`)

    if (response.data.code === 1) {
      // 删除成功，移除本地数组中的考试
      const index = exams.value.findIndex(exam => exam.exam_id === examToDelete.value.exam_id)
      if (index > -1) {
        exams.value.splice(index, 1)
      }

      // 如果删除的是当前选中的考试，清除选中状态
      if (selectedExam.value && selectedExam.value.exam_id === examToDelete.value.exam_id) {
        selectedExam.value = null
        showGradesDialog.value = false
      }

      alert('考试删除成功！')
    } else {
      alert('删除失败：' + (response.data.message || '未知错误'))
    }
  } catch (error) {
    console.error('删除考试失败:', error)
    alert('删除失败，请检查网络连接')
  } finally {
    closeDeleteConfirm()
  }
}

// 编辑考试
const editExam = (exam) => {
  isEditMode.value = true
  // 正确处理日期格式，确保datetime-local输入能正确显示
  let formattedDate = ''
  if (exam.exam_date) {
    const date = new Date(exam.exam_date)
    // 转换为datetime-local格式: YYYY-MM-DDTHH:MM
    // 需要调整时区，避免显示错误的时间
    const year = date.getFullYear()
    const month = String(date.getMonth() + 1).padStart(2, '0')
    const day = String(date.getDate()).padStart(2, '0')
    const hours = String(date.getHours()).padStart(2, '0')
    const minutes = String(date.getMinutes()).padStart(2, '0')
    formattedDate = `${year}-${month}-${day}T${hours}:${minutes}`
  }

  examForm.value = {
    exam_id: exam.exam_id,
    exam_name: exam.exam_name,
    description: exam.description || '',
    exam_date: formattedDate,
    status: 'created'  // 固定状态，用户不可编辑
  }
  showCreateExamDialog.value = true
}

// 保存考试（创建或更新）
const saveExam = async () => {
  if (!examForm.value.exam_name.trim()) {
    examMsg.value = '请输入考试名称'
    return
  }

  examSaving.value = true
  examMsg.value = ''

  try {
    let response

    if (isEditMode.value) {
      // 更新考试
      response = await axios.put(`/api/exams/${examForm.value.exam_id}`, {
        exam_name: examForm.value.exam_name,
        description: examForm.value.description,
        exam_date: examForm.value.exam_date,
        status: 'created'  // 保持状态为已创建
      })
    } else {
      // 创建新考试
      response = await axios.post('/api/exams', {
        exam_name: examForm.value.exam_name,
        description: examForm.value.description,
        exam_date: examForm.value.exam_date,
        status: 'created'  // 新考试默认为已创建状态
      })
    }

    if (response.data.code === 1) {
      examMsg.value = isEditMode.value ? '考试更新成功！' : '考试创建成功！'

      // 延迟关闭弹窗并重新加载列表（无论是创建还是编辑都重新加载）
      setTimeout(() => {
        closeCreateExamDialog()
        loadExams()  // 直接重新加载考试列表，确保显示最新的数据库数据
      }, 1000)
    } else {
      examMsg.value = response.data.msg || (isEditMode.value ? '更新失败' : '创建失败')
      examSaving.value = false
    }
  } catch (e) {
    console.error('保存考试失败', e)
    examMsg.value = isEditMode.value ? '更新失败，请重试' : '创建失败，请重试'
    examSaving.value = false
  }
}

// 关闭创建/编辑考试弹窗
const closeCreateExamDialog = () => {
  showCreateExamDialog.value = false
  isEditMode.value = false
  examSaving.value = false
  examMsg.value = ''
  examForm.value = {
    exam_id: null,
    exam_name: '',
    description: '',
    exam_date: '',
    status: 'created'
  }
}

const logout = () => {
  localStorage.removeItem('username')
  router.push('/login')
}

const loadExams = async () => {
  try {
    const res = await axios.get('/api/exams')
    exams.value = res.data.data || []
  } catch (e) {
    console.error('获取考试列表失败', e)
  }
}

onMounted(async () => {
  if (!localStorage.getItem('username')) {
    router.push('/login')
    return
  }

  await loadExams()
})
</script>

<style>
/* 去掉body和html的默认背景 */
body, html {
  margin: 0;
  padding: 0;
  background: transparent !important;
  background-color: transparent !important;
}

* {
  box-sizing: border-box;
}
</style>

<style scoped>
.exam-management-container {
  min-height: 100vh;
  width: 100vw;
  background: transparent;
  position: relative;
}


.main-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: rgba(35, 57, 93, 0.9);
  color: #fff;
  padding: 0 32px;
  height: 56px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
}

.title {
  font-size: 1.8rem;
  font-weight: bold;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 16px;
}

.user-info button {
  background: #f39c12;
  color: #fff;
  border: none;
  padding: 6px 16px;
  border-radius: 4px;
  cursor: pointer;
}

.main-content {
  padding: 32px;
  height: calc(100vh - 56px);
  overflow-y: auto;
}

.action-buttons {
  display: flex;
  gap: 20px;
  margin-bottom: 32px;
  justify-content: center;
}

.action-btn {
  padding: 12px 24px;
  border: none;
  border-radius: 8px;
  font-size: 1.1rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.create-exam-btn {
  background: #3b82f6;
  color: white;
}

.create-exam-btn:hover {
  background: #2563eb;
  transform: translateY(-2px);
}

.exam-list-section {
  padding: 24px;
}

.exam-list-section h2 {
  text-align: center;
  margin-bottom: 24px;
  color: #4a5568;
  font-size: 1.8rem;
  font-weight: 600;
}

.no-exams {
  text-align: center;
  padding: 60px 20px;
  color: #6b7280;
}

.no-exams p {
  font-size: 1.2rem;
  margin-bottom: 8px;
}

.hint {
  font-size: 1rem;
  color: #9ca3af;
  font-style: italic;
}

.exam-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 20px;
}

.exam-card {
  background: rgba(35, 57, 93, 0.95);
  border-radius: 12px;
  padding: 20px;
  box-shadow: 0 4px 15px rgba(35, 57, 93, 0.3);
  transition: all 0.2s;
  border: 2px solid rgba(255, 255, 255, 0.1);
  color: white;
}

.exam-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 25px rgba(35, 57, 93, 0.5);
  border-color: rgba(255, 255, 255, 0.3);
  background: rgba(35, 57, 93, 1);
}

/* 考试卡片行布局 */
.exam-row {
  margin-bottom: 12px;
  display: flex;
  align-items: center;
}

.exam-row:last-child {
  margin-bottom: 0;
}

/* 第一排：考试名称 */
.exam-row:first-child .exam-title {
  font-size: 1.3rem;
  font-weight: 600;
  color: white;
  margin: 0;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
}

/* 第二排：备注 */
.exam-description {
  color: #fbbf24;
  font-size: 0.9rem;
  line-height: 1.4;
  flex: 1;
  font-style: italic;
  font-weight: 500;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.4);
}

/* 第三排：开考时间 */
.exam-time-info {
  font-size: 0.9rem;
  font-weight: 500;
}

.exam-time-info.time-finished {
  color: #f87171; /* 柔和的珊瑚红 - 已考完 */
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.4);
  font-style: italic;
  opacity: 0.9;
}

.exam-time-info.time-today {
  color: #f59e0b; /* 橙色 - 今天开考 */
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.4);
  font-weight: 600;
}

.exam-time-info.time-tomorrow {
  color: #10b981; /* 绿色 - 明天开考 */
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.4);
}

.exam-time-info.time-upcoming {
  color: rgba(255, 255, 255, 0.85); /* 白色 - 未来考试 */
}

/* 第四排：操作按钮 */
.exam-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-start;
  width: 100%;
}

.exam-action-btn {
  padding: 6px 12px;
  border: none;
  border-radius: 6px;
  font-size: 0.8rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
}

.exam-action-btn.grades-btn {
  background: linear-gradient(135deg, #3b82f6, #2563eb);
  color: white;
}

.exam-action-btn.grades-btn:hover {
  background: linear-gradient(135deg, #2563eb, #1d4ed8);
  transform: translateY(-1px);
}

.exam-action-btn.edit-btn {
  background: linear-gradient(135deg, #f59e0b, #d97706);
  color: white;
}

.exam-action-btn.edit-btn:hover {
  background: linear-gradient(135deg, #d97706, #b45309);
  transform: translateY(-1px);
}

.exam-action-btn.delete-btn {
  background: linear-gradient(135deg, #f56565, #e53e3e);
  color: white;
}

.exam-action-btn.delete-btn:hover {
  background: linear-gradient(135deg, #e53e3e, #c53030);
  transform: translateY(-1px);
}

.exam-header {
  margin-bottom: 16px;
}

.exam-title {
  font-size: 1.3rem;
  font-weight: 600;
  color: #374151;
  margin-bottom: 8px;
}

.exam-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.exam-status {
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 0.8rem;
  font-weight: 500;
}

.status-created {
  background: #e5e7eb;
  color: #374151;
}

.status-active {
  background: #dcfce7;
  color: #166534;
}

.status-completed {
  background: #dbeafe;
  color: #1e40af;
}

.exam-date {
  font-size: 0.9rem;
  color: #6b7280;
}


.exam-actions {
  display: flex;
  gap: 8px;
}

.exam-action-btn {
  flex: 1;
  padding: 8px 12px;
  border: none;
  border-radius: 6px;
  font-size: 0.85rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
}

.grades-btn {
  background: #10b981;
  color: white;
}

.grades-btn:hover {
  background: #059669;
}

.edit-btn {
  background: #f59e0b;
  color: white;
}

.edit-btn:hover {
  background: #d97706;
}

.delete-btn {
  background: #ef4444;
  color: white;
}

.delete-btn:hover {
  background: #dc2626;
}

.upload-dialog {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.dialog-content {
  background: rgba(255, 255, 255, 0.95);
  padding: 32px 24px;
  border-radius: 8px;
  min-width: 320px;
  max-width: 90vw;
  max-height: 90vh;
  overflow-y: auto;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.25);
}

.dialog-content h3 {
  margin-top: 0;
  margin-bottom: 16px;
  color: #374151;
}

.dialog-content label {
  display: block;
  margin: 8px 0 4px 0;
  font-weight: 500;
  color: #374151;
}

.dialog-content input,
.dialog-content textarea,
.dialog-content select {
  width: 100%;
  padding: 8px 12px;
  margin-bottom: 16px;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  font-size: 0.9rem;
  box-sizing: border-box;
}

.dialog-content textarea {
  resize: vertical;
  min-height: 80px;
}

.dialog-content select {
  background: white;
  cursor: pointer;
}

.dialog-actions {
  margin-top: 20px;
  display: flex;
  gap: 12px;
}

.dialog-actions button {
  flex: 1;
  padding: 10px 16px;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-weight: 500;
  transition: all 0.2s;
}

.primary-btn {
  background: #3b82f6;
  color: white;
}

.primary-btn:hover:not(:disabled) {
  background: #2563eb;
}

.primary-btn:disabled {
  background: #9ca3af;
  cursor: not-allowed;
}

.secondary-btn {
  background: #e5e7eb;
  color: #374151;
}

.secondary-btn:hover {
  background: #d1d5db;
}

.danger-btn {
  background: #ef4444;
  color: white;
}

.danger-btn:hover {
  background: #dc2626;
}

.saving-message {
  margin-top: 12px;
  text-align: center;
  color: #3b82f6;
  font-weight: 500;
}

.time-hint {
  margin-top: 4px;
  font-size: 0.85rem;
  color: #9ca3af;
  font-style: italic;
}

/* datetime-local输入框样式 */
.datetime-input-wrapper {
  position: relative;
}

input[type="datetime-local"] {
  width: 100%;
  padding: 8px 12px;
  margin-bottom: 16px;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  font-size: 0.9rem;
  box-sizing: border-box;
  background: white;
  color: #374151;
}

/* 当没有值时显示自定义占位符 */
input[type="datetime-local"]:not(.has-value):before {
  content: "请选择开考时间";
  color: #9ca3af;
  font-style: italic;
  position: absolute;
  left: 12px;
  top: 50%;
  transform: translateY(-50%);
  pointer-events: none;
}

input[type="datetime-local"]:not(.has-value) {
  color: transparent;
}

input[type="datetime-local"].has-value {
  color: #374151;
}

.message {
  margin-top: 12px;
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 0.9rem;
}

.message.success {
  background: #dcfce7;
  color: #166534;
}

.message.error {
  background: #fee2e2;
  color: #b91c1c;
}

.delete-dialog {
  max-width: 400px;
}

.delete-warning {
  margin-bottom: 20px;
}

.delete-warning p {
  margin-bottom: 8px;
  color: #374151;
}

.warning-text {
  color: #ef4444 !important;
  font-size: 0.9rem;
}

.grades-placeholder {
  text-align: center;
  padding: 40px 20px;
  color: #6b7280;
}

.grades-placeholder p {
  margin-bottom: 8px;
  font-size: 1.1rem;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .main-content {
    padding: 16px;
  }

  .action-buttons {
    flex-direction: column;
  }

  .action-btn {
    width: 100%;
  }

  .exam-grid {
    grid-template-columns: 1fr;
  }

  .exam-actions {
    flex-direction: column;
  }

  .exam-action-btn {
    width: 100%;
  }

  .dialog-content {
    margin: 10px;
    padding: 20px 16px;
    min-width: auto;
  }
}
</style>