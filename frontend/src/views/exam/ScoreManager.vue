<template>
  <div class="score-manager">
    <el-card>
      <template #header>
        <div class="header-actions">
          <span>成绩列表</span>
          <div>
            <el-button type="primary" @click="exportObjectiveAnswers">导出客观题答案</el-button>
            <el-button type="warning" @click="exportSubjectiveAnswers">导出主观题答案</el-button>
            <el-button type="primary" @click="exportExcel">导出Excel</el-button>
            <el-button @click="refreshScores">刷新</el-button>
          </div>
        </div>
      </template>

      <div class="sort-toggle" style="margin-bottom: 12px;">
        <el-radio-group v-model="sortMode" size="small">
          <el-radio-button value="rank">按排名排序</el-radio-button>
          <el-radio-button value="student_id">按学号排序</el-radio-button>
        </el-radio-group>
      </div>
      <el-table :data="sortedList" border v-loading="loading">
        <el-table-column type="index" label="排名" width="80" />
        <el-table-column prop="student_number" label="学号" width="150" />
        <el-table-column prop="class" label="班级" width="120" />
        <el-table-column prop="name" label="姓名" width="100" />
        <el-table-column label="得分" width="80">
          <template #default="{ row }">
            {{ row.total_score !== null ? row.total_score : '未评分' }}
          </template>
        </el-table-column>
        <el-table-column label="选择题" width="80">
          <template #default="{ row }">
            {{ row.choice_total !== null ? row.choice_total : '—' }}
          </template>
        </el-table-column>
        <el-table-column label="填空题" width="80">
          <template #default="{ row }">
            {{ row.fill_total !== null ? row.fill_total : '—' }}
          </template>
        </el-table-column>
        <el-table-column label="简答题" width="80">
          <template #default="{ row }">
            {{ row.subjective_total !== null ? row.subjective_total : '—' }}
          </template>
        </el-table-column>
        <el-table-column label="阅卷状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.grading_status === 'completed' ? 'success' : 'info'">
              {{ row.grading_status === 'completed' ? '已完成' : '未完成' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="阅卷时间" width="170">
          <template #default="{ row }">
            {{ row.graded_at ? formatDate(row.graded_at) : '—' }}
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import axios from 'axios'

const props = defineProps({
  examId: { type: [String, Number], required: true }
})

const loading = ref(false)
const studentList = ref([])
const examName = ref('')
const sortMode = ref('rank')

const sortedList = computed(() => {
  const list = [...studentList.value]
  if (sortMode.value === 'student_id') {
    list.sort((a, b) => a.student_id - b.student_id)
  } else {
    // 按排名：已评分按总分降序，未评分放最后
    list.sort((a, b) => {
      if (a.total_score === null && b.total_score === null) return a.student_id - b.student_id
      if (a.total_score === null) return 1
      if (b.total_score === null) return -1
      return b.total_score - a.total_score
    })
  }
  return list
})

const formatDate = (dateStr) => {
  if (!dateStr) return ''
  return new Date(dateStr).toLocaleString('zh-CN')
}

const fetchScores = async () => {
  loading.value = true
  try {
    const res = await axios.get(`/api/exams/${props.examId}/scores`)
    if (res.data.code === 1) {
      const data = res.data.data
      examName.value = data.exam_info?.exam_name || ''
      studentList.value = (data.students || []).map(s => ({
        ...s,
        grading_status: s.total_score !== null ? 'completed' : 'pending',
        graded_at: s.graded_at || null
      })).sort((a, b) => a.student_id - b.student_id)
    } else {
      ElMessage.error(res.data.msg || '获取成绩失败')
    }
  } catch (error) {
    console.error('获取成绩失败:', error)
    ElMessage.error('获取成绩失败')
  } finally {
    loading.value = false
  }
}

const refreshScores = () => {
  fetchScores()
}

// 导出客观题答案
const exportObjectiveAnswers = async () => {
  try {
    const response = await axios.get(`/api/exams/${props.examId}/export-objective`, { responseType: 'blob' })
    const url = window.URL.createObjectURL(new Blob([response.data]))
    const link = document.createElement('a')
    const name = examName.value || '考试'
    link.href = url
    link.setAttribute('download', `exam_${name}_${props.examId}_objective_answers.xlsx`)
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(url)
    ElMessage.success('导出成功')
  } catch (error) {
    console.error('导出失败:', error)
    ElMessage.error('导出失败')
  }
}

// 导出主观题答案
const exportSubjectiveAnswers = async () => {
  try {
    const response = await axios.get(`/api/exams/${props.examId}/export-subjective`, { responseType: 'blob' })
    const url = window.URL.createObjectURL(new Blob([response.data]))
    const link = document.createElement('a')
    const name = examName.value || '考试'
    link.href = url
    link.setAttribute('download', `exam_${name}_${props.examId}_subjective_answers.xlsx`)
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(url)
    ElMessage.success('导出成功')
  } catch (error) {
    console.error('导出失败:', error)
    ElMessage.error('导出失败')
  }
}

// 导出总成绩Excel
const exportExcel = async () => {
  try {
    const response = await axios.get(`/api/exams/${props.examId}/export`, { responseType: 'blob' })
    const url = window.URL.createObjectURL(new Blob([response.data]))
    const link = document.createElement('a')
    const name = examName.value || '考试'
    link.href = url
    link.setAttribute('download', `exam_${name}_${props.examId}_scores.xlsx`)
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(url)
    ElMessage.success('导出成功')
  } catch (error) {
    console.error('导出失败:', error)
    ElMessage.error('导出失败')
  }
}

onMounted(() => {
  fetchScores()
})
</script>

<style scoped>
.header-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>