<template>
  <div class="exam-analysis-container">
    <div v-loading="loading">
      <!-- 整体分析 -->
      <el-card class="analysis-card">
        <template #header>
          <div class="card-header">
            <span>试卷整体分析</span>
            <el-button
              type="primary"
              size="small"
              :loading="savingOverall"
              @click="saveOverall"
            >保存整体分析</el-button>
          </div>
        </template>
        <el-input
          v-model="overallAnalysis"
          type="textarea"
          :rows="4"
          placeholder="在此撰写整张试卷的分析，如总体情况、难度评价、教学改进建议等"
        />
      </el-card>

      <!-- 按题型分组 -->
      <el-card
        v-for="group in typeGroups"
        :key="group.type"
        class="analysis-card"
      >
        <template #header>
          <div class="card-header">
            <span>{{ group.type }}（平均得分率 {{ group.avgRate }}%）</span>
            <el-button
              type="primary"
              size="small"
              :loading="savingType === group.type"
              @click="saveTypeAnalysis(group.type)"
            >保存{{ group.type }}分析</el-button>
          </div>
        </template>

        <el-table :data="group.questions" border size="small">
          <el-table-column prop="question_order" label="题号" width="80" align="center" />
          <el-table-column label="题目内容" min-width="280">
            <template #default="{ row }">
              <div class="truncate-text">{{ row.content || '（无内容）' }}</div>
            </template>
          </el-table-column>
          <el-table-column label="得分情况" width="180">
            <template #default="{ row }">
              <div class="score-cell">
                <el-progress
                  :percentage="row.rate"
                  :stroke-width="12"
                  :color="rateColor(row.rate)"
                  style="width: 110px;"
                />
                <span class="score-text">{{ row.avg_score }} / {{ row.max_score }} 分</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="参考人数" width="90" align="center">
            <template #default="{ row }">
              {{ row.scored_count }} / {{ row.student_count }}
            </template>
          </el-table-column>
          <el-table-column label="所属知识点" min-width="240">
            <template #default="{ row }">
              <div style="display: flex; gap: 8px; align-items: center;">
                <el-input
                  v-model="row.knowledge_point"
                  size="small"
                  placeholder="填写本题所属知识点"
                />
                <el-button
                  size="small"
                  type="primary"
                  plain
                  :loading="savingQuestion === row.question_id"
                  @click="saveKnowledge(row)"
                >保存</el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>

        <div class="type-analysis">
          <div class="type-analysis-label">题型分析：</div>
          <el-input
            v-model="group.analysis"
            type="textarea"
            :rows="3"
            placeholder="在此撰写该题型的分析，如学生掌握情况、常见错误、教学建议等"
          />
        </div>
      </el-card>

      <div v-if="!typeGroups.length" class="empty-tip">
        该考试暂无题目
      </div>
    </div>
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
const overallAnalysis = ref('')
const questions = ref([])
const typeAnalyses = ref({})

const savingOverall = ref(false)
const savingType = ref('')
const savingQuestion = ref(0)

const typeGroups = computed(() => {
  const groups = {}
  for (const q of questions.value) {
    if (!groups[q.type]) {
      groups[q.type] = {
        type: q.type,
        questions: [],
        analysis: typeAnalyses.value[q.type] || '',
        avgRate: 0
      }
    }
    groups[q.type].questions.push(q)
  }
  const result = Object.values(groups)
  for (const g of result) {
    const total = g.questions.reduce((sum, q) => sum + q.rate, 0)
    g.avgRate = g.questions.length ? (total / g.questions.length).toFixed(1) : '0'
  }
  return result
})

const rateColor = (rate) => {
  if (rate < 60) return '#f56c6c'
  if (rate < 80) return '#e6a23c'
  return '#67c23a'
}

const fetchAnalysis = async () => {
  loading.value = true
  try {
    const res = await axios.get(`/api/exams/${props.examId}/analysis`)
    if (res.data.code === 1) {
      const data = res.data.data || {}
      overallAnalysis.value = data.overall_analysis || ''
      questions.value = data.questions || []
      typeAnalyses.value = data.type_analyses || {}
    } else {
      ElMessage.error(res.data.msg || '获取分析失败')
    }
  } catch (error) {
    console.error('获取考试分析失败:', error)
    ElMessage.error('获取考试分析失败')
  } finally {
    loading.value = false
  }
}

const saveKnowledge = async (row) => {
  savingQuestion.value = row.question_id
  try {
    const res = await axios.put(
      `/api/exams/${props.examId}/analysis/question/${row.question_id}`,
      { knowledge_point: row.knowledge_point }
    )
    if (res.data.code === 1) {
      ElMessage.success('知识点已保存')
    } else {
      ElMessage.error(res.data.msg || '保存失败')
    }
  } catch (error) {
    console.error('保存知识点失败:', error)
    ElMessage.error('保存知识点失败')
  } finally {
    savingQuestion.value = 0
  }
}

const saveTypeAnalysis = async (type) => {
  savingType.value = type
  const group = typeGroups.value.find(g => g.type === type)
  try {
    const res = await axios.put(
      `/api/exams/${props.examId}/analysis/type`,
      { question_type: type, analysis: group ? group.analysis : '' }
    )
    if (res.data.code === 1) {
      ElMessage.success(`${type}分析已保存`)
      typeAnalyses.value[type] = group ? group.analysis : ''
    } else {
      ElMessage.error(res.data.msg || '保存失败')
    }
  } catch (error) {
    console.error('保存题型分析失败:', error)
    ElMessage.error('保存题型分析失败')
  } finally {
    savingType.value = ''
  }
}

const saveOverall = async () => {
  savingOverall.value = true
  try {
    const res = await axios.put(
      `/api/exams/${props.examId}/analysis/overall`,
      { overall_analysis: overallAnalysis.value }
    )
    if (res.data.code === 1) {
      ElMessage.success('整体分析已保存')
    } else {
      ElMessage.error(res.data.msg || '保存失败')
    }
  } catch (error) {
    console.error('保存整体分析失败:', error)
    ElMessage.error('保存整体分析失败')
  } finally {
    savingOverall.value = false
  }
}

onMounted(() => {
  fetchAnalysis()
})
</script>

<style scoped>
.exam-analysis-container {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.analysis-card {
  margin-bottom: 0;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.score-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

.score-text {
  font-size: 0.8rem;
  color: #606266;
  white-space: nowrap;
}

.type-analysis {
  margin-top: 16px;
}

.type-analysis-label {
  font-weight: bold;
  margin-bottom: 8px;
  color: #303133;
}

.truncate-text {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.empty-tip {
  text-align: center;
  color: #909399;
  padding: 40px;
}
</style>
