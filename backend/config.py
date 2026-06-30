import os
from dotenv import load_dotenv

# 加载 .env 文件中的环境变量
load_dotenv()

# 数据库配置
DATABASE_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', ''),
    'database': os.getenv('DB_NAME', 'exam_platform')
}


# 上传目录
UPLOAD_DIR = "./uploads"

# 多模态模型 API 配置
MM_MODEL_CONFIG = {
    "provider": "qwen",
    "api_key": os.getenv('MM_API_KEY', ''),  # 在 .env 中配置
    "api_url": os.getenv(
        'MM_API_URL',
        'https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation'
    ),
    "model": os.getenv('MM_MODEL', 'qwen-vl-plus'),  # 或 qwen-vl-max
    "timeout": int(os.getenv('MM_TIMEOUT', '30')),
    "max_retries": int(os.getenv('MM_MAX_RETRIES', '2'))
}
