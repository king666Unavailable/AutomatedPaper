<template>
  <div
    class="answer-manager"
    v-loading="folderUploading || uploadingSingle"
    element-loading-text="正在上传图片，请稍候..."
    element-loading-background="rgba(255, 255, 255, 0.8)"
  >
    <div class="tab-actions">
      <el-button type="primary" @click="openUploadDialog">上传图片</el-button>
      <el-button @click="fetchStudentImages">刷新</el-button>
      <el-button type="success" @click="handleImportFolder">导入文件夹</el-button>
      <el-radio-group v-model="autoMatchMode" style="margin-left: 15px;">
        <el-radio :label="false">顺序对应</el-radio>
        <el-radio :label="true">姓名匹配</el-radio>
      </el-radio-group>
    </div>

    <!-- 学生表格 -->
    <el-table :data="studentList" style="width: 100%" row-key="student_id">
      <el-table-column type="index" label="序号" width="60" />
      <el-table-column prop="student_number" label="学号" width="120" />
      <el-table-column prop="name" label="姓名" width="100" />
      <el-table-column prop="class" label="班级" width="120" />
      <el-table-column label="答题卡图片" min-width="400">
        <template #default="{ row }">
          <div class="images-container">
            <div v-for="img in row.images" :key="img.id" class="image-item">
              <img
                :src="getImageUrl(img)"
                class="image-thumb"
                @click="openPreview(getImageUrl(img))"
              />
              <div class="image-actions">
                <el-input-number
                  v-model="img.page_order"
                  :min="0"
                  size="small"
                  controls-position="right"
                  @change="updateImageOrder(img)"
                  style="width: 100px"
                />
                <el-button type="danger" size="small" @click="deleteImage(img.id)">删除</el-button>
                <el-button type="warning" size="small" @click="openEditDialog(img)">遮盖</el-button>
              </div>
              <div class="image-filename">{{ img.filename }}</div>
            </div>
            <el-upload
              :auto-upload="false"
              :show-file-list="false"
              :on-change="(file) => handleAddFile(file, row.student_id)"
              multiple
              accept=".jpg,.jpeg,.png,.bmp"
            >
              <el-button type="primary" plain size="small">+ 添加图片</el-button>
            </el-upload>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="100" align="center">
        <template #default="{ row }">
          <el-button type="danger" size="small" @click="deleteAllImages(row.student_id, row.name)">删除全部</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 上传对话框 -->
    <el-dialog v-model="showUploadDialog" title="上传答题卡图片" width="600px">
      <el-form label-width="100px">
        <el-form-item label="匹配模式">
          <el-radio-group v-model="autoMatchMode" @change="onModeChange">
            <el-radio :label="false">顺序对应（需选学生）</el-radio>
            <el-radio :label="true">自动姓名匹配</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="选择学生" v-if="!autoMatchMode">
          <el-select v-model="uploadStudentId" placeholder="请选择学生" filterable>
            <el-option
              v-for="s in studentList"
              :key="s.student_id"
              :label="`${s.name} (${s.student_number || '无学号'})`"
              :value="s.student_id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="图片文件">
          <el-upload
            ref="uploadRef"
            v-model:file-list="uploadFileList"
            :auto-upload="false"
            multiple
            accept=".jpg,.jpeg,.png,.bmp"
            :limit="20"
          >
            <el-button>选择文件</el-button>
            <template #tip>
              <div class="el-upload__tip" v-if="autoMatchMode">
                每组 {{ imagesPerStudent }} 张图片，按学生顺序选择，系统将自动识别第一张姓名
              </div>
              <div class="el-upload__tip" v-else>
                可多选，每张图片将按顺序分配页码（0,1,2...）
              </div>
            </template>
          </el-upload>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showUploadDialog = false">取消</el-button>
        <el-button type="primary" @click="uploadImages">确认上传</el-button>
      </template>
    </el-dialog>

    <!-- 遮盖编辑对话框 -->
    <el-dialog
      v-model="showEditDialog"
      title="涂抹遮盖（鼠标拖拽选择矩形区域）"
      width="900px"
      @closed="clearEdit"
    >
      <div style="display: flex; justify-content: center; margin-bottom: 10px;">
        <el-button @click="undoRect">撤销上一个矩形</el-button>
        <el-button @click="resetMask">重置为原图</el-button>
        <el-button type="success" @click="saveEdit">保存遮盖并更新</el-button>
      </div>
      <div
        ref="editContainer"
        style="position: relative; display: inline-block; user-select: none; cursor: crosshair;"
        @mousedown="startDraw"
        @mousemove="drawing"
        @mouseup="endDraw"
        @mouseleave="endDraw"
      >
        <el-image
          :src="editImageUrl"
          fit="contain"
          style="max-width: 100%; display: block;"
        />
        <div
          v-for="(rect, index) in editRects"
          :key="index"
          :style="{
            position: 'absolute',
            left: rect.x + 'px',
            top: rect.y + 'px',
            width: rect.w + 'px',
            height: rect.h + 'px',
            border: '1px dashed red',
            background: 'rgba(255,255,255,0.5)'
          }"
        ></div>
        <div
          v-if="drawingRect"
          :style="{
            position: 'absolute',
            left: drawingRect.x + 'px',
            top: drawingRect.y + 'px',
            width: drawingRect.w + 'px',
            height: drawingRect.h + 'px',
            border: '2px dashed blue',
            background: 'rgba(200,200,255,0.3)'
          }"
        ></div>
      </div>
    </el-dialog>

    <!-- 自定义全屏图片预览（可拖拽、缩放，多种关闭方式） -->
    <Teleport to="body">
      <div v-if="previewVisible" class="preview-overlay" @click.self="closePreview">
        <div
          class="preview-content"
          @mousedown.prevent="startDrag"
          @mousemove="onDrag"
          @mouseup="endDrag"
          @mouseleave="endDrag"
          @wheel.prevent="onWheel"
          @dblclick="resetTransform"
        >
          <img
            :src="previewImg"
            :style="{
              transform: `translate(${previewTranslate.x}px, ${previewTranslate.y}px) scale(${previewScale})`,
              cursor: isDragging ? 'grabbing' : 'grab'
            }"
            class="preview-img"
            draggable="false"
            @mouseup.stop="onImageMouseUp"
          />
        </div>
        <!-- 右上角关闭叉号 -->
        <el-icon class="preview-close" @click="closePreview"><Close /></el-icon>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Close } from '@element-plus/icons-vue'
import axios from 'axios'

const props = defineProps({
  examId: { type: [String, Number], required: true },
  students: { type: Array, default: () => [] },
  imagesPerStudent: { type: Number, default: 4 }
})

const studentList = ref([])
const showUploadDialog = ref(false)
const uploadStudentId = ref(null)
const uploadFileList = ref([])
const folderUploading = ref(false)
const uploadingSingle = ref(false)
const autoMatchMode = ref(false)

// 预览相关
const previewVisible = ref(false)
const previewImg = ref('')

// 拖拽与缩放状态
const previewScale = ref(1)
const previewTranslate = ref({ x: 0, y: 0 })
const isDragging = ref(false)
const lastMouse = ref({ x: 0, y: 0 })
const dragStartMouse = ref({ x: 0, y: 0 })  // 用于判断是点击还是拖拽

// 遮盖编辑相关
const showEditDialog = ref(false)
const editImageUrl = ref('')
const editImageId = ref(null)
const editRects = ref([])
const drawingRect = ref(null)
const startPos = ref(null)
const editContainer = ref(null)

const onModeChange = () => { uploadStudentId.value = null }

const getImageUrl = (img) => {
  const filePath = img.processed_file_path || img.file_path
  let relative = filePath
  if (relative.startsWith('./')) relative = relative.slice(2)
  if (relative.startsWith('uploads/')) relative = relative.slice(8)
  return `/uploads/${relative}?r=${Math.random()}`
}

// 预览拖拽/缩放
const startDrag = (e) => {
  isDragging.value = true
  lastMouse.value = { x: e.clientX, y: e.clientY }
  dragStartMouse.value = { x: e.clientX, y: e.clientY }
}

const onDrag = (e) => {
  if (!isDragging.value) return
  const dx = e.clientX - lastMouse.value.x
  const dy = e.clientY - lastMouse.value.y
  previewTranslate.value.x += dx
  previewTranslate.value.y += dy
  lastMouse.value = { x: e.clientX, y: e.clientY }
}

const endDrag = () => {
  isDragging.value = false
}

// 判断鼠标移动距离，若<5px则视为点击图片关闭
const onImageMouseUp = (e) => {
  const dx = e.clientX - dragStartMouse.value.x
  const dy = e.clientY - dragStartMouse.value.y
  const distance = Math.sqrt(dx * dx + dy * dy)
  if (distance < 5) {
    closePreview()
  }
}

const onWheel = (e) => {
  const rect = e.currentTarget.getBoundingClientRect()
  const offsetX = e.clientX - rect.left
  const offsetY = e.clientY - rect.top
  const prevScale = previewScale.value
  const factor = e.deltaY < 0 ? 1.1 : 0.9
  const newScale = prevScale * factor
  previewScale.value = newScale
  previewTranslate.value.x = offsetX - (offsetX - previewTranslate.value.x) * (newScale / prevScale)
  previewTranslate.value.y = offsetY - (offsetY - previewTranslate.value.y) * (newScale / prevScale)
}

const resetTransform = () => {
  previewScale.value = 1
  previewTranslate.value = { x: 0, y: 0 }
}

const openPreview = (url) => {
  previewImg.value = url
  previewScale.value = 1
  previewTranslate.value = { x: 0, y: 0 }
  previewVisible.value = true
}

const closePreview = () => { previewVisible.value = false }

// 获取列表、上传、删除、排序等逻辑保持不变...
const fetchStudentImages = async () => {
  try {
    const studentsRes = await axios.get(`/api/exams/${props.examId}/students`)
    if (studentsRes.data.code !== 1) { ElMessage.error('获取学生列表失败'); return }
    const students = studentsRes.data.data

    const imagesRes = await axios.get(`/api/exams/${props.examId}/images`)
    if (imagesRes.data.code !== 1) { ElMessage.error('获取图片列表失败'); return }
    const images = imagesRes.data.data

    const imgMap = new Map()
    for (const img of images) {
      const sid = img.student.student_id
      if (!imgMap.has(sid)) imgMap.set(sid, [])
      imgMap.get(sid).push(img)
    }
    const list = students.map(student => {
      const studentImages = imgMap.get(student.student_id) || []
      const uniqueImages = []
      const seenIds = new Set()
      for (const img of studentImages) {
        if (!seenIds.has(img.id)) { seenIds.add(img.id); uniqueImages.push(img) }
      }
      uniqueImages.sort((a, b) => a.page_order - b.page_order)
      return { ...student, images: uniqueImages }
    })
    studentList.value = list
  } catch (error) { console.error('获取数据失败:', error); ElMessage.error('获取数据失败') }
}

const openUploadDialog = () => {
  if (!studentList.value.length) { ElMessage.warning('请先导入学生名单'); return }
  uploadStudentId.value = null; uploadFileList.value = []; showUploadDialog.value = true
}

const uploadImages = async () => {
  if (uploadFileList.value.length === 0) { ElMessage.error('请选择图片文件'); return }
  const formData = new FormData()
  for (const file of uploadFileList.value) { formData.append('files', file.raw) }
  if (autoMatchMode.value) { formData.append('auto_match', true) }
  else {
    if (!uploadStudentId.value) { ElMessage.error('请选择学生'); return }
    formData.append('student_ids', uploadStudentId.value)
  }
  uploadingSingle.value = true
  try {
    const response = await axios.post(`/api/exams/${props.examId}/images`, formData, { headers: { 'Content-Type': 'multipart/form-data' } })
    if (response.data.code === 1) {
      ElMessage.success(`上传成功，共 ${response.data.data.uploaded_count} 个文件`)
      showUploadDialog.value = false; uploadFileList.value = []; await fetchStudentImages()
    } else { ElMessage.error(response.data.msg || '上传失败') }
  } catch (error) { console.error('上传失败:', error); ElMessage.error('上传失败') }
  finally { uploadingSingle.value = false }
}

const deleteImage = async (imageId) => {
  try {
    await ElMessageBox.confirm('确定删除该图片吗？', '提示', { type: 'warning' })
    const response = await axios.delete(`/api/exams/${props.examId}/images/${imageId}`)
    if (response.data.code === 1) { ElMessage.success('删除成功'); await fetchStudentImages() }
    else { ElMessage.error(response.data.msg || '删除失败') }
  } catch (error) { if (error !== 'cancel') { console.error('删除失败:', error); ElMessage.error('删除失败') } }
}

const deleteAllImages = async (studentId, studentName) => {
  try {
    await ElMessageBox.confirm(`确定要删除 ${studentName} 的所有答题卡图片吗？此操作不可恢复。`, '警告', { confirmButtonText: '确定删除', cancelButtonText: '取消', type: 'warning' })
    const response = await axios.delete(`/api/exams/${props.examId}/students/${studentId}/images`)
    if (response.data.code === 1) { ElMessage.success(`已删除 ${studentName} 的所有图片`); await fetchStudentImages() }
    else { ElMessage.error(response.data.msg || '删除失败') }
  } catch (error) { if (error !== 'cancel') { console.error('批量删除失败:', error); ElMessage.error('批量删除失败') } }
}

const updateImageOrder = async (img) => {
  const formData = new FormData(); formData.append('page_order', img.page_order)
  try {
    const response = await axios.put(`/api/exams/${props.examId}/images/${img.id}`, formData, { headers: { 'Content-Type': 'multipart/form-data' } })
    if (response.data.code === 1) { ElMessage.success('顺序更新成功'); await fetchStudentImages() }
    else { ElMessage.error(response.data.msg || '更新失败'); await fetchStudentImages() }
  } catch (error) { console.error('更新顺序失败:', error); ElMessage.error('更新顺序失败'); await fetchStudentImages() }
}

const handleAddFile = async (file, studentId) => {
  const formData = new FormData(); formData.append('files', file.raw); formData.append('student_ids', studentId)
  try {
    const response = await axios.post(`/api/exams/${props.examId}/images`, formData, { headers: { 'Content-Type': 'multipart/form-data' } })
    if (response.data.code === 1) { ElMessage.success('图片添加成功'); await fetchStudentImages() }
    else { ElMessage.error(response.data.msg || '添加失败') }
  } catch (error) { console.error('添加图片失败:', error); ElMessage.error('添加图片失败') }
}

const fetchStudentList = async () => {
  try { await axios.get(`/api/exams/${props.examId}/students`) } catch (error) { console.error('获取学生列表失败', error) }
}

const handleImportFolder = async () => {
  const students = (props.students && props.students.length) ? props.students : studentList.value
  if (!students || students.length === 0) { ElMessage.error('请先导入学生名单'); return }
  const input = document.createElement('input'); input.type = 'file'; input.webkitdirectory = true; input.directory = true; input.multiple = true
  input.onchange = async (e) => {
    const files = Array.from(e.target.files)
    const imageFiles = files.filter(f => /\.(jpg|jpeg|png|bmp)$/i.test(f.name)).sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }))
    if (imageFiles.length === 0) { ElMessage.error('文件夹中没有图片文件'); return }
    const totalStudents = students.length; const imagesPerStudent = props.imagesPerStudent; const requiredImages = totalStudents * imagesPerStudent
    if (imageFiles.length < requiredImages) { ElMessage.error(`图片数量不足，需要 ${requiredImages} 张，实际 ${imageFiles.length} 张`); return }
    const groups = []; for (let i = 0; i < totalStudents; i++) { const student = students[i]; const startIdx = i * imagesPerStudent; const studentImages = imageFiles.slice(startIdx, startIdx + imagesPerStudent); groups.push({ studentId: student.student_id, files: studentImages }) }
    try { await ElMessageBox.confirm(`将为 ${totalStudents} 个学生各上传 ${imagesPerStudent} 张图片，共 ${requiredImages} 张。是否继续？`, '确认导入', { type: 'info' }) } catch { return }
    folderUploading.value = true; let successCount = 0; let failCount = 0
    for (const group of groups) {
      const formData = new FormData(); for (const file of group.files) { formData.append('files', file) }
      if (autoMatchMode.value) { formData.append('auto_match', true) } else { formData.append('student_ids', group.studentId) }
      try {
        const res = await axios.post(`/api/exams/${props.examId}/images`, formData, { headers: { 'Content-Type': 'multipart/form-data' } })
        if (res.data.code === 1) { successCount += group.files.length } else { failCount += group.files.length; console.error(`学生 ${group.studentId} 组上传失败:`, res.data.msg) }
      } catch (err) { failCount += group.files.length; console.error(`学生 ${group.studentId} 组上传异常:`, err) }
    }
    folderUploading.value = false; ElMessage.success(`上传完成：成功 ${successCount} 张，失败 ${failCount} 张`); await fetchStudentImages()
  }
  input.click()
}

// ================= 遮盖编辑 =================
const openEditDialog = (img) => {
  editImageId.value = img.id
  let filePath = img.processed_file_path || img.file_path
  if (filePath.startsWith('./')) filePath = filePath.slice(2)
  if (filePath.startsWith('uploads/')) filePath = filePath.slice(8)
  editImageUrl.value = `/uploads/${filePath}`
  editRects.value = []
  showEditDialog.value = true
}

const clearEdit = () => {
  editImageId.value = null
  editImageUrl.value = ''
  editRects.value = []
  drawingRect.value = null
  startPos.value = null
}

const undoRect = () => {
  editRects.value.pop()
}

const getOffset = (e) => {
  const el = editContainer.value
  if (!el) return { x: 0, y: 0 }
  const rect = el.getBoundingClientRect()
  return { x: e.clientX - rect.left, y: e.clientY - rect.top }
}

const startDraw = (e) => {
  startPos.value = getOffset(e)
  drawingRect.value = { ...startPos.value, w: 0, h: 0 }
}

const drawing = (e) => {
  if (!startPos.value || !drawingRect.value) return
  const cur = getOffset(e)
  drawingRect.value.x = Math.min(startPos.value.x, cur.x)
  drawingRect.value.y = Math.min(startPos.value.y, cur.y)
  drawingRect.value.w = Math.abs(startPos.value.x - cur.x)
  drawingRect.value.h = Math.abs(startPos.value.y - cur.y)
}

const endDraw = () => {
  if (drawingRect.value && drawingRect.value.w > 5 && drawingRect.value.h > 5) {
    editRects.value.push({ ...drawingRect.value })
  }
  drawingRect.value = null
  startPos.value = null
}

const saveEdit = async () => {
  if (!editImageId.value) return
  try {
    const el = editContainer.value
    if (!el) return
    const img = el.querySelector('img')
    if (!img) return
    const naturalWidth = img.naturalWidth
    const naturalHeight = img.naturalHeight
    const displayedWidth = img.clientWidth
    const displayedHeight = img.clientHeight
    const scaleX = naturalWidth / displayedWidth
    const scaleY = naturalHeight / displayedHeight

    const rects = editRects.value.map(rect => ({
      x: Math.round(rect.x * scaleX),
      y: Math.round(rect.y * scaleY),
      w: Math.round(rect.w * scaleX),
      h: Math.round(rect.h * scaleY)
    }))

    const response = await axios.post(
      `/api/exams/${props.examId}/images/${editImageId.value}/mask`,
      { rects },
      { headers: { 'Content-Type': 'application/json' } }
    )
    if (response.data.code === 1) {
      ElMessage.success('遮盖已更新')
      showEditDialog.value = false
      await fetchStudentImages()
    } else {
      ElMessage.error(response.data.msg || '保存失败')
    }
  } catch (error) {
    console.error('保存遮盖失败:', error)
    ElMessage.error('保存遮盖失败')
  }
}

const resetMask = async () => {
  if (!editImageId.value) return
  try {
    await ElMessageBox.confirm('确定要重置为未遮盖的预处理图吗？所有遮盖内容将丢失。', '提示', { type: 'warning' })
    const response = await axios.post(
      `/api/exams/${props.examId}/images/${editImageId.value}/reset-mask`
    )
    if (response.data.code === 1) {
      ElMessage.success('已重置')
      showEditDialog.value = false
      await fetchStudentImages()
    } else {
      ElMessage.error(response.data.msg || '重置失败')
    }
  } catch (error) {
    if (error !== 'cancel') {
      console.error('重置失败:', error)
      ElMessage.error('重置失败')
    }
  }
}

onMounted(() => { fetchStudentImages(); fetchStudentList() })
</script>

<style scoped>
.tab-actions { margin-bottom: 20px; display: flex; gap: 12px; }
.images-container { display: flex; flex-wrap: wrap; gap: 16px; align-items: flex-start; }
.image-item { width: 360px; border: 1px solid #e4e7ed; border-radius: 8px; padding: 8px; background: #fafafa; }
.image-thumb { width: 100%; height: auto; max-height: 400px; object-fit: contain; border-radius: 4px; cursor: pointer; display: block; }
.image-actions { display: flex; justify-content: space-between; align-items: center; margin-top: 8px; }
.image-filename { font-size: 12px; color: #909399; margin-top: 4px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>

<style>
/* 自定义预览遮罩 */
.preview-overlay {
  position: fixed; top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0, 0, 0, 0.9); z-index: 100000;
  display: flex; align-items: center; justify-content: center;
}
.preview-content {
  position: relative;
  width: 100%;
  height: 100%;
  overflow: hidden;
}
.preview-img {
  position: absolute;
  top: 0;
  left: 0;
  transform-origin: 0 0;
  user-select: none;
}
/* 右上角关闭按钮 */
.preview-close {
  position: absolute; top: 20px; right: 40px; font-size: 32px; color: #fff; cursor: pointer; z-index: 100001;
}
</style>