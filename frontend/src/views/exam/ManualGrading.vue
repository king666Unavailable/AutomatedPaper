<template>
  <div class="manual-grading-container">
    <!-- 顶部题号列表 -->
    <div class="question-tabs">
      <div
        v-for="(q, index) in questions"
        :key="q.id"
        class="question-tab"
        :class="{ active: currentQuestionIndex === index }"
        @click="selectQuestion(index)"
      >
        第{{ q.question_order }}题
      </div>
      <div v-if="!questions.length" class="empty-tip">暂无问答题</div>
    </div>

    <div v-if="questions.length" class="main-layout">
      <!-- 左侧学生列表 -->
      <div class="student-sidebar">
        <div class="sidebar-header">
          <span>学生列表</span>
          <span class="review-progress">{{ reviewedCount }} / {{ students.length }}</span>
        </div>
        <div class="student-list">
          <div
            v-for="(s, index) in students"
            :key="s.student_id"
            class="student-item"
            :class="{ active: currentStudentIndex === index, reviewed: s.manual_reviewed }"
            @click="selectStudent(index)"
          >
            <el-avatar
              :size="32"
              :class="['student-avatar', s.manual_reviewed ? 'reviewed' : 'unreviewed']"
            >
              {{ s.name.charAt(0) }}
            </el-avatar>
            <div class="student-info">
              <div class="student-name">{{ s.name }}</div>
              <div class="student-number">{{ s.student_number || '无学号' }}</div>
            </div>
            <el-tag v-if="s.score !== null" size="small" type="success">{{ s.score }}分</el-tag>
            <el-tag v-else size="small" type="info">未评</el-tag>
          </div>
        </div>
      </div>

      <!-- 右侧答题详情 -->
      <div class="detail-panel">
        <div v-if="currentStudent" class="detail-content">
          <div class="detail-header">
            <div class="student-title">
              <h3>{{ currentStudent.name }} - 第{{ currentQuestion.question_order }}题</h3>
              <span class="student-meta">{{ currentStudent.student_number }} · {{ currentStudent.class || '无班级' }}</span>
            </div>
            <div class="nav-actions">
              <el-button
                size="small"
                :disabled="currentStudentIndex === 0"
                @click="prevStudent"
              >上一学生</el-button>
              <el-button
                size="small"
                :disabled="currentStudentIndex === students.length - 1"
                @click="nextStudent"
              >下一学生</el-button>
            </div>
          </div>

          <div class="detail-body">
            <div class="detail-info">
              <el-descriptions :column="1" border size="small">
                <el-descriptions-item label="题目内容">
                  <div class="description-content">{{ currentQuestion.content || '（无题目内容）' }}</div>
                </el-descriptions-item>
                <el-descriptions-item label="参考答案">
                  <div class="description-content">{{ currentQuestion.reference_answer || '（无参考答案）' }}</div>
                </el-descriptions-item>
                <el-descriptions-item label="评分标准">
                  <div class="description-content">{{ currentQuestion.scoring_rules || '（无评分标准）' }}</div>
                </el-descriptions-item>
                <el-descriptions-item label="满分">
                  {{ currentQuestion.max_score || 0 }}
                </el-descriptions-item>
                <el-descriptions-item label="学生答案">
                  <div style="display: flex; gap: 16px;">
                    <div style="flex: 1; min-width: 0;">
                      <div style="color: #909399; font-size: 0.85rem; margin-bottom: 4px;">自动识别结果</div>
                      <div class="description-content">{{ currentStudent.student_answer || '（未识别）' }}</div>
                    </div>
                    <div style="flex: 1; min-width: 0;">
                      <div style="color: #909399; font-size: 0.85rem; margin-bottom: 4px;">修正答案</div>
                      <el-input
                        v-model="currentCorrectedAnswer"
                        type="textarea"
                        :rows="2"
                        placeholder="若自动识别有误，可在此填写修正后的答案"
                        size="small"
                        :disabled="saving"
                      />
                    </div>
                  </div>
                </el-descriptions-item>
                <el-descriptions-item label="识别结果人工标注">
                  <div style="display: flex; align-items: center; gap: 10px;">
                    <el-select v-model="currentRecognitionCorrect" size="small" style="width: 100px;" :disabled="saving">
                      <el-option label="正确" :value="true" />
                      <el-option label="错误" :value="false" />
                    </el-select>
                  </div>
                </el-descriptions-item>
                <el-descriptions-item label="当前得分">
                  <div style="display: flex; align-items: center; gap: 10px;">
                    <el-input-number
                      v-model="currentScore"
                      :min="0"
                      :max="currentQuestion.max_score || 100"
                      size="small"
                      controls-position="right"
                      :disabled="saving"
                    />
                    <el-button type="primary" size="small" :loading="saving" @click="saveCurrent">保存</el-button>
                  </div>
                </el-descriptions-item>
                <el-descriptions-item label="查看状态">
                  <el-tag :type="currentStudent.manual_reviewed ? 'success' : 'info'">
                    {{ currentStudent.manual_reviewed ? '已查看' : '未查看' }}
                  </el-tag>
                </el-descriptions-item>
              </el-descriptions>
            </div>

            <!-- 原始答题卡图片 -->
            <div class="detail-images">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                <h4 style="margin: 0;">原始答题卡</h4>
                <span style="color: #6b7280; font-size: 0.85rem;">可以手动切换答题卡页面</span>
              </div>
              <div v-if="currentImages && currentImages.length" class="image-wrapper">
                <div style="display: flex; justify-content: center; align-items: center; gap: 12px; margin-bottom: 10px;">
                  <el-button
                    size="small"
                    :disabled="currentImageIndex === 0"
                    @click="currentImageIndex--"
                  >上一页</el-button>
                  <span>第 {{ currentImageIndex + 1 }} / {{ currentImages.length }} 页</span>
                  <el-button
                    size="small"
                    :disabled="currentImageIndex === currentImages.length - 1"
                    @click="currentImageIndex++"
                  >下一页</el-button>
                </div>
                <el-image
                  :src="getOriginalImageUrl(currentImages[currentImageIndex])"
                  fit="contain"
                  style="width: 100%; height: 100%; border: 1px solid #ddd; cursor: pointer;"
                  :preview-src-list="[getOriginalImageUrl(currentImages[currentImageIndex])]"
                />
              </div>
              <div v-else>暂无答题卡图片</div>
            </div>
          </div>
        </div>
        <div v-else class="empty-detail">
          请选择学生
        </div>
      </div>
    </div>
    <div v-else class="empty-main">
      该考试暂无问答题
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import axios from 'axios'

const props = defineProps({
  examId: { type: [String, Number], required: true }
})

const questions = ref([])
const students = ref([])
const currentQuestionIndex = ref(0)
const currentStudentIndex = ref(0)
const loading = ref(false)
const saving = ref(false)

const currentScore = ref(0)
const currentRecognitionCorrect = ref(true)
const currentCorrectedAnswer = ref('')
const currentImages = ref([])
const currentImageIndex = ref(0)

const currentQuestion = computed(() => questions.value[currentQuestionIndex.value] || {})
const currentStudent = computed(() => students.value[currentStudentIndex.value] || null)
const reviewedCount = computed(() => students.value.filter(s => s.manual_reviewed).length)

// 获取所有主观题
const fetchQuestions = async () => {
  try {
    const res = await axios.get(`/api/exams/${props.examId}/subjective-questions`)
    if (res.data.code === 1) {
      questions.value = res.data.data || []
      if (questions.value.length) {
        await fetchStudentsForQuestion(questions.value[0].id)
      }
    } else {
      ElMessage.error(res.data.msg || '获取主观题失败')
    }
  } catch (error) {
    console.error('获取主观题失败:', error)
    ElMessage.error('获取主观题失败')
  }
}

// 获取某题下所有学生作答
const fetchStudentsForQuestion = async (questionId) => {
  loading.value = true
  try {
    const res = await axios.get(`/api/exams/${props.examId}/scores/${questionId}/students`)
    if (res.data.code === 1) {
      const data = res.data.data || {}
      // 保持当前题目信息
      const q = data.question || {}
      const qIndex = questions.value.findIndex(item => item.id === q.id)
      if (qIndex !== -1) {
        questions.value[qIndex] = { ...questions.value[qIndex], ...q }
      }
      students.value = data.students || []
      currentStudentIndex.value = 0
      await loadCurrentStudentDetail()
    } else {
      ElMessage.error(res.data.msg || '获取学生作答失败')
    }
  } catch (error) {
    console.error('获取学生作答失败:', error)
    ElMessage.error('获取学生作答失败')
  } finally {
    loading.value = false
  }
}

// 获取学生图片
const fetchStudentImages = async (studentId) => {
  try {
    const res = await axios.get(`/api/exams/${props.examId}/students/${studentId}/images`)
    if (res.data.code === 1) {
      const images = res.data.data || []
      return images.sort((a, b) => a.page_order - b.page_order)
    }
    return []
  } catch (error) {
    console.error('获取学生图片失败:', error)
    return []
  }
}

const getOriginalImageUrl = (img) => {
  if (!img) return ''
  const filePath = img.file_path || img.processed_file_path
  let relative = filePath
  if (relative.startsWith('./')) relative = relative.slice(2)
  if (relative.startsWith('uploads/')) relative = relative.slice(8)
  return `/uploads/${relative}`
}

// 加载当前学生详情
const loadCurrentStudentDetail = async () => {
  currentImageIndex.value = 0
  const s = currentStudent.value
  if (!s) {
    currentScore.value = 0
    currentRecognitionCorrect.value = true
    currentCorrectedAnswer.value = ''
    currentImages.value = []
    return
  }

  currentScore.value = s.score ?? 0
  currentRecognitionCorrect.value = s.recognition_correct !== false
  currentCorrectedAnswer.value = s.corrected_answer || ''
  currentImages.value = await fetchStudentImages(s.student_id)

  // 自动标记为已查看
  if (!s.manual_reviewed) {
    markReviewed()
  }
}

// 标记当前学生为已查看
const markReviewed = async () => {
  const s = currentStudent.value
  const q = currentQuestion.value
  if (!s || !q) return
  try {
    await axios.put(
      `/api/exams/${props.examId}/scores/${s.student_id}/${q.id}`,
      { score: s.score ?? 0, manual_reviewed: true }
    )
    s.manual_reviewed = true
  } catch (error) {
    console.error('标记已查看失败:', error)
  }
}

const selectStudent = async (index) => {
  currentStudentIndex.value = index
  await loadCurrentStudentDetail()
}

const nextStudent = async () => {
  if (currentStudentIndex.value < students.value.length - 1) {
    currentStudentIndex.value++
    await loadCurrentStudentDetail()
  }
}

const prevStudent = async () => {
  if (currentStudentIndex.value > 0) {
    currentStudentIndex.value--
    await loadCurrentStudentDetail()
  }
}

const selectQuestion = async (index) => {
  currentQuestionIndex.value = index
  await fetchStudentsForQuestion(questions.value[index].id)
}

// 保存当前学生的得分、修正答案、识别结果
const saveCurrent = async () => {
  const s = currentStudent.value
  const q = currentQuestion.value
  if (!s || !q) return

  saving.value = true
  try {
    const res = await axios.put(
      `/api/exams/${props.examId}/scores/${s.student_id}/${q.id}`,
      {
        score: currentScore.value,
        recognition_correct: currentRecognitionCorrect.value,
        corrected_answer: currentCorrectedAnswer.value,
        manual_reviewed: true
      }
    )
    if (res.data.code === 1) {
      ElMessage.success('保存成功')
      s.score = currentScore.value
      s.recognition_correct = currentRecognitionCorrect.value
      s.corrected_answer = currentCorrectedAnswer.value
      s.manual_reviewed = true
    } else {
      ElMessage.error(res.data.msg || '保存失败')
    }
  } catch (error) {
    console.error('保存失败:', error)
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  fetchQuestions()
})
</script>

<style scoped>
.manual-grading-container {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 240px);
  min-height: 500px;
}

.question-tabs {
  display: flex;
  gap: 8px;
  padding: 12px 16px;
  background: #f5f7fa;
  border-radius: 8px 8px 0 0;
  overflow-x: auto;
  flex-shrink: 0;
}

.question-tab {
  padding: 8px 16px;
  background: #fff;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.2s;
}

.question-tab:hover {
  border-color: #409eff;
  color: #409eff;
}

.question-tab.active {
  background: #409eff;
  color: #fff;
  border-color: #409eff;
}

.empty-tip {
  color: #909399;
  padding: 8px 0;
}

.main-layout {
  display: flex;
  flex: 1;
  border: 1px solid #e4e7ed;
  border-top: none;
  border-radius: 0 0 8px 8px;
  overflow: hidden;
}

.student-sidebar {
  width: 240px;
  border-right: 1px solid #e4e7ed;
  background: #fafafa;
  display: flex;
  flex-direction: column;
}

.sidebar-header {
  padding: 12px 16px;
  border-bottom: 1px solid #e4e7ed;
  font-weight: bold;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.review-progress {
  font-size: 0.85rem;
  color: #606266;
  font-weight: normal;
}

.student-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.student-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px;
  border-radius: 6px;
  cursor: pointer;
  margin-bottom: 6px;
  transition: background 0.2s;
}

.student-item:hover {
  background: #e6f2ff;
}

.student-item.active {
  background: #d9ecff;
}

.student-item.reviewed {
  border-left: 3px solid #67c23a;
}

.student-avatar {
  font-size: 0.85rem;
  flex-shrink: 0;
}

.student-avatar.reviewed {
  background: #67c23a;
  color: #fff;
}

.student-avatar.unreviewed {
  background: #fff;
  color: #606266;
  border: 1px solid #dcdfe6;
}

.student-info {
  flex: 1;
  min-width: 0;
}

.student-name {
  font-size: 0.95rem;
  font-weight: 500;
}

.student-number {
  font-size: 0.75rem;
  color: #909399;
}

.detail-panel {
  flex: 1;
  padding: 20px;
  background: #fff;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.detail-content {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.detail-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  flex-shrink: 0;
}

.detail-body {
  display: flex;
  gap: 20px;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.detail-info {
  flex: 1;
  min-width: 0;
  overflow-y: auto;
  padding-right: 4px;
}

.detail-images {
  width: 45%;
  min-width: 320px;
  max-width: 600px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.image-wrapper {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.student-title h3 {
  margin: 0 0 4px 0;
}

.student-meta {
  color: #909399;
  font-size: 0.85rem;
}

.nav-actions {
  display: flex;
  gap: 8px;
}

.description-content {
  white-space: pre-wrap;
  max-height: 120px;
  overflow-y: auto;
  padding-right: 4px;
  line-height: 1.6;
}

.empty-detail,
.empty-main {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #909399;
  font-size: 1.1rem;
}
</style>
