# 试卷图片分析和AI阅卷实验平台 (Automated Paper Grading & Analysis Platform)

## 项目简介
本项目是一个基于 **Vue 3**、**FastAPI** 和 **MySQL** 的试卷管理与 AI 阅卷平台，提供考试、学生、题目和答题卡管理，以及 AI 阅卷、主观题人工阅卷、成绩管理和考试分析功能。

## 系统架构
项目采用前后端分离架构：
- **前端**：基于 **Vue 3** + **Vite** 构建，使用 **Element Plus** 组件库实现现代化的用户界面。负责数据的展示、交互以及考试流程的管理。
- **后端**：基于 **Python 3.9** + **FastAPI** 构建。提供高性能的 RESTful API，处理业务逻辑、数据持久化以及未来的AI算法集成。
- **数据库**：使用 **MySQL** 存储考试信息、学生数据、题目详情及阅卷结果。


## 目录结构说明

```text
AutomatedPaper/
├── backend/                # 后端代码目录
│   ├── app_main.py         # 后端核心入口文件，集成所有路由
│   ├── config.py           # 配置文件（从 .env 加载数据库和模型配置）
│   ├── database.py         # 数据库连接初始化
│   ├── schema.sql          # 数据库初始化脚本
│   ├── requirements.txt    # Python依赖包列表
│   └── routers/            # 路由模块 (按功能拆分)
│       ├── auth.py         # 用户认证 (登录/注册)
│       ├── exams.py        # 考试管理 (创建/更新/删除)
│       ├── students.py     # 学生管理 & 考试学生关联
│       ├── questions.py    # 题目管理 & 考试题目关联
│       ├── answers.py      # 答题卡图片管理
│       ├── grading.py      # AI阅卷
│       ├── scores.py       # 成绩与主观题人工阅卷
│       └── analysis.py     # 考试分析
├── frontend/               # 前端代码目录
│   ├── src/
│   │   ├── views/          # 页面组件
│   │   │   ├── ExamDetail.vue        # 考试详情页（核心功能入口）
│   │   │   ├── home/                 # 首页相关
│   │   │   └── exam/                 # 考试功能子模块
│   │   │       ├── StudentManager.vue    # 学生信息管理
│   │   │       ├── QuestionManager.vue   # 题目与参考答案管理
│   │   │       ├── AnswerManager.vue     # 学生作答管理
│   │   │       ├── AIGradingConsole.vue  # AI阅卷与答题详情
│   │   │       └── ScoreManager.vue      # 成绩管理、主观题阅卷和考试分析
│   └── ...
└── README.md               # 项目说明文档
```

## 关键功能代码导读
本项目的核心逻辑集中在后端的 `routers/` 目录和前端的 `views/exam/` 目录下。以下是关键功能的代码出处对照，方便开发者快速定位和修改：

### 1. 考试管理模块
*   **后端实现**: `backend/routers/exams.py`
    *   `get_exams()`: 获取考试列表。
    *   `create_exam()`: 创建新考试。
    *   `update_exam()`: 更新考试信息（如状态流转）。
*   **前端实现**: `frontend/src/views/home/examlist.vue` (考试列表页)

### 2. 学生信息与导入模块
*   **后端实现**: `backend/routers/students.py`
    *   `import_students_from_file()`: **核心函数**。使用 `pandas` 解析 Excel/CSV 或 Python 字符串处理解析 TXT，提取学生名单。
    *   `batch_add_students_to_exam()`: 处理批量添加及学号查重逻辑。
    *   `get_available_students()`: 获取学生池中未分配到当前考试的学生。
*   **前端实现**: `frontend/src/views/exam/StudentManager.vue`
    *   实现了文件上传组件与后端交互，以及学生列表的展示与管理。

### 3. 题目管理与文档解析模块
*   **后端实现**: `backend/routers/questions.py`
    *   `import_questions_from_file()`: **核心函数**。
        *   使用 `python-docx` 库解析 Word 文档，识别题目内容、分值和答案。
        *   使用 `pandas` 解析 Excel 题库。
        *   包含简单的正则表达式逻辑，用于提取题目结构（如 `@@@` 分隔符处理）。
    *   `reorder_exam_questions()`: 处理题目序号的重新排列。
    *   `get_available_questions()`: 获取题库中未分配到当前考试的题目。
*   **前端实现**: `frontend/src/views/exam/QuestionManager.vue`
    *   提供题目预览、手动编辑、文件导入以及从题库选择题目的入口。

### 4. 答题卡图片管理模块
*   **后端实现**: `backend/routers/answers.py`
    *   `upload_exam_images()`: 接收前端上传的学生答卷图片，并保存到服务器。
    *   `get_exam_images()`: 获取已上传的图片列表。
*   **前端实现**: `frontend/src/views/exam/AnswerManager.vue`
    *   提供图片上传组件，支持多文件选择和上传进度展示。

### 5. AI 阅卷与成绩模块
*   **后端实现**:
    *   `backend/routers/grading.py`: `start_grading()` - 触发AI阅卷流程（OCR + 评分）。
    *   `backend/routers/scores.py`: `get_exam_scores()` - 获取阅卷结果和统计数据。
*   **前端实现**:
    *   `frontend/src/views/exam/AIGradingConsole.vue`: 控制阅卷流程，展示进度。
    *   `frontend/src/views/exam/ScoreManager.vue`: 展示成绩表格和详情。

## 数据库设计说明
项目使用 MySQL 关系型数据库，当前有效表结构定义在 `backend/schema.sql` 中（项目根目录下的 `database_schema.sql` 已滞后，初始化请使用 `backend/schema.sql`）。

| 表名 | 中文名 | 描述 | 关键字段 |
| :--- | :--- | :--- | :--- |
| **exams** | 考试表 | 存储考试的基本元数据和整体分析 | `exam_id` (PK), `status` (状态), `images_per_student` (每生图片数，默认 2), `answer_sheet_layout` (答题卡布局 JSON), `overall_analysis` |
| **students** | 学生表 | 全局学生信息库，不依附于特定考试 | `student_id` (PK), `student_number` (Unique 学号), `class` (班级) |
| **exam_students** | 考试-学生关联表 | **多对多关系表**。记录某次考试有哪些学生参加 | `exam_id` (FK), `student_id` (FK), `sort_order` (考场排序) |
| **questions** | 题目表 | 题目库，存储题目内容、分值、标准答案、评分规则和知识点 | `id` (PK), `content`, `reference_answer`, `scoring_rules`, `score`, `knowledge_point` |
| **exam_questions** | 考试-题目关联表 | **多对多关系表**。定义某次考试包含哪些题目及顺序 | `exam_id` (FK), `question_id` (FK), `question_order` (题号) |
| **answer_sheets** | 答题卡图片表 | 存储学生上传的答题卡图片路径及预处理后的图片路径 | `id` (PK), `exam_id`, `student_id`, `filename`, `file_path`, `processed_file_path`, `page_order` |
| **student_scores** | 学生成绩明细表 | 存储每名学生每道题的得分、OCR 结果和人工复核信息 | `score`, `student_answer`, `recognition_correct`, `corrected_answer`, `manual_reviewed` |
| **grading_jobs** | AI阅卷任务表 | 记录 AI 阅卷任务的进度和状态 | `id` (PK), `exam_id`, `status`, `total_students`, `processed_students` |
| **exam_type_analyses** | 题型分析表 | 保存每场考试各题型的分析文本 | `exam_id`, `question_type`, `analysis` |
| **users** | 用户表 | 教师/管理员登录认证 | `user_id` (PK), `username`, `password_hash`, `role` |

> **设计思路**: `students` 和 `questions` 表设计为**全局资源池**。
> *   同一个学生可以参加多个 `exams` (通过 `exam_students` 关联)。
> *   同一道题目可以被多场 `exams` 复用（通过 `exam_questions` 关联），方便组卷。
> *   `student_scores.student_answer` 保存 AI/OCR 识别的原始答案；`corrected_answer` 保存人工修正答案，不覆盖原始识别结果；`recognition_correct` 用于标注识别结果是否正确，`manual_reviewed` 记录主观题人工阅卷是否已查看。


## 技术栈
### 后端
- **Language**: Python 3.9
- **Framework**: FastAPI
- **Database**: MySQL + SQLAlchemy
- **Data Processing**: Pandas, Python-docx

### 前端
- **Framework**: Vue.js 3 + Vite
- **UI Library**: Element Plus
- **HTTP Client**: Axios

## 快速开始

### 1. 环境准备
确保本地已安装以下环境：
- Python 3.9 (建议使用 Miniconda 或 Anaconda)
- Node.js (LTS 版本)
- MySQL (5.7 或 8.0)

### 2. 数据库配置
1. 登录 MySQL，创建一个名为 `exam_platform` 的数据库。
   ```sql
   CREATE DATABASE exam_platform CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   ```
2. 运行 `backend/schema.sql` 脚本，初始化表结构。
   ```bash
   mysql -u root -p exam_platform < backend/schema.sql
   ```

### 3. 后端部署
1. 进入后端目录：
   ```bash
   cd backend
   ```
2. 创建并激活 Python 虚拟环境（推荐）：
   ```bash
   conda create -n automated_paper python=3.9
   conda activate automated_paper
   ```
3. 安装依赖包：
   ```bash
   pip install -r requirements.txt
   ```
4. **配置环境变量**：
   项目根目录下已提供 `.env.example` 模板，复制为 `.env` 后填入你的本地配置：
   ```bash
   cp .env.example .env
   ```
   然后编辑 `.env` 文件：
   ```env
   # 数据库配置
   DB_HOST=localhost
   DB_USER=root
   DB_PASSWORD=your_password  # <--- 修改为你的 MySQL 密码
   DB_NAME=exam_platform

   # 多模态模型 API 配置（AI 阅卷需要）
   MM_API_KEY=your_api_key  # <--- 替换为你的 API Key
   ```
   > `.env` 文件已被 `.gitignore` 忽略，不会提交到版本控制，避免泄露密码和 API Key。
5. 启动后端服务：
   ```bash
   python app_main.py
   ```
   服务将运行在 `http://0.0.0.0:8001`。

### 4. 前端部署
1. 打开一个新的终端窗口，进入前端目录：
   ```bash
   cd frontend
   ```
2. 安装 Node.js 依赖：
   ```bash
   npm install
   ```
3. 启动开发服务器：
   ```bash
   npm run dev
   ```
   访问控制台输出的本地地址（通常是 `http://localhost:5173`）即可使用系统。

## 当前功能

- 考试、学生和题目管理，支持学生及题目文件导入。
- 答题卡图片上传、预处理、页面排序和学生匹配。
- AI 阅卷、学生答案与识别结果复核、按学生重新阅卷。
- 主观题人工阅卷、成绩查看与导出。
- 考试分析：题目得分统计、知识点记录、题型分析和整卷分析。





