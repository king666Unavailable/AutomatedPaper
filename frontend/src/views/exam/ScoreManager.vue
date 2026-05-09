<template>
  <div class="score-manager">
    <el-card>
      <template #header>
        <div class="header-actions">
          <span>成绩列表</span>
          <div>
            <el-button type="primary" @click="exportExcel">导出Excel</el-button>
            <el-button @click="refreshScores">刷新</el-button>
          </div>
        </div>
      </template>

      <el-table :data="studentList" border v-loading="loading">
        <el-table-column type="index" label="排名" width="80" />
        <el-table-column prop="student_number" label="学号" width="150" />
        <el-table-column prop="class" label="班级" width="120" />
        <el-table-column prop="name" label="姓名" width="100" />
        <el-table-column label="得分" width="80">
          <template #default="{ row }">
            {{ row.total_score !== null ? row.total_score : '未评分' }}
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
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import axios from 'axios'

const props = defineProps({
  examId: { type: [String, Number], required: true }
})

const loading = ref(false)
const studentList = ref([])

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
      studentList.value = data.students.map(s => ({
        ...s,
        grading_status: s.total_score !== null ? 'completed' : 'pending',
        graded_at: s.graded_at || null
      }))
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

const exportExcel = async () => {
  try {
    const response = await axios.get(`/api/exams/${props.examId}/export`, {
      responseType: 'blob'
    })
    const url = window.URL.createObjectURL(new Blob([response.data]))
    const link = document.createElement('a')
    link.href = url
    link.setAttribute('download', `exam_${props.examId}_scores.xlsx`)
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