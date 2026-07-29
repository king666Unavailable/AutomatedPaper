<template>
  <div class="ai-grading-container">
    <div class="ai-grading-header">
      <h3>AI阅卷控制台</h3>
      <p>使用人工智能对学生的答卷进行自动评分和分析</p>
    </div>

    <div class="ai-grading-actions">
      <el-button type="success" size="large" @click="triggerAIGrading" :loading="aiGradingInProgress">
        <el-icon><Cpu /></el-icon> 开始AI阅卷
      </el-button>
      <el-button @click="refreshAll">
        <el-icon><Refresh /></el-icon> 刷新状态
      </el-button>
    </div>

    <div class="ai-grading-status" v-if="aiGradingInProgress">
      <el-progress :percentage="aiGradingProgress" :status="aiGradingStatus" />
      <p>{{ aiGradingMessage }}</p>
    </div>

    <div class="ai-grading-info" v-if="!aiGradingInProgress">
      <el-card>
        <template #header>
          <span>阅卷统计</span>
        </template>
        <div class="stats-grid">
          <div class="stat-item">
            <div class="stat-value">{{ ungradedCount }}</div>
            <div class="stat-label">待阅卷</div>
          </div>
          <div class="stat-item">
            <div class="stat-value">{{ gradedCount }}</div>
            <div class="stat-label">已完成</div>
          </div>
          <div class="stat-item">
            <div class="stat-value">{{ totalStudents }}</div>
            <div class="stat-label">总学生数</div>
          </div>
        </div>
      </el-card>
    </div>

    <!-- 学生答题详情表格 -->
    <el-card style="margin-top: 20px">
      <template #header>
        <span>学生答题详情</span>
      </template>
      <div style="overflow-x: auto;">
        <el-table :data="studentScoreList" border v-loading="loadingScores" max-height="calc(100vh - 260px)">
          <el-table-column type="index" label="序号" width="60" fixed="left" />
          <el-table-column prop="name" label="姓名" width="120" fixed="left" />
          <el-table-column prop="student_number" label="学号" width="150" fixed="left" />
          <el-table-column label="总分" width="100" fixed="left">
            <template #default="{ row }">
              {{ row.total_score !== null ? row.total_score : '未评分' }}
            </template>
          </el-table-column>
          <!-- 操作列 -->
          <el-table-column label="操作" width="200" align="center" fixed="left">
            <template #default="{ row }">
              <div style="display: flex; flex-direction: column; gap: 6px; align-items: center;">
                <el-button
                  type="warning"
                  size="small"
                  :loading="regradingStudents.has(row.student_id)"
                  @click="regradeStudent(row.student_id)"
                >重新阅卷</el-button>
                <el-button
                  type="primary"
                  size="small"
                  @click="viewStudentAnswers(row)"
                >查看学生答案</el-button>
              </div>
            </template>
          </el-table-column>
          <!-- 动态题目列 -->
          <el-table-column
            v-for="order in questionOrders"
            :key="order"
            :label="String(order)"
            width="80"
            align="center"
          >
            <template #default="{ row }">
              <el-link type="primary" :underline="false" @click="viewQuestionDetail(row, order)">
                {{ getScoreDisplay(row, order) }}
              </el-link>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </el-card>

    <!-- 题目详情弹窗（含原始答题卡图片） -->
    <el-dialog
      v-model="detailDialogVisible"
      width="800px"
      @closed="resetDetail"
    >
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center; width: 100%;">
          <span>{{ `题目详情 - ${currentDetail.studentName} 第${currentDetail.order}题` }}</span>
          <div style="display: flex; gap: 8px;">
            <el-button
              size="small"
              :disabled="currentDetail.currentIndex === 0"
              @click="switchQuestion(-1)"
            >上一题</el-button>
            <el-button
              size="small"
              :disabled="currentDetail.currentIndex === currentDetail.allQuestions.length - 1"
              @click="switchQuestion(1)"
            >下一题</el-button>
          </div>
        </div>
      </template>
      <div v-if="currentDetail.question">
        <el-descriptions :column="1" border size="small">
          <el-descriptions-item label="题目内容">
            <div class="description-content">{{ currentDetail.question.content }}</div>
          </el-descriptions-item>
          <el-descriptions-item label="参考答案">
            <div class="description-content">{{ currentDetail.question.reference_answer }}</div>
          </el-descriptions-item>
          <el-descriptions-item label="评分标准">
            <div class="description-content">{{ currentDetail.question.scoring_rules }}</div>
          </el-descriptions-item>
          <el-descriptions-item label="满分">
            {{ currentDetail.question.max_score || 0 }}
          </el-descriptions-item>
          <el-descriptions-item label="学生答案">
            <div style="display: flex; gap: 16px;">
              <div style="flex: 1; min-width: 0;">
                <div style="color: #909399; font-size: 0.85rem; margin-bottom: 4px;">自动识别结果</div>
                <div class="description-content">{{ currentDetail.question.student_answer || '（未识别）' }}</div>
              </div>
              <div style="flex: 1; min-width: 0;">
                <div style="color: #909399; font-size: 0.85rem; margin-bottom: 4px;">修正答案</div>
                <el-input
                  v-model="currentCorrectedAnswer"
                  type="textarea"
                  :rows="2"
                  placeholder="若自动识别有误，可在此填写修正后的答案"
                  size="small"
                  :disabled="savingScore"
                />
              </div>
            </div>
          </el-descriptions-item>
          <el-descriptions-item label="识别结果人工标注">
            <div style="display: flex; align-items: center; gap: 10px;">
              <el-select v-model="currentRecognitionCorrect" size="small" style="width: 100px;" :disabled="savingScore">
                <el-option label="正确" :value="true" />
                <el-option label="错误" :value="false" />
              </el-select>
              <el-button type="primary" size="small" :loading="savingScore" @click="saveScore">保存</el-button>
            </div>
          </el-descriptions-item>
          <el-descriptions-item label="当前得分">
            <div style="display: flex; align-items: center; gap: 10px;">
              <el-input-number
                v-model="currentScore"
                :min="0"
                :max="currentDetail.question.max_score || 100"
                size="small"
                controls-position="right"
                :disabled="savingScore"
              />
              <el-button type="primary" size="small" :loading="savingScore" @click="saveScore">保存</el-button>
            </div>
          </el-descriptions-item>
        </el-descriptions>

        <!-- 对应原始答题卡图片 -->
        <div style="margin-top: 20px;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
            <h4 style="margin: 0;">原始答题卡</h4>
            <span style="color: #6b7280; font-size: 0.85rem;">可以手动切换答题卡页面</span>
          </div>
          <div v-if="currentDetail.images && currentDetail.images.length">
            <div style="display: flex; justify-content: center; align-items: center; gap: 12px; margin-bottom: 10px;">
              <el-button
                size="small"
                :disabled="currentImageIndex === 0"
                @click="currentImageIndex--"
              >上一页</el-button>
              <span>第 {{ currentImageIndex + 1 }} / {{ currentDetail.images.length }} 页</span>
              <el-button
                size="small"
                :disabled="currentImageIndex === currentDetail.images.length - 1"
                @click="currentImageIndex++"
              >下一页</el-button>
            </div>
            <el-image
              :src="getOriginalImageUrl(currentDetail.images[currentImageIndex])"
              fit="contain"
              style="width: 100%; height: 500px; border: 1px solid #ddd; cursor: pointer;"
              :preview-src-list="[getOriginalImageUrl(currentDetail.images[currentImageIndex])]"
            />
          </div>
          <div v-else>暂无答题卡图片</div>
        </div>
      </div>
      <div v-else style="text-align: center; color: #999;">暂无题目数据</div>
      <template #footer>
        <el-button @click="detailDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 学生全部答案弹窗 -->
    <el-dialog
      v-model="answersDialogVisible"
      :title="`学生答案 - ${currentStudentAnswers.studentName}`"
      width="900px"
      @closed="resetStudentAnswers"
    >
      <el-table :data="currentStudentAnswers.answers" border v-loading="savingStudentAnswers">
        <el-table-column prop="question_order" label="题号" width="80" align="center" />
        <el-table-column label="学生答案" min-width="320">
          <template #default="{ row }">
            <div style="display: flex; gap: 12px;">
              <div style="flex: 1; min-width: 0;">
                <div style="color: #909399; font-size: 0.75rem; margin-bottom: 4px;">自动识别</div>
                <div style="white-space: pre-wrap;">{{ row.student_answer || '（未识别或无答案）' }}</div>
              </div>
              <div style="flex: 1; min-width: 0;">
                <div style="color: #909399; font-size: 0.75rem; margin-bottom: 4px;">修正答案</div>
                <el-input
                  v-model="row.corrected_answer"
                  type="textarea"
                  :rows="2"
                  placeholder="可填写修正后的答案"
                  size="small"
                />
              </div>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="识别结果人工标注" width="160" align="center">
          <template #default="{ row }">
            <el-select v-model="row.recognition_correct" size="small" style="width: 100px;">
              <el-option label="正确" :value="true" />
              <el-option label="错误" :value="false" />
            </el-select>
          </template>
        </el-table-column>

        <el-table-column label="参考答案" min-width="160">
          <template #default="{ row }">
            <div style="white-space: pre-wrap;">{{ row.reference_answer || '（无参考答案）' }}</div>
          </template>
        </el-table-column>

        <el-table-column label="当前得分" width="140" align="center">
          <template #default="{ row }">
            <el-input-number
              v-model="row.score"
              :min="0"
              :max="row.max_score || 100"
              size="small"
              controls-position="right"
            />
          </template>
        </el-table-column>
      </el-table>

      <template #footer>
        <el-button @click="answersDialogVisible = false">关闭</el-button>
        <el-button type="primary" :loading="savingStudentAnswers" @click="saveStudentAnswers">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Cpu, Refresh } from '@element-plus/icons-vue'
import axios from 'axios'

const props = defineProps({
  examId: { type: [String, Number], required: true },
  scores: { type: Object, default: () => ({ total: 0, graded: 0 }) },
  totalStudents: { type: Number, default: 0 }
})

const emit = defineEmits(['refresh'])

// 阅卷状态
const aiGradingInProgress = ref(false)
const aiGradingProgress = ref(0)
const aiGradingStatus = ref('success')
const aiGradingMessage = ref('')

// 学生成绩列表
const studentScoreList = ref([])
const loadingScores = ref(false)
const questionOrders = ref([])

// 正在重新阅卷的学生ID集合
const regradingStudents = ref(new Set())

// 题目详情弹窗相关
const detailDialogVisible = ref(false)
const currentDetail = ref({
  studentName: '',
  order: 0,
  studentId: 0,
  question: null,
  images: [],
  allQuestions: [],
  currentIndex: 0
})
const currentScore = ref(0)
const currentRecognitionCorrect = ref(true)
const currentCorrectedAnswer = ref('')
const savingScore = ref(false)
const currentImageIndex = ref(0)

const hasUnsavedScoreChange = computed(() => {
  const q = currentDetail.value.question
  if (!q) return false
  const scoreChanged = currentScore.value !== q.score
  const recognitionChanged = currentRecognitionCorrect.value !== q.recognition_correct
  const correctedChanged = currentCorrectedAnswer.value !== (q.corrected_answer || '')
  return scoreChanged || recognitionChanged || correctedChanged
})

// 学生全部答案弹窗相关
const answersDialogVisible = ref(false)
const savingStudentAnswers = ref(false)
const currentStudentAnswers = ref({
  studentId: 0,
  studentName: '',
  answers: []
})

// 题目信息映射表
const questionsMap = ref({})

const ungradedCount = computed(() => props.scores.total - props.scores.graded)
const gradedCount = computed(() => props.scores.graded)

// 获取题目信息列表
const fetchQuestions = async () => {
  try {
    const res = await axios.get(`/api/exams/${props.examId}/questions`)
    if (res.data.code === 1) {
      const questions = res.data.data || []
      const map = {}
      questions.forEach(q => {
        map[q.question_order] = {
          id: q.id,
          content: q.content,
          reference_answer: q.reference_answer,
          scoring_rules: q.scoring_rules,
          max_score: q.score
        }
      })
      questionsMap.value = map
    }
  } catch (error) {
    console.error('获取题目信息失败:', error)
  }
}

// 获取学生成绩列表
const fetchStudentScores = async () => {
  loadingScores.value = true
  try {
    const res = await axios.get(`/api/exams/${props.examId}/scores`)
    if (res.data.code === 1) {
      const data = res.data.data
      studentScoreList.value = data.students || []
      if (studentScoreList.value.length > 0 && studentScoreList.value[0].question_scores) {
        questionOrders.value = studentScoreList.value[0].question_scores.map(q => q.question_order)
      }
      await fetchQuestions()
    } else {
      ElMessage.error(res.data.msg || '获取成绩失败')
    }
  } catch (error) {
    console.error('获取成绩失败:', error)
    ElMessage.error('获取成绩失败')
  } finally {
    loadingScores.value = false
  }
}

// 获取原始图片路径
const getOriginalImageUrl = (img) => {
  if (!img) return ''
  const filePath = img.file_path || img.processed_file_path
  let relative = filePath
  if (relative.startsWith('./')) relative = relative.slice(2)
  if (relative.startsWith('uploads/')) relative = relative.slice(8)
  return `/uploads/${relative}`
}

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

const getScoreDisplay = (row, order) => {
  const qs = row.question_scores?.find(q => q.question_order === order)
  if (qs && qs.score !== null) {
    return `${qs.score}/${qs.max_score || 0}`
  } else {
    return '—'
  }
}

const computeImageIndex = (order, allImages) => {
  if (allImages.length === 0 || questionOrders.value.length === 0) return 0
  const totalQuestions = questionOrders.value.length
  const pages = allImages.length
  const questionsPerPage = Math.ceil(totalQuestions / pages)
  const pageIndex = Math.floor((order - questionOrders.value[0]) / questionsPerPage)
  return Math.min(Math.max(pageIndex, 0), pages - 1)
}

const buildQuestionDetail = (qs, studentName, studentId, allImages, allQuestions, index) => {
  const order = qs.question_order
  const questionInfo = questionsMap.value[order] || {}
  return {
    studentName,
    order,
    studentId,
    question: {
      question_id: qs.question_id,
      content: questionInfo.content || '（无题目内容）',
      reference_answer: questionInfo.reference_answer || '（无参考答案）',
      scoring_rules: questionInfo.scoring_rules || '（无评分标准）',
      max_score: questionInfo.max_score || qs.max_score || 0,
      student_answer: qs.student_answer,
      score: qs.score,
      recognition_correct: qs.recognition_correct !== false,
      corrected_answer: qs.corrected_answer || ''
    },
    images: allImages,
    allQuestions,
    currentIndex: index
  }
}

// 点击题目得分，显示详情弹窗
const viewQuestionDetail = async (row, order) => {
  const allQuestions = (row.question_scores || []).sort((a, b) => a.question_order - b.question_order)
  const index = allQuestions.findIndex(q => q.question_order === order)
  if (index === -1) return

  const qs = allQuestions[index]
  const allImages = await fetchStudentImages(row.student_id)
  currentImageIndex.value = computeImageIndex(order, allImages)

  currentDetail.value = buildQuestionDetail(qs, row.name, row.student_id, allImages, allQuestions, index)
  currentScore.value = qs.score ?? 0
  currentRecognitionCorrect.value = qs.recognition_correct !== false
  currentCorrectedAnswer.value = qs.corrected_answer || ''
  detailDialogVisible.value = true
}

// 切换题目
const switchQuestion = async (delta) => {
  const newIndex = currentDetail.value.currentIndex + delta
  if (newIndex < 0 || newIndex >= currentDetail.value.allQuestions.length) return

  if (hasUnsavedScoreChange.value) {
    try {
      await ElMessageBox.confirm(
        '当前题得分、修正答案或识别标注已修改但尚未保存，切换后将丢失修改。是否继续？',
        '提示',
        { confirmButtonText: '继续切换', cancelButtonText: '取消', type: 'warning' }
      )
    } catch {
      return
    }
  }

  const qs = currentDetail.value.allQuestions[newIndex]
  currentDetail.value = buildQuestionDetail(
    qs,
    currentDetail.value.studentName,
    currentDetail.value.studentId,
    currentDetail.value.images,
    currentDetail.value.allQuestions,
    newIndex
  )
  currentScore.value = qs.score ?? 0
  currentRecognitionCorrect.value = qs.recognition_correct !== false
  currentCorrectedAnswer.value = qs.corrected_answer || ''
}

// 关闭弹窗时重置
const resetDetail = () => {
  currentDetail.value = { studentName: '', order: 0, studentId: 0, question: null, images: [], allQuestions: [], currentIndex: 0 }
  currentScore.value = 0
  currentRecognitionCorrect.value = true
  currentCorrectedAnswer.value = ''
  savingScore.value = false
  currentImageIndex.value = 0
}

// 查看学生全部答案
const viewStudentAnswers = (row) => {
  const answers = (row.question_scores || []).map(qs => {
    const questionInfo = questionsMap.value[qs.question_order] || {}
    return {
      question_id: qs.question_id,
      question_order: qs.question_order,
      student_answer: qs.student_answer,
      corrected_answer: qs.corrected_answer || '',
      reference_answer: questionInfo.reference_answer,
      recognition_correct: qs.recognition_correct !== false,
      score: qs.score ?? 0,
      max_score: questionInfo.max_score || qs.max_score || 0
    }
  }).sort((a, b) => a.question_order - b.question_order)

  currentStudentAnswers.value = {
    studentId: row.student_id,
    studentName: row.name,
    answers
  }
  answersDialogVisible.value = true
}

// 关闭学生答案弹窗时重置
const resetStudentAnswers = () => {
  currentStudentAnswers.value = { studentId: 0, studentName: '', answers: [] }
}

// 保存学生全部答案的得分
const saveStudentAnswers = async () => {
  const { studentId, answers } = currentStudentAnswers.value
  if (!answers.length) return

  savingStudentAnswers.value = true
  try {
    for (const item of answers) {
      await axios.put(
        `/api/exams/${props.examId}/scores/${studentId}/${item.question_id}`,
        { score: item.score, recognition_correct: item.recognition_correct, corrected_answer: item.corrected_answer }
      )
    }
    ElMessage.success('分数已保存')
    await fetchStudentScores()
    emit('refresh')
    answersDialogVisible.value = false
  } catch (error) {
    console.error('保存分数失败:', error)
    ElMessage.error('保存分数失败')
  } finally {
    savingStudentAnswers.value = false
  }
}

// 保存修改后的分数
const saveScore = async () => {
  if (!currentDetail.value.question) return
  const { studentId, question } = currentDetail.value

  savingScore.value = true
  try {
    const res = await axios.put(
      `/api/exams/${props.examId}/scores/${studentId}/${question.question_id}`,
      { score: currentScore.value, recognition_correct: currentRecognitionCorrect.value, corrected_answer: currentCorrectedAnswer.value }
    )
    if (res.data.code === 1) {
      ElMessage.success('分数已更新')
      currentDetail.value.question.score = currentScore.value
      currentDetail.value.question.recognition_correct = currentRecognitionCorrect.value
      currentDetail.value.question.corrected_answer = currentCorrectedAnswer.value
      await fetchStudentScores()
      emit('refresh')
    } else {
      ElMessage.error(res.data.msg || '更新失败')
    }
  } catch (error) {
    console.error('更新分数失败:', error)
    ElMessage.error('更新分数失败')
  } finally {
    savingScore.value = false
  }
}

// 单个学生重新阅卷
const regradeStudent = async (studentId) => {
  if (regradingStudents.value.has(studentId)) return
  regradingStudents.value.add(studentId)
  try {
    const startRes = await axios.post(`/api/exams/${props.examId}/students/${studentId}/regrade`)
    if (startRes.data.code !== 1) throw new Error(startRes.data.msg || '启动失败')
    const { job_id } = startRes.data.data
    let finished = false
    while (!finished) {
      await new Promise(resolve => setTimeout(resolve, 2000))
      const statusRes = await axios.get(`/api/grading/jobs/${job_id}`)
      if (statusRes.data.code !== 1) throw new Error(statusRes.data.msg)
      const { status } = statusRes.data.data
      if (status === 'completed') {
        finished = true
        ElMessage.success('该学生的阅卷已完成')
        await fetchStudentScores()
        emit('refresh')
      } else if (status === 'failed') {
        throw new Error('阅卷任务失败')
      }
    }
  } catch (error) {
    console.error(error)
    ElMessage.error(error.message || '重新阅卷失败')
  } finally {
    regradingStudents.value.delete(studentId)
  }
}

// 开始AI阅卷
const triggerAIGrading = async () => {
  try {
    aiGradingInProgress.value = true
    aiGradingProgress.value = 0

    const startRes = await axios.post(`/api/exams/${props.examId}/grade`)
    if (startRes.data.code !== 1) throw new Error(startRes.data.msg || '启动失败')
    const { job_id } = startRes.data.data

    let finished = false
    while (!finished) {
      await new Promise(resolve => setTimeout(resolve, 2000))
      const statusRes = await axios.get(`/api/grading/jobs/${job_id}`)
      if (statusRes.data.code !== 1) throw new Error(statusRes.data.msg)
      const { status, total_students, processed_students } = statusRes.data.data

      if (total_students > 0) {
        aiGradingProgress.value = Math.floor((processed_students / total_students) * 100)
      }
      if (status === 'completed') {
        finished = true
        ElMessage.success(`阅卷完成，共处理 ${total_students} 名学生`)
        await fetchStudentScores()
        emit('refresh')
        break
      } else if (status === 'failed') {
        throw new Error('阅卷任务失败')
      }
    }
  } catch (error) {
    aiGradingStatus.value = 'exception'
    ElMessage.error(error.message || 'AI阅卷失败')
  } finally {
    aiGradingInProgress.value = false
    setTimeout(() => { aiGradingProgress.value = 0 }, 2000)
  }
}

// 手动刷新
const refreshAll = () => {
  emit('refresh')
  fetchStudentScores()
}

onMounted(() => {
  fetchStudentScores()
})
</script>

<style scoped>
.ai-grading-container { padding: 20px; display: flex; flex-direction: column; gap: 24px; }
.ai-grading-header { text-align: center; }
.ai-grading-header h3 { margin: 0 0 8px 0; color: #374151; font-size: 1.5rem; font-weight: 600; }
.ai-grading-header p { margin: 0; color: #6b7280; font-size: 1rem; }
.ai-grading-actions { display: flex; justify-content: center; gap: 16px; flex-wrap: wrap; }
.ai-grading-status { text-align: center; padding: 20px; background: #f9fafb; border-radius: 8px; }
.ai-grading-status p { margin: 12px 0 0 0; color: #374151; font-weight: 500; }
.ai-grading-info { margin-top: 24px; }
.stats-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 24px; margin-top: 16px; }
.stat-item { text-align: center; padding: 20px; background: #f9fafb; border-radius: 8px; transition: all 0.2s; }
.stat-item:hover { background: #f3f4f6; transform: translateY(-2px); }
.stat-value { font-size: 2rem; font-weight: bold; color: #3b82f6; margin-bottom: 8px; }
.stat-label { font-size: 0.9rem; color: #6b7280; font-weight: 500; }

.description-content {
  white-space: pre-wrap;
  max-height: 120px;
  overflow-y: auto;
  padding-right: 4px;
  line-height: 1.6;
}
</style>