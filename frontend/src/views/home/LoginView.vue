<template>
  <div class="login-container">
    <div class="background-shapes">
      <div class="shape shape-1"></div>
      <div class="shape shape-2"></div>
      <div class="shape shape-3"></div>
    </div>
    
    <el-card class="login-card" shadow="hover">
      <div class="card-header">
        <div class="logo-container">
          <el-icon class="logo-icon" :size="40" color="#409EFF"><Reading /></el-icon>
        </div>
        <h2 class="login-title">自动阅卷系统</h2>
        <p class="login-subtitle">智能 · 高效 · 便捷</p>
      </div>
      
      <el-form @submit.prevent="handleLogin" size="large">
        <el-form-item>
          <el-input 
            v-model="username" 
            placeholder="账号" 
            prefix-icon="User"
            clearable 
          />
        </el-form-item>
        
        <el-form-item>
          <el-input 
            v-model="password" 
            type="password" 
            placeholder="密码" 
            prefix-icon="Lock"
            show-password 
            @keyup.enter="handleLogin"
          />
        </el-form-item>

        <div class="action-buttons">
          <el-button type="primary" class="full-width submit-btn" @click="handleLogin" :loading="loading" round>
            登 录
          </el-button>
          <div class="link-buttons">
            <el-button link type="primary" @click="showRegister = true">
              注册新账号
            </el-button>
            <el-button link type="info">忘记密码?</el-button>
          </div>
        </div>
      </el-form>

      <transition name="el-fade-in">
        <el-alert
          v-if="error"
          :title="error"
          type="error"
          show-icon
          :closable="false"
          class="mt-3 custom-alert"
        />
      </transition>
    </el-card>

    <!-- 注册对话框 -->
    <el-dialog 
      v-model="showRegister" 
      title="注册账号" 
      width="420px"
      :close-on-click-modal="false"
      class="register-dialog"
      align-center
    >
      <el-form 
        ref="registerFormRef"
        :model="registerForm"
        :rules="registerRules"
        label-width="80px"
        status-icon
        size="large"
      >
        <el-form-item label="账号" prop="username">
          <el-input v-model="registerForm.username" placeholder="设置账号 (1-50字符)" prefix-icon="User" />
        </el-form-item>
        
        <el-form-item label="邮箱" prop="email">
          <el-input v-model="registerForm.email" placeholder="电子邮箱 (可选)" prefix-icon="Message" />
        </el-form-item>

        <el-form-item label="密码" prop="password">
          <el-input 
            v-model="registerForm.password" 
            type="password" 
            placeholder="设置密码" 
            show-password
            prefix-icon="Lock"
          />
        </el-form-item>
        
        <el-form-item label="确认" prop="confirmPassword">
          <el-input 
            v-model="registerForm.confirmPassword" 
            type="password" 
            placeholder="再次输入密码" 
            show-password
            prefix-icon="Check"
          />
        </el-form-item>
      </el-form>
      
      <div v-if="regError" class="error-text mb-2">
        <el-icon><Warning /></el-icon> {{ regError }}
      </div>
      <div v-if="regSuccess" class="success-text mb-2">
        <el-icon><CircleCheck /></el-icon> {{ regSuccess }}
      </div>

      <template #footer>
        <span class="dialog-footer">
          <el-button @click="closeRegister">取消</el-button>
          <el-button type="primary" @click="handleRegister" :loading="regLoading">
            立即注册
          </el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import axios from 'axios'
import { User, Lock, Reading, Message, Check, Warning, CircleCheck } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

const router = useRouter()
const username = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)

// 注册相关
const showRegister = ref(false)
const regLoading = ref(false)
const regError = ref('')
const regSuccess = ref('')
const registerFormRef = ref(null)

const registerForm = reactive({
  username: '',
  email: '',
  password: '',
  confirmPassword: ''
})

// 密码验证规则
const validatePass = (rule, value, callback) => {
  if (value === '') {
    callback(new Error('请输入密码'))
  } else {
    if (registerForm.confirmPassword !== '') {
      if (!registerFormRef.value) return
      registerFormRef.value.validateField('confirmPassword', () => null)
    }
    callback()
  }
}

const validatePass2 = (rule, value, callback) => {
  if (value === '') {
    callback(new Error('请再次输入密码'))
  } else if (value !== registerForm.password) {
    callback(new Error('两次输入密码不一致!'))
  } else {
    callback()
  }
}

const registerRules = reactive({
  username: [
    { required: true, message: '请输入账号', trigger: 'blur' },
    { min: 1, max: 50, message: '长度在 1 到 50 个字符', trigger: 'blur' }
  ],
  password: [
    { required: true, validator: validatePass, trigger: 'blur' }
  ],
  confirmPassword: [
    { required: true, validator: validatePass2, trigger: 'blur' }
  ]
})

const handleLogin = async () => {
  if (!username.value || !password.value) {
    error.value = '请输入账号和密码'
    return
  }
  
  loading.value = true
  error.value = ''
  
  try {
    const response = await axios.post('/api/login', {
      username: username.value,
      password: password.value
    })
    
    if (response.data.code === 1) {
      localStorage.setItem('username', username.value)
      ElMessage.success('登录成功')
      router.push('/home')
    } else {
      error.value = response.data.msg || '登录失败'
    }
  } catch (e) {
    error.value = e.response?.data?.detail || '登录失败，请检查账号密码'
  } finally {
    loading.value = false
  }
}

const handleRegister = async () => {
  if (!registerFormRef.value) return
  
  await registerFormRef.value.validate(async (valid) => {
    if (valid) {
      regLoading.value = true
      regError.value = ''
      regSuccess.value = ''
      
      try {
        const response = await axios.post('/api/register', {
          username: registerForm.username,
          password: registerForm.password,
          email: registerForm.email || undefined
        })
        
        if (response.data.code === 1) {
          regSuccess.value = '注册成功，即将自动填充账号'
          ElMessage.success('注册成功')
          
          setTimeout(() => {
            showRegister.value = false
            username.value = registerForm.username
            password.value = ''
            registerFormRef.value.resetFields()
            regSuccess.value = ''
          }, 1500)
        } else {
          regError.value = response.data.msg || '注册失败'
        }
      } catch (e) {
        regError.value = e.response?.data?.detail || '注册失败，请稍后重试'
      } finally {
        regLoading.value = false
      }
    }
  })
}

const closeRegister = () => {
  showRegister.value = false
  registerFormRef.value?.resetFields()
  regError.value = ''
  regSuccess.value = ''
}
</script>

<style scoped>
.login-container {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
  width: 100vw;
  position: relative;
  overflow: hidden;
  background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
}

/* Animated Background Shapes */
.background-shapes {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  overflow: hidden;
  z-index: 0;
}

.shape {
  position: absolute;
  border-radius: 50%;
  opacity: 0.4;
  filter: blur(60px);
  animation: float 15s infinite ease-in-out;
}

.shape-1 {
  top: -10%;
  left: -10%;
  width: 500px;
  height: 500px;
  background: linear-gradient(to right, #4facfe 0%, #00f2fe 100%);
  animation-delay: 0s;
}

.shape-2 {
  bottom: -10%;
  right: -5%;
  width: 400px;
  height: 400px;
  background: linear-gradient(to right, #43e97b 0%, #38f9d7 100%);
  animation-delay: -5s;
}

.shape-3 {
  top: 40%;
  left: 40%;
  width: 300px;
  height: 300px;
  background: linear-gradient(to right, #fa709a 0%, #fee140 100%);
  animation-delay: -10s;
}

@keyframes float {
  0% { transform: translate(0, 0) rotate(0deg); }
  33% { transform: translate(30px, -50px) rotate(10deg); }
  66% { transform: translate(-20px, 20px) rotate(-5deg); }
  100% { transform: translate(0, 0) rotate(0deg); }
}

/* Card Styling */
.login-card {
  width: 100%;
  max-width: 420px;
  background: rgba(255, 255, 255, 0.85);
  backdrop-filter: blur(20px);
  border-radius: 16px;
  border: 1px solid rgba(255, 255, 255, 0.6);
  box-shadow: 0 8px 32px rgba(31, 38, 135, 0.15);
  z-index: 1;
  padding: 20px 10px;
}

.card-header {
  text-align: center;
  margin-bottom: 30px;
}

.logo-container {
  width: 70px;
  height: 70px;
  background: #eff6ff;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 16px;
  box-shadow: 0 4px 12px rgba(64, 158, 255, 0.2);
}

.login-title {
  color: #2c3e50;
  margin: 0 0 8px;
  font-size: 28px;
  font-weight: 700;
  letter-spacing: 1px;
}

.login-subtitle {
  color: #909399;
  margin: 0;
  font-size: 14px;
  letter-spacing: 3px;
}

/* Form Styling */
.action-buttons {
  margin-top: 10px;
}

.submit-btn {
  height: 44px;
  font-size: 16px;
  font-weight: 600;
  letter-spacing: 2px;
  transition: all 0.3s ease;
}

.submit-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(64, 158, 255, 0.4);
}

.link-buttons {
  display: flex;
  justify-content: space-between;
  margin-top: 16px;
}

.full-width {
  width: 100%;
}

.mt-3 {
  margin-top: 16px;
}

.mb-2 {
  margin-bottom: 8px;
}

.error-text {
  color: #f56c6c;
  font-size: 14px;
  text-align: center;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  background: #fef0f0;
  padding: 8px;
  border-radius: 4px;
}

.success-text {
  color: #67c23a;
  font-size: 14px;
  text-align: center;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  background: #f0f9eb;
  padding: 8px;
  border-radius: 4px;
}

/* Custom Alert */
.custom-alert {
  border-radius: 8px;
}

/* Responsive */
@media (max-width: 480px) {
  .login-card {
    max-width: 90%;
    padding: 10px 5px;
  }
}
</style>