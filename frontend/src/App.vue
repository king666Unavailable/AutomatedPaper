<script setup>
import { ref, onMounted } from 'vue'
import axios from 'axios'

const students = ref([])

onMounted(async () => {
  try {
  const res = await axios.get('/api/students')
    students.value = res.data.data || []
  } catch (e) {
    console.error('获取学生列表失败', e)
    students.value = []
  }
})
</script>

<template>
  <Background />
  <router-view />
</template>

<style scoped>
.app-container {
  font-family: 'Microsoft YaHei', Arial, sans-serif;
  background: #f7f8fa;
  min-height: 100vh;
}
.navbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: #23395d;
  color: #fff;
  padding: 0 32px;
  height: 56px;
}
.navbar-title {
  font-size: 1.4rem;
  font-weight: bold;
}
.navbar-actions {
  display: flex;
  align-items: center;
  gap: 16px;
}
.logout-btn {
  background: #f39c12;
  color: #fff;
  border: none;
  padding: 6px 16px;
  border-radius: 4px;
  cursor: pointer;
}
.main-content {
  display: flex;
  height: calc(100vh - 56px);
}
.sidebar {
  width: 220px;
  background: #fff;
  border-right: 1px solid #e0e0e0;
  padding: 16px 0;
  display: flex;
  flex-direction: column;
  align-items: stretch;
}
.switch-mode {
  display: flex;
  justify-content: space-around;
  margin-bottom: 16px;
}
.switch-mode button {
  flex: 1;
  margin: 0 4px;
  padding: 8px 0;
  border: none;
  background: #e0e0e0;
  color: #23395d;
  font-weight: bold;
  border-radius: 4px;
  cursor: pointer;
  transition: background 0.2s;
}
.switch-mode button.active {
  background: #23395d;
  color: #fff;
}
.list-container {
  flex: 1;
  overflow-y: auto;
}
.list-container ul {
  list-style: none;
  padding: 0;
  margin: 0;
}
.list-container li {
  padding: 10px 24px;
  cursor: pointer;
  border-left: 4px solid transparent;
  transition: background 0.2s, border-color 0.2s;
}
.list-container li.selected {
  background: #f0f4fa;
  border-left: 4px solid #f39c12;
  font-weight: bold;
}
.detail-area {
  flex: 1;
  padding: 32px 40px;
  background: #f7f8fa;
  overflow-y: auto;
}
</style>