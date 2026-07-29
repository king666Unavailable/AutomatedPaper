<template>
  <div class="home-container">
    <div class="header">
      <h1>考试管理平台</h1>
      <p>试卷图片分析和AI阅卷实验平台</p>
    </div>

    <div class="actions">
      <el-button type="primary" size="large" @click="showCreateDialog = true">
        <el-icon><Plus /></el-icon>
        创建考试
      </el-button>
    </div>

    <div class="exam-list">
      <el-card v-if="exams.length === 0" class="empty-card">
        <el-empty description="暂无考试，请创建新考试" />
      </el-card>

      <el-card v-for="exam in exams" :key="exam.exam_id" class="exam-card" shadow="hover">
        <template #header>
          <div class="card-header">
            <span class="exam-title">{{ exam.exam_name }}</span>
            <div class="card-actions">
              <el-button size="small" @click="goToExamDetail(exam.exam_id)">
                管理考试
              </el-button>
              <el-button size="small" type="success" @click="triggerAIGrading(exam.exam_id)">
                AI阅卷
              </el-button>
              <el-dropdown>
                <el-button size="small" type="text">
                  更多
                  <el-icon><ArrowDown /></el-icon>
                </el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item @click="editExam(exam)">编辑</el-dropdown-item>
                    <el-dropdown-item @click="deleteExam(exam.exam_id)" divided>删除</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
          </div>
        </template>

        <div class="exam-info">
          <p class="description">{{ exam.description || '暂无描述' }}</p>
          <div class="stats">
            <div class="stat-item">
              <el-icon><User /></el-icon>
              <span>{{ exam.student_count || 0 }} 名学生</span>
            </div>
            <div class="stat-item">
              <el-icon><Document /></el-icon>
              <span>{{ exam.total_questions || 0 }} 道题目</span>
            </div>
            <div class="stat-item">
              <el-icon><Star /></el-icon>
              <span>总分 {{ exam.total_score || 100 }} 分</span>
            </div>
          </div>
          <div class="status">
            <el-tag :type="getStatusType(exam.status)">
              {{ getStatusText(exam.status) }}
            </el-tag>
            <span class="create-time">
              创建于 {{ formatDate(exam.created_at) }}
            </span>
          </div>
        </div>
      </el-card>
    </div>

    <!-- 创建考试对话框 -->
    <el-dialog v-model="showCreateDialog" title="创建考试" width="500px">
      <el-form :model="newExam" label-width="80px">
        <el-form-item label="考试名称" required>
          <el-input v-model="newExam.exam_name" placeholder="请输入考试名称" />
        </el-form-item>
        <el-form-item label="考试描述">
          <el-input
            v-model="newExam.description"
            type="textarea"
            :rows="3"
            placeholder="请输入考试描述"
          />
        </el-form-item>
        <el-form-item label="题目数量">
          <el-input-number v-model="newExam.total_questions" :min="0" />
        </el-form-item>
        <el-form-item label="总分">
          <el-input-number v-model="newExam.total_score" :min="1" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" @click="createExam">创建</el-button>
      </template>
    </el-dialog>

    <!-- 编辑考试对话框 -->
    <el-dialog v-model="showEditDialog" title="编辑考试" width="500px">
      <el-form :model="editingExam" label-width="80px">
        <el-form-item label="考试名称" required>
          <el-input v-model="editingExam.exam_name" placeholder="请输入考试名称" />
        </el-form-item>
        <el-form-item label="考试描述">
          <el-input
            v-model="editingExam.description"
            type="textarea"
            :rows="3"
            placeholder="请输入考试描述"
          />
        </el-form-item>
        <el-form-item label="题目数量">
          <el-input-number v-model="editingExam.total_questions" :min="0" />
        </el-form-item>
        <el-form-item label="总分">
          <el-input-number v-model="editingExam.total_score" :min="1" />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="editingExam.status" placeholder="选择状态">
            <el-option label="已创建" value="created" />
            <el-option label="上传中" value="uploading" />
            <el-option label="处理中" value="processing" />
            <el-option label="已完成" value="completed" />
            <el-option label="已阅卷" value="graded" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEditDialog = false">取消</el-button>
        <el-button type="primary" @click="updateExam">更新</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, ArrowDown, User, Document, Star } from '@element-plus/icons-vue'
import axios from 'axios'

const router = useRouter()
const exams = ref([])
const showCreateDialog = ref(false)
const showEditDialog = ref(false)
const newExam = ref({
  exam_name: '',
  description: '',
  total_questions: 0,
  total_score: 100
})
const editingExam = ref({})

// 获取考试列表
const fetchExams = async () => {
  try {
    const response = await axios.get('/api/exams')
    exams.value = response.data.data || []
  } catch (error) {
    console.error('获取考试列表失败:', error)
    ElMessage.error('获取考试列表失败')
  }
}

// 创建考试
const createExam = async () => {
  try {
    const response = await axios.post('/api/exams', newExam.value)
    if (response.data.code === 1) {
      ElMessage.success('创建成功')
      showCreateDialog.value = false
      newExam.value = { exam_name: '', description: '', total_questions: 0, total_score: 100 }
      await fetchExams()
    } else {
      ElMessage.error(response.data.msg || '创建失败')
    }
  } catch (error) {
    console.error('创建考试失败:', error)
    ElMessage.error('创建考试失败')
  }
}

// 编辑考试
const editExam = (exam) => {
  editingExam.value = { ...exam }
  showEditDialog.value = true
}

// 更新考试
const updateExam = async () => {
  try {
    const response = await axios.put(`/api/exams/${editingExam.value.exam_id}`, editingExam.value)
    if (response.data.code === 1) {
      ElMessage.success('更新成功')
      showEditDialog.value = false
      await fetchExams()
    } else {
      ElMessage.error(response.data.msg || '更新失败')
    }
  } catch (error) {
    console.error('更新考试失败:', error)
    ElMessage.error('更新考试失败')
  }
}

// 删除考试
const deleteExam = async (examId) => {
  try {
    await ElMessageBox.confirm('确定要删除这个考试吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })

    const response = await axios.delete(`/api/exams/${examId}`)
    if (response.data.code === 1) {
      ElMessage.success('删除成功')
      await fetchExams()
    } else {
      ElMessage.error(response.data.msg || '删除失败')
    }
  } catch (error) {
    if (error !== 'cancel') {
      console.error('删除考试失败:', error)
      ElMessage.error('删除考试失败')
    }
  }
}

// 触发AI阅卷
const triggerAIGrading = async (examId) => {
  try {
    await ElMessageBox.confirm('确定要开始AI阅卷吗？这将模拟AI阅卷过程。', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'info'
    })

    ElMessage.info('正在启动AI阅卷...')
    const response = await axios.post(`/api/exams/${examId}/grade`)

    if (response.data.code === 1) {
      ElMessage.success(`AI阅卷完成！处理了 ${response.data.data.graded_count} 个学生`)
      await fetchExams()
    } else {
      ElMessage.error(response.data.msg || 'AI阅卷失败')
    }
  } catch (error) {
    if (error !== 'cancel') {
      console.error('AI阅卷失败:', error)
      ElMessage.error('AI阅卷失败')
    }
  }
}

// 跳转到考试详情
const goToExamDetail = (examId) => {
  router.push(`/exam/${examId}`)
}

// 获取状态类型
const getStatusType = (status) => {
  const statusMap = {
    created: '',
    uploading: 'warning',
    processing: 'warning',
    completed: 'success',
    graded: 'success'
  }
  return statusMap[status] || ''
}

// 获取状态文本
const getStatusText = (status) => {
  const statusMap = {
    created: '已创建',
    uploading: '上传中',
    processing: '处理中',
    completed: '已完成',
    graded: '已阅卷'
  }
  return statusMap[status] || '未知'
}

// 格式化日期
const formatDate = (dateStr) => {
  if (!dateStr) return ''
  return new Date(dateStr).toLocaleString('zh-CN')
}

onMounted(() => {
  fetchExams()
})
</script>

<style scoped>
.home-container {
  padding: 24px;
  background: #f5f7fa;
  min-height: 100vh;
}

.header {
  text-align: center;
  margin-bottom: 32px;
}

.header h1 {
  color: #2c3e50;
  margin-bottom: 8px;
  font-size: 2.5rem;
}

.header p {
  color: #7f8c8d;
  font-size: 1.1rem;
}

.actions {
  text-align: center;
  margin-bottom: 32px;
}

.exam-list {
  max-width: 1200px;
  margin: 0 auto;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(400px, 1fr));
  gap: 24px;
}

.exam-card {
  transition: transform 0.2s;
}

.exam-card:hover {
  transform: translateY(-2px);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.exam-title {
  font-size: 1.2rem;
  font-weight: bold;
  color: #2c3e50;
}

.card-actions {
  display: flex;
  gap: 8px;
}

.exam-info {
  color: #606266;
}

.description {
  margin-bottom: 16px;
  min-height: 40px;
}

.stats {
  display: flex;
  gap: 24px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.stat-item {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 0.9rem;
}

.status {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.create-time {
  font-size: 0.85rem;
  color: #909399;
}

.empty-card {
  grid-column: 1 / -1;
  text-align: center;
}
</style>