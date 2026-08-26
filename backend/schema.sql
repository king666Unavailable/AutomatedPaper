-- ============================================
-- 1. 用户表
-- ============================================
CREATE TABLE `users` (
  `user_id` int NOT NULL AUTO_INCREMENT,
  `username` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '用户名',
  `password_hash` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '密码哈希',
  `email` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '邮箱',
  `role` enum('admin','teacher','student') COLLATE utf8mb4_unicode_ci DEFAULT 'teacher' COMMENT '用户角色',
  `is_active` tinyint(1) DEFAULT '1' COMMENT '是否激活',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `last_login` timestamp NULL DEFAULT NULL COMMENT '最后登录时间',
  PRIMARY KEY (`user_id`),
  UNIQUE KEY `username` (`username`),
  UNIQUE KEY `email` (`email`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户信息表';

-- ============================================
-- 2. 考试表
-- ============================================
CREATE TABLE `exams` (
  `exam_id` int NOT NULL AUTO_INCREMENT,
  `exam_name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '考试名称',
  `description` text COLLATE utf8mb4_unicode_ci COMMENT '考试描述',
  `exam_date` datetime DEFAULT NULL COMMENT '开考时间',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `status` enum('created','uploading','processing','completed','graded') COLLATE utf8mb4_unicode_ci DEFAULT 'created' COMMENT '考试状态',
  `total_questions` int DEFAULT NULL COMMENT '总题数',
  `total_score` int DEFAULT NULL COMMENT '总分',
  `images_per_student` int NOT NULL DEFAULT '4' COMMENT '每个学生答题卡图片数量',
  `answer_sheet_layout` text COLLATE utf8mb4_unicode_ci COMMENT '答题卡布局JSON',
  `overall_analysis` text COLLATE utf8mb4_unicode_ci COMMENT '试卷整体分析',
  PRIMARY KEY (`exam_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='考试信息表';

-- ============================================
-- 3. 学生表
-- ============================================
CREATE TABLE `students` (
  `student_id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '学生姓名',
  `student_number` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '学号',
  `class` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '班级',
  `contact_info` text COLLATE utf8mb4_unicode_ci COMMENT '联系方式',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`student_id`),
  UNIQUE KEY `student_number` (`student_number`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='学生信息表';

-- ============================================
-- 4. 题目表
-- ============================================
CREATE TABLE `questions` (
  `id` int NOT NULL AUTO_INCREMENT,
  `type` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '题型',
  `content` text COLLATE utf8mb4_unicode_ci COMMENT '题目内容',
  `score` decimal(5,2) DEFAULT '0.00' COMMENT '分值',
  `reference_answer` text COLLATE utf8mb4_unicode_ci COMMENT '参考答案',
  `scoring_rules` text COLLATE utf8mb4_unicode_ci COMMENT '赋分规则',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `parent_id` int DEFAULT NULL COMMENT '所属大题ID，指向本表的id',
  `knowledge_point` text COLLATE utf8mb4_unicode_ci COMMENT '所属知识点',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='题目信息表';

-- ============================================
-- 5. 考试-题目关联表
-- ============================================
CREATE TABLE `exam_questions` (
  `id` int NOT NULL AUTO_INCREMENT,
  `question_id` int NOT NULL COMMENT '题目ID',
  `exam_id` int NOT NULL COMMENT '考试ID',
  `question_order` int NOT NULL COMMENT '题目序号',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_exam_question` (`exam_id`,`question_id`),
  UNIQUE KEY `unique_exam_order` (`exam_id`,`question_order`),
  KEY `question_id` (`question_id`),
  CONSTRAINT `exam_questions_ibfk_1` FOREIGN KEY (`question_id`) REFERENCES `questions` (`id`) ON DELETE CASCADE,
  CONSTRAINT `exam_questions_ibfk_2` FOREIGN KEY (`exam_id`) REFERENCES `exams` (`exam_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='考试题目关联表';

-- ============================================
-- 6. 考试-学生关联表
-- ============================================
CREATE TABLE `exam_students` (
  `exam_student_id` int NOT NULL AUTO_INCREMENT,
  `exam_id` int NOT NULL,
  `student_id` int NOT NULL,
  `assigned_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP COMMENT '分配时间',
  `sort_order` int DEFAULT '0' COMMENT '排序顺序',
  PRIMARY KEY (`exam_student_id`),
  UNIQUE KEY `unique_exam_student` (`exam_id`,`student_id`),
  KEY `idx_exam_students_exam_id` (`exam_id`),
  KEY `idx_exam_students_student_id` (`student_id`),
  CONSTRAINT `exam_students_ibfk_1` FOREIGN KEY (`exam_id`) REFERENCES `exams` (`exam_id`) ON DELETE CASCADE,
  CONSTRAINT `exam_students_ibfk_2` FOREIGN KEY (`student_id`) REFERENCES `students` (`student_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='考试学生关联表';

-- ============================================
-- 7. 答题卡图片表（当前实际使用的表）
-- ============================================
CREATE TABLE `answer_sheets` (
  `id` int NOT NULL AUTO_INCREMENT,
  `exam_id` int NOT NULL,
  `student_id` int NOT NULL,
  `filename` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '原始文件名',
  `file_path` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '图片存储路径',
  `uploaded_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `page_order` int NOT NULL DEFAULT '0' COMMENT '图片顺序（从0开始）',
  `processed_file_path` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '预处理后的图片路径',
  PRIMARY KEY (`id`),
  KEY `student_id` (`student_id`),
  KEY `idx_exam_student_order` (`exam_id`,`student_id`,`page_order`),
  CONSTRAINT `answer_sheets_ibfk_1` FOREIGN KEY (`exam_id`) REFERENCES `exams` (`exam_id`) ON DELETE CASCADE,
  CONSTRAINT `answer_sheets_ibfk_2` FOREIGN KEY (`student_id`) REFERENCES `students` (`student_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='学生答题图片表';

-- ============================================
-- 8. 答题卡图片表（旧表/未使用）
-- 注意：代码中并未使用该表，建议删除。
-- ============================================
CREATE TABLE `answer_images` (
  `id` int NOT NULL AUTO_INCREMENT,
  `exam_id` int NOT NULL,
  `student_id` int NOT NULL,
  `image_path` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '图片存储路径',
  `original_filename` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '原始文件名',
  `uploaded_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `exam_id` (`exam_id`),
  KEY `student_id` (`student_id`),
  CONSTRAINT `answer_images_ibfk_1` FOREIGN KEY (`exam_id`) REFERENCES `exams` (`exam_id`) ON DELETE CASCADE,
  CONSTRAINT `answer_images_ibfk_2` FOREIGN KEY (`student_id`) REFERENCES `students` (`student_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='学生答题图片表（旧）';

-- ============================================
-- 9. 学生成绩明细表（当前实际使用）
-- ============================================
CREATE TABLE `student_scores` (
  `id` int NOT NULL AUTO_INCREMENT,
  `exam_id` int NOT NULL,
  `student_id` int NOT NULL,
  `question_id` int NOT NULL,
  `score` decimal(5,2) NOT NULL,
  `feedback` text COLLATE utf8mb4_unicode_ci COMMENT '评语',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `student_answer` text COLLATE utf8mb4_unicode_ci COMMENT '学生答案',
  `recognition_correct` tinyint(1) DEFAULT '1' COMMENT '识别结果人工标注：1正确，0错误',
  `corrected_answer` text COLLATE utf8mb4_unicode_ci COMMENT '人工修正后的学生答案',
  `manual_reviewed` tinyint(1) DEFAULT '0' COMMENT '是否已在人工阅卷界面查看过：1已查看，0未查看',
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_scoring` (`exam_id`,`student_id`,`question_id`),
  KEY `student_id` (`student_id`),
  KEY `question_id` (`question_id`),
  CONSTRAINT `student_scores_ibfk_1` FOREIGN KEY (`exam_id`) REFERENCES `exams` (`exam_id`) ON DELETE CASCADE,
  CONSTRAINT `student_scores_ibfk_2` FOREIGN KEY (`student_id`) REFERENCES `students` (`student_id`) ON DELETE CASCADE,
  CONSTRAINT `student_scores_ibfk_3` FOREIGN KEY (`question_id`) REFERENCES `questions` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================
-- 10. 成绩明细表（旧表/未使用）
-- 注意：代码中所有操作都走 student_scores，该表可删除。
-- ============================================
CREATE TABLE `scores` (
  `id` int NOT NULL AUTO_INCREMENT,
  `exam_id` int NOT NULL,
  `student_id` int NOT NULL,
  `question_id` int NOT NULL,
  `score` decimal(5,2) NOT NULL COMMENT '得分',
  `feedback` text COLLATE utf8mb4_unicode_ci COMMENT '评语',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_scoring` (`exam_id`,`student_id`,`question_id`),
  KEY `student_id` (`student_id`),
  KEY `question_id` (`question_id`),
  CONSTRAINT `scores_ibfk_1` FOREIGN KEY (`exam_id`) REFERENCES `exams` (`exam_id`) ON DELETE CASCADE,
  CONSTRAINT `scores_ibfk_2` FOREIGN KEY (`student_id`) REFERENCES `students` (`student_id`) ON DELETE CASCADE,
  CONSTRAINT `scores_ibfk_3` FOREIGN KEY (`question_id`) REFERENCES `questions` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='考试成绩明细表（旧）';

-- ============================================
-- 11. AI阅卷任务表
-- ============================================
CREATE TABLE `grading_jobs` (
  `id` int NOT NULL AUTO_INCREMENT,
  `exam_id` int NOT NULL,
  `status` enum('pending','processing','completed','failed') COLLATE utf8mb4_unicode_ci DEFAULT 'pending',
  `total_students` int DEFAULT '0',
  `processed_students` int DEFAULT '0',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `exam_id` (`exam_id`),
  CONSTRAINT `grading_jobs_ibfk_1` FOREIGN KEY (`exam_id`) REFERENCES `exams` (`exam_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='AI阅卷任务记录表';

-- ============================================
-- 12. 题型分析表
-- ============================================
CREATE TABLE `exam_type_analyses` (
  `id` int NOT NULL AUTO_INCREMENT,
  `exam_id` int NOT NULL,
  `question_type` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '题型',
  `analysis` text COLLATE utf8mb4_unicode_ci COMMENT '题型分析内容',
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_exam_type` (`exam_id`,`question_type`),
  KEY `exam_id` (`exam_id`),
  CONSTRAINT `exam_type_analyses_ibfk_1` FOREIGN KEY (`exam_id`) REFERENCES `exams` (`exam_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='题型分析表';