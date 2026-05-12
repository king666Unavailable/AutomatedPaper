from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends, Body
from typing import List, Optional
import logging
import os
import time
import shutil
import cv2
import numpy as np
import json
import base64
import re
import requests
from sqlalchemy import text
from sqlalchemy.orm import Session
from backend.database import get_db
from PIL import Image, ExifTags

logger = logging.getLogger(__name__)

from backend.database import engine
from backend.config import UPLOAD_DIR, MM_MODEL_CONFIG

router = APIRouter()

ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp'}


def is_allowed_file(filename: str) -> bool:
    ext = os.path.splitext(filename)[1].lower()
    return ext in ALLOWED_EXTENSIONS


def ensure_upload_dir(exam_id: int) -> str:
    target_dir = os.path.join(UPLOAD_DIR, "answer_sheets", str(exam_id))
    os.makedirs(target_dir, exist_ok=True)
    return target_dir


# ==================== 答题卡预处理函数 ====================
def auto_orient(image: np.ndarray, image_path: str) -> np.ndarray:
    """
    智能方向纠正：如果宽高比异常，则用模型检测文字方向，并根据结果旋转。
    参数 image_path 用于模型识别（仅当宽高比异常时调用）。
    """
    h, w = image.shape[:2]
    # 仅当宽明显大于高时才检查文字方向，避免不必要的模型调用
    if w > h * 1.2:
        orientation = detect_text_orientation(image_path)
        if orientation == 'rotated_left':
            # 文字逆时针旋转90度，图片需要顺时针旋转90度
            # 假设原图文字是逆时针转90度的
            # 需要顺时针旋转90度才能让文字水平。这里我们用 cv2.ROTATE_90_CLOCKWISE
            logger.info("检测到文字逆时针旋转90度，进行顺时针90度校正")
            image = cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
        elif orientation == 'rotated_right':
            logger.info("检测到文字顺时针旋转90度，进行逆时针90度校正")
            image = cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)
        # normal 或 未知则不旋转
    return image

def correct_exif_orientation(image_path: str) -> np.ndarray:
    """
    根据图片的EXIF旋转信息自动转正，返回BGR格式图像。
    如果无法读取或没有旋转信息，返回原图。
    """
    try:
        pil_img = Image.open(image_path)
        # 检查EXIF中的方向标签
        exif = pil_img._getexif()
        if exif is not None:
            orientation = exif.get(0x0112)  # 0x0112 = Orientation tag
            if orientation:
                # 根据方向值旋转/翻转
                if orientation == 2:
                    pil_img = pil_img.transpose(Image.FLIP_LEFT_RIGHT)
                elif orientation == 3:
                    pil_img = pil_img.rotate(180, expand=True)
                elif orientation == 4:
                    pil_img = pil_img.transpose(Image.FLIP_TOP_BOTTOM)
                elif orientation == 5:
                    pil_img = pil_img.rotate(-90, expand=True).transpose(Image.FLIP_LEFT_RIGHT)
                elif orientation == 6:
                    pil_img = pil_img.rotate(-90, expand=True)   # 常见：顺时针90度转正
                elif orientation == 7:
                    pil_img = pil_img.rotate(90, expand=True).transpose(Image.FLIP_LEFT_RIGHT)
                elif orientation == 8:
                    pil_img = pil_img.rotate(90, expand=True)
                # 其他值不处理
        # 转为OpenCV BGR格式
        pil_img = pil_img.convert('RGB')
        open_cv_image = np.array(pil_img)
        open_cv_image = cv2.cvtColor(open_cv_image, cv2.COLOR_RGB2BGR)
        return open_cv_image
    except Exception as e:
        # 如果读取失败，回退到cv2.imread
        logger.warning(f"EXIF校正失败: {e}，使用cv2.imread")
        return cv2.imread(image_path)

def deskew_image(image: np.ndarray) -> np.ndarray:
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image.copy()

    edges = cv2.Canny(gray, 50, 150, apertureSize=3)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=100,
                            minLineLength=100, maxLineGap=10)
    angles = []
    if lines is not None:
        for line in lines:
            x1, y1, x2, y2 = line[0]
            angle = np.arctan2(y2 - y1, x2 - x1) * 180.0 / np.pi
            if -45 < angle < 45:
                angles.append(angle)

    if not angles:
        logger.info("未检测到有效水平线段，跳过倾斜校正")
        return image

    median_angle = np.median(angles)
    logger.info(f"检测到倾斜角度: {median_angle:.2f}°")

    if abs(median_angle) < 0.5:
        return image

    h, w = image.shape[:2]
    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, median_angle, 1.0)
    rotated = cv2.warpAffine(image, M, (w, h),
                             borderMode=cv2.BORDER_CONSTANT,
                             borderValue=(255, 255, 255))
    return rotated


def enhance_text_clarity(gray: np.ndarray) -> np.ndarray:
    clahe = cv2.createCLAHE(clipLimit=1.5, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    denoised = cv2.bilateralFilter(enhanced, 5, 30, 30)
    kernel_sharpen = np.array([[-0.5, -1, -0.5],
                               [-1, 7, -1],
                               [-0.5, -1, -0.5]])
    sharpened = cv2.filter2D(denoised, -1, kernel_sharpen)
    sharpened = np.clip(sharpened, 0, 255).astype(np.uint8)
    return sharpened


def detect_and_remove_strikethroughs(gray: np.ndarray) -> np.ndarray:
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    kernel_h = cv2.getStructuringElement(cv2.MORPH_RECT, (30, 1))
    horizontal = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel_h)

    kernel_v = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 30))
    vertical = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel_v)

    kernel_smear = cv2.getStructuringElement(cv2.MORPH_RECT, (18, 18))
    smear = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel_smear)

    strikethrough = cv2.bitwise_or(horizontal, vertical)
    strikethrough = cv2.bitwise_or(strikethrough, smear)

    kernel_dilate = np.ones((3, 3), np.uint8)
    strikethrough = cv2.dilate(strikethrough, kernel_dilate, iterations=1)

    contours, _ = cv2.findContours(strikethrough, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    mask = np.zeros_like(gray)
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < 80:
            continue
        x, y, w, h = cv2.boundingRect(cnt)
        aspect_ratio = max(w / h, h / w) if h > 0 else 999
        if area > 600 or (aspect_ratio > 4 and area > 200):
            cv2.drawContours(mask, [cnt], -1, 255, -1)

    cleaned_gray = cv2.inpaint(gray, mask, 5, cv2.INPAINT_TELEA)
    return cleaned_gray


def detect_regions_with_vlm(image_path: str, questions_per_section: List[int]) -> Optional[List[int]]:
    try:
        with open(image_path, "rb") as f:
            img_base64 = base64.b64encode(f.read()).decode("utf-8")
        mime_type = "image/jpeg" if not image_path.lower().endswith('.png') else "image/png"

        num_sections = len(questions_per_section)
        prompt = (
            f"这是一张学生答题卡图片，共有 {num_sections} 个题型区域，从上到下依次排列。"
            "请找出每个题型区域的分界线（即下一个题型开始的垂直位置），"
            "以图像高度的比例（0~1之间的小数）返回。"
            "例如，如果选择题在图像顶部30%处结束，填空题从30%开始，简答题从70%开始，返回 [0.3, 0.7]。"
            "只返回一个JSON数组，不要包含其他文字。"
        )

        content = [
            {"text": prompt},
            {"image": f"data:{mime_type};base64,{img_base64}"}
        ]

        body = {
            "model": MM_MODEL_CONFIG["model"],
            "input": {"messages": [{"role": "user", "content": content}]},
            "parameters": {"result_format": "message", "temperature": 0.0}
        }
        headers = {
            "Authorization": f"Bearer {MM_MODEL_CONFIG['api_key']}",
            "Content-Type": "application/json"
        }

        resp = requests.post(MM_MODEL_CONFIG["api_url"], headers=headers, json=body,
                             timeout=MM_MODEL_CONFIG["timeout"])
        resp.raise_for_status()
        result = resp.json()
        raw = result["output"]["choices"][0]["message"]["content"][0]["text"]
        logger.info(f"VLM区域检测原始返回: {raw}")

        cleaned = re.sub(r'^```json\s*', '', raw.strip())
        cleaned = re.sub(r'\s*```$', '', cleaned)
        ratios = json.loads(cleaned)
        if not isinstance(ratios, list) or len(ratios) != num_sections - 1:
            return None

        img = correct_exif_orientation(image_path)
        if img is None:
            logger.error(f"无法读取图片: {image_path}")
            return None
        if img is None:
            return None
        h = img.shape[0]
        y_coords = [int(r * h) for r in ratios if 0 < r < 1]
        y_coords = [y for y in y_coords if 30 < y < h - 30]
        y_coords.sort()
        if len(y_coords) == num_sections - 1:
            return y_coords
        else:
            return None

    except Exception as e:
        logger.warning(f"VLM区域检测失败: {e}")
        return None


def draw_question_regions(image: np.ndarray,
                          questions_per_section: List[int],
                          section_types: List[str] = None,
                          divider_ys: List[int] = None) -> np.ndarray:
    num_sections = len(questions_per_section)
    if num_sections == 0:
        return image

    h, w = image.shape[:2]

    if divider_ys and len(divider_ys) >= num_sections - 1:
        y_coords = []
        prev_y = 0
        for i, y in enumerate(divider_ys[:num_sections - 1]):
            y_coords.append((prev_y, y))
            prev_y = y
        y_coords.append((prev_y, h))
    else:
        section_height = h // num_sections
        y_coords = [(i * section_height, (i + 1) * section_height) for i in range(num_sections)]
        y_coords[-1] = (y_coords[-1][0], h)

    overlay = image.copy()
    colors = [(200, 220, 240), (240, 220, 200), (220, 240, 220),
              (240, 200, 240), (200, 240, 240), (240, 240, 200)]
    for i, (y1, y2) in enumerate(y_coords):
        color = colors[i % len(colors)]
        cv2.rectangle(overlay, (0, y1), (w, y2), color, -1)
    alpha = 0.15
    image = cv2.addWeighted(overlay, alpha, image, 1 - alpha, 0)

    for i, (y1, y2) in enumerate(y_coords):
        if i < len(y_coords) - 1:
            cv2.line(image, (0, y2), (w, y2), (255, 100, 0), 2)
        label = section_types[i] if section_types and i < len(section_types) else f'区域{i+1}'
        cv2.putText(image, label, (10, y1 + 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)

    return image


def draw_question_dividers(image: np.ndarray,
                           layout: Optional[List[dict]] = None,
                           questions_per_section: Optional[List[int]] = None) -> np.ndarray:
    h, w = image.shape[:2]
    if not layout and questions_per_section:
        total_q = sum(questions_per_section)
        if total_q == 0:
            return image
        cum = 0
        for i, cnt in enumerate(questions_per_section[:-1]):
            cum += cnt
            y = int((cum / total_q) * h)
            cv2.line(image, (0, y), (w, y), (255, 100, 0), 2)
            cv2.putText(image, f'第{i + 1}大题', (10, y - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 100, 0), 2)
    elif layout:
        for div in layout:
            y = div['y'] if isinstance(div['y'], int) else int(div['y'] * h)
            cv2.line(image, (0, y), (w, y), (255, 100, 0), 2)
            if div.get('label'):
                cv2.putText(image, div['label'], (10, y - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 100, 0), 2)
    else:
        for i in range(1, 3):
            y = int(h * i / 3)
            cv2.line(image, (0, y), (w, y), (255, 100, 0), 2)
            cv2.putText(image, f'第{i}大题', (10, y - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 100, 0), 2)
    return image


def preprocess_answer_sheet(image_path: str,
                            layout: Optional[List[dict]] = None,
                            questions_per_section: Optional[List[int]] = None,
                            section_types: Optional[List[str]] = None) -> Optional[np.ndarray]:
    img = correct_exif_orientation(image_path)
    if img is None:
        logger.error(f"无法读取图片: {image_path}")
        return None

    # 0. 智能方向纠正
    img = auto_orient(img, image_path)

    # 1. 倾斜校正
    img = deskew_image(img)

    # 2. 灰度化 + 增强
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = enhance_text_clarity(gray)

    # 3. 划痕/涂抹遮盖
    gray = detect_and_remove_strikethroughs(gray)

    # 4. 转回三通道并绘制区域/分割线
    result = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

    # 5. 区域划分
    if questions_per_section:
        result = draw_question_regions(result, questions_per_section, section_types)
    elif layout:
        result = draw_question_dividers(result, layout)
    else:
        result = draw_question_dividers(result)

    return result


# ==================== 姓名识别与匹配函数 ====================
def detect_text_orientation(image_path: str) -> str:
    """
    使用多模态模型检测图片中文字的方向。
    返回 'normal'、'rotated_left' 或 'rotated_right'。
    失败时返回 'normal'。
    """
    try:
        with open(image_path, "rb") as f:
            img_base64 = base64.b64encode(f.read()).decode("utf-8")
        mime_type = "image/jpeg" if not image_path.lower().endswith('.png') else "image/png"

        prompt = (
            "请判断这张图片中文字的方向："
            "如果文字是正常的水平方向，回答 'normal'；"
            "如果文字逆时针旋转了90度（需要顺时针旋转90度才能读），回答 'rotated_left'；"
            "如果文字顺时针旋转了90度，回答 'rotated_right'。"
            "只回答一个词，不要解释。"
        )
        content = [
            {"text": prompt},
            {"image": f"data:{mime_type};base64,{img_base64}"}
        ]
        body = {
            "model": MM_MODEL_CONFIG["model"],
            "input": {"messages": [{"role": "user", "content": content}]},
            "parameters": {"result_format": "message", "temperature": 0.0}
        }
        headers = {
            "Authorization": f"Bearer {MM_MODEL_CONFIG['api_key']}",
            "Content-Type": "application/json"
        }
        resp = requests.post(MM_MODEL_CONFIG["api_url"], headers=headers, json=body,
                             timeout=MM_MODEL_CONFIG["timeout"])
        resp.raise_for_status()
        result = resp.json()
        answer = result["output"]["choices"][0]["message"]["content"][0]["text"].strip().lower()
        logger.info(f"文字方向检测结果: {answer}")
        if answer in ('normal', 'rotated_left', 'rotated_right'):
            return answer
        else:
            return 'normal'
    except Exception as e:
        logger.warning(f"文字方向检测失败: {e}")
        return 'normal'

def extract_student_name(image_path: str) -> str:
    """
    使用多模态模型从答题卡第一页提取学生姓名。
    返回提取到的姓名文本，如果失败返回空字符串。
    """
    try:
        with open(image_path, "rb") as f:
            img_base64 = base64.b64encode(f.read()).decode("utf-8")
        mime_type = "image/jpeg" if not image_path.lower().endswith('.png') else "image/png"

        prompt = "请从这张答题卡图片中提取学生的姓名（仅输出姓名，不要其他内容）。如果找不到姓名，输出空字符串。"
        content = [
            {"text": prompt},
            {"image": f"data:{mime_type};base64,{img_base64}"}
        ]
        body = {
            "model": MM_MODEL_CONFIG["model"],
            "input": {"messages": [{"role": "user", "content": content}]},
            "parameters": {"result_format": "message", "temperature": 0.0}
        }
        headers = {
            "Authorization": f"Bearer {MM_MODEL_CONFIG['api_key']}",
            "Content-Type": "application/json"
        }
        resp = requests.post(MM_MODEL_CONFIG["api_url"], headers=headers, json=body, timeout=MM_MODEL_CONFIG["timeout"])
        resp.raise_for_status()
        result = resp.json()
        name = result["output"]["choices"][0]["message"]["content"][0]["text"].strip()
        logger.info(f"识别到学生姓名: {name}")
        return name
    except Exception as e:
        logger.warning(f"姓名识别失败: {e}")
        return ""

def match_student(name: str, exam_id: int) -> Optional[int]:
    """
    在考试的学生名单中模糊匹配姓名，返回 student_id，若找不到返回 None。
    """
    if not name:
        return None
    try:
        with engine.connect() as conn:
            students = conn.execute(
                text("""
                    SELECT s.student_id, s.name FROM students s
                    JOIN exam_students es ON s.student_id = es.student_id
                    WHERE es.exam_id = :exam_id
                """),
                {"exam_id": exam_id}
            ).fetchall()
            # 完全匹配
            for row in students:
                if row.name == name:
                    return row.student_id
            # 包含匹配
            for row in students:
                if name in row.name or row.name in name:
                    return row.student_id
            return None
    except Exception as e:
        logger.error(f"匹配学生失败: {e}")
        return None

# ==================== API 端点 ====================

@router.get("/api/exams/{exam_id}/images")
def get_exam_images(exam_id: int):
    try:
        with engine.connect() as conn:
            exam = conn.execute(
                text("SELECT exam_id FROM exams WHERE exam_id = :exam_id"),
                {"exam_id": exam_id}
            ).fetchone()
            if not exam:
                raise HTTPException(status_code=404, detail=f"考试 {exam_id} 不存在")

            result = conn.execute(
                text("""
                SELECT 
                    a.id, a.filename, a.file_path, a.processed_file_path,
                    a.uploaded_at, a.page_order,
                    s.student_id, s.name as student_name, s.student_number, s.class as student_class
                FROM answer_sheets a
                JOIN students s ON a.student_id = s.student_id
                WHERE a.exam_id = :exam_id
                ORDER BY s.student_id, a.page_order
                """),
                {"exam_id": exam_id}
            )
            images = []
            for row in result.fetchall():
                images.append({
                    "id": row.id,
                    "filename": row.filename,
                    "file_path": row.file_path,
                    "processed_file_path": row.processed_file_path or row.file_path,
                    "uploaded_at": row.uploaded_at.isoformat() if row.uploaded_at else None,
                    "page_order": row.page_order,
                    "student": {
                        "student_id": row.student_id,
                        "name": row.student_name,
                        "student_number": row.student_number,
                        "class": row.student_class
                    }
                })
            return {"code": 1, "msg": "获取成功", "data": images}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取考试图片列表失败 (exam_id={exam_id}): {str(e)}")
        raise HTTPException(status_code=500, detail="获取图片列表失败")

@router.post("/api/exams/{exam_id}/images")
async def upload_exam_images(
        exam_id: int,
        files: List[UploadFile] = File(...),
        student_ids: List[int] = Form([]),
        auto_match: bool = Form(False)
):
    # 验证考试，同时获取 images_per_student
    try:
        with engine.connect() as conn:
            exam = conn.execute(
                text("SELECT exam_id, answer_sheet_layout, images_per_student FROM exams WHERE exam_id = :exam_id"),
                {"exam_id": exam_id}
            ).fetchone()
            if not exam:
                raise HTTPException(status_code=404, detail=f"考试 {exam_id} 不存在")
            exam_layout = exam.answer_sheet_layout
            images_per_student = exam.images_per_student or 1
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"验证考试失败: {str(e)}")
        raise HTTPException(status_code=500, detail="验证考试失败")

    # 姓名匹配模式
    if auto_match:
        if len(files) % images_per_student != 0:
            raise HTTPException(status_code=400,
                                detail=f"总文件数({len(files)})应为每名学生图片数({images_per_student})的整数倍")
        student_ids = []
        temp_dir = ensure_upload_dir(exam_id)
        group_count = len(files) // images_per_student
        for g in range(group_count):
            first_idx = g * images_per_student
            first_file = files[first_idx]
            temp_name = f"temp_{int(time.time())}_{g}_{first_file.filename}"
            temp_path = os.path.join(temp_dir, temp_name)
            try:
                with open(temp_path, "wb") as buffer:
                    shutil.copyfileobj(first_file.file, buffer)
                name = extract_student_name(temp_path)
                if not name:
                    raise HTTPException(status_code=400, detail=f"第{g+1}组图片未能识别到姓名，请检查图片或手动上传")
                sid = match_student(name, exam_id)
                if sid is None:
                    raise HTTPException(status_code=400, detail=f"无法将姓名'{name}'匹配到考试中的任何学生，请手动上传")
                student_ids.extend([sid] * images_per_student)
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                await first_file.seek(0)
    else:
        # 顺序模式：原有的验证逻辑
        if len(student_ids) == 1 and len(files) > 1:
            student_ids = student_ids * len(files)
        elif len(student_ids) != len(files):
            raise HTTPException(status_code=400, detail="文件数量与学生ID数量不匹配")

        try:
            with engine.connect() as conn:
                for sid in set(student_ids):
                    student_in_exam = conn.execute(
                        text("SELECT 1 FROM exam_students WHERE exam_id = :exam_id AND student_id = :student_id"),
                        {"exam_id": exam_id, "student_id": sid}
                    ).fetchone()
                    if not student_in_exam:
                        raise HTTPException(status_code=400, detail=f"学生 {sid} 未参加考试 {exam_id}")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"验证学生失败: {str(e)}")
            raise HTTPException(status_code=500, detail="验证学生失败")

    # 获取题目分布（用于预处理分割线）
    questions_per_section = []
    section_types = []
    try:
        with engine.connect() as conn:
            q_rows = conn.execute(
                text("""
                    SELECT eq.question_order, q.type
                    FROM exam_questions eq
                    JOIN questions q ON eq.question_id = q.id
                    WHERE eq.exam_id = :exam_id
                    ORDER BY eq.question_order
                """),
                {"exam_id": exam_id}
            ).fetchall()
            current_type = None
            for row in q_rows:
                if row.type != current_type:
                    questions_per_section.append(0)
                    section_types.append(row.type)
                    current_type = row.type
                questions_per_section[-1] += 1
    except Exception as e:
        logger.warning(f"获取题目分布失败: {e}")

    # 手动布局解析
    layout = None
    if exam_layout:
        try:
            layout = json.loads(exam_layout)
            if not isinstance(layout, list):
                layout = None
        except:
            pass

    upload_dir = ensure_upload_dir(exam_id)
    uploaded_count = 0
    errors = []

    student_counter = {}
    page_orders = []
    for sid in student_ids:
        cnt = student_counter.get(sid, 0)
        page_orders.append(cnt)
        student_counter[sid] = cnt + 1

    for idx, file in enumerate(files):
        student_id = student_ids[idx]
        page_order = page_orders[idx]

        if not is_allowed_file(file.filename):
            errors.append(f"文件 {file.filename} 类型不支持")
            continue

        timestamp = int(time.time())
        safe_filename = f"{timestamp}_{file.filename.replace('/', '_')}"
        file_path = os.path.join(upload_dir, safe_filename)

        try:
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)

            base, ext = os.path.splitext(file_path)
            processed_path = f"{base}_processed.png"

            try:
                processed_img = preprocess_answer_sheet(
                    file_path, layout, questions_per_section, section_types
                )
                if processed_img is not None:
                    cv2.imwrite(processed_path, processed_img)
                else:
                    processed_path = file_path
            except Exception as pp_err:
                logger.error(f"预处理失败 {file_path}: {pp_err}")
                processed_path = file_path

            with engine.connect() as conn:
                conn.execute(
                    text("""
                    INSERT INTO answer_sheets 
                    (exam_id, student_id, filename, file_path, processed_file_path, page_order)
                    VALUES (:exam_id, :student_id, :filename, :file_path, :processed_path, :page_order)
                    """),
                    {
                        "exam_id": exam_id,
                        "student_id": student_id,
                        "filename": file.filename,
                        "file_path": file_path,
                        "processed_path": processed_path,
                        "page_order": page_order
                    }
                )
                conn.commit()

            uploaded_count += 1
            logger.info(f"上传成功: exam={exam_id}, student={student_id}, order={page_order}, file={file.filename}")
        except Exception as e:
            logger.error(f"上传失败 {file.filename}: {str(e)}")
            errors.append(f"{file.filename}: {str(e)}")
            if os.path.exists(file_path):
                os.remove(file_path)
        finally:
            await file.close()

    return {
        "code": 1,
        "msg": f"成功上传 {uploaded_count} 个文件",
        "data": {"uploaded_count": uploaded_count, "errors": errors}
    }


@router.get("/api/exams/{exam_id}/students/{student_id}/images")
def get_student_images(exam_id: int, student_id: int):
    try:
        with engine.connect() as conn:
            check = conn.execute(
                text("SELECT 1 FROM exam_students WHERE exam_id = :exam_id AND student_id = :student_id"),
                {"exam_id": exam_id, "student_id": student_id}
            ).fetchone()
            if not check:
                raise HTTPException(status_code=404, detail="学生未参加该考试")

            result = conn.execute(
                text("""
                SELECT id, filename, file_path, processed_file_path, uploaded_at, page_order
                FROM answer_sheets
                WHERE exam_id = :exam_id AND student_id = :student_id
                ORDER BY page_order
                """),
                {"exam_id": exam_id, "student_id": student_id}
            )
            images = []
            for row in result.fetchall():
                images.append({
                    "id": row.id,
                    "filename": row.filename,
                    "file_path": row.file_path,
                    "processed_file_path": row.processed_file_path or row.file_path,
                    "uploaded_at": row.uploaded_at.isoformat() if row.uploaded_at else None,
                    "page_order": row.page_order
                })
            return {"code": 1, "msg": "获取成功", "data": images}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取学生图片失败: {str(e)}")
        raise HTTPException(status_code=500, detail="获取学生图片失败")


@router.delete("/api/exams/{exam_id}/images/{image_id}")
def delete_image(exam_id: int, image_id: int):
    try:
        with engine.connect() as conn:
            img = conn.execute(
                text("SELECT file_path, processed_file_path FROM answer_sheets WHERE id = :image_id AND exam_id = :exam_id"),
                {"image_id": image_id, "exam_id": exam_id}
            ).fetchone()
            if not img:
                raise HTTPException(status_code=404, detail="图片不存在")

            if os.path.exists(img.file_path):
                os.remove(img.file_path)
            if img.processed_file_path and img.processed_file_path != img.file_path and os.path.exists(img.processed_file_path):
                os.remove(img.processed_file_path)

            conn.execute(text("DELETE FROM answer_sheets WHERE id = :image_id"), {"image_id": image_id})
            conn.commit()

            return {"code": 1, "msg": "删除成功"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除图片失败: {str(e)}")
        raise HTTPException(status_code=500, detail="删除图片失败")


@router.put("/api/exams/{exam_id}/images/{image_id}")
def update_image_order(
        exam_id: int,
        image_id: int,
        page_order: int = Form(...)
):
    try:
        with engine.connect() as conn:
            img = conn.execute(
                text("SELECT id FROM answer_sheets WHERE id = :image_id AND exam_id = :exam_id"),
                {"image_id": image_id, "exam_id": exam_id}
            ).fetchone()
            if not img:
                raise HTTPException(status_code=404, detail="图片不存在")

            conn.execute(
                text("UPDATE answer_sheets SET page_order = :page_order WHERE id = :image_id"),
                {"page_order": page_order, "image_id": image_id}
            )
            conn.commit()
            return {"code": 1, "msg": "更新成功"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新图片顺序失败: {str(e)}")
        raise HTTPException(status_code=500, detail="更新图片顺序失败")


@router.put("/api/exams/{exam_id}/images/{image_id}/transfer")
def transfer_image(
        exam_id: int,
        image_id: int,
        target_student_id: int,
        db: Session = Depends(get_db)
):
    try:
        img = db.execute(
            text("SELECT student_id, page_order FROM answer_sheets WHERE id = :image_id AND exam_id = :exam_id"),
            {"image_id": image_id, "exam_id": exam_id}
        ).fetchone()
        if not img:
            raise HTTPException(status_code=404, detail="图片不存在")

        target = db.execute(
            text("SELECT 1 FROM exam_students WHERE exam_id = :exam_id AND student_id = :target_student_id"),
            {"exam_id": exam_id, "target_student_id": target_student_id}
        ).fetchone()
        if not target:
            raise HTTPException(status_code=400, detail="目标学生未参加该考试")

        max_order = db.execute(
            text("SELECT COALESCE(MAX(page_order), -1) as max_order FROM answer_sheets WHERE exam_id = :exam_id AND student_id = :target_student_id"),
            {"exam_id": exam_id, "target_student_id": target_student_id}
        ).fetchone().max_order

        new_order = max_order + 1
        db.execute(
            text("UPDATE answer_sheets SET student_id = :target_student_id, page_order = :new_order WHERE id = :image_id"),
            {"target_student_id": target_student_id, "new_order": new_order, "image_id": image_id}
        )
        db.commit()
        return {"code": 1, "msg": "图片移动成功"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"移动图片失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"移动图片失败: {str(e)}")

@router.delete("/api/exams/{exam_id}/students/{student_id}/images")
def delete_student_images(exam_id: int, student_id: int):
    """删除某个学生在某次考试中的所有答题卡图片"""
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT file_path, processed_file_path FROM answer_sheets WHERE exam_id = :exam_id AND student_id = :student_id"),
                {"exam_id": exam_id, "student_id": student_id}
            ).fetchall()

            if not rows:
                raise HTTPException(status_code=404, detail="该学生没有上传任何图片")

            for row in rows:
                if os.path.exists(row.file_path):
                    os.remove(row.file_path)
                if row.processed_file_path and row.processed_file_path != row.file_path and os.path.exists(row.processed_file_path):
                    os.remove(row.processed_file_path)

            conn.execute(
                text("DELETE FROM answer_sheets WHERE exam_id = :exam_id AND student_id = :student_id"),
                {"exam_id": exam_id, "student_id": student_id}
            )
            conn.commit()

        return {"code": 1, "msg": "已删除该学生的所有图片"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"批量删除学生图片失败: {str(e)}")
        raise HTTPException(status_code=500, detail="批量删除失败")

@router.post("/api/exams/{exam_id}/images/{image_id}/mask")
def mask_image_rects(exam_id: int, image_id: int, rects: List[dict] = Body(..., embed=True)):
    """
    基于预处理后的图片进行矩形遮盖，并更新 processed_file_path。
    若没有预处理图，则使用原图。
    """
    try:
        with engine.connect() as conn:
            img = conn.execute(
                text("SELECT file_path, processed_file_path FROM answer_sheets WHERE id = :image_id AND exam_id = :exam_id"),
                {"image_id": image_id, "exam_id": exam_id}
            ).fetchone()
            if not img:
                raise HTTPException(status_code=404, detail="图片不存在")

        # 优先使用预处理图，没有则用原图
        source_path = img.processed_file_path if img.processed_file_path else img.file_path
        source_img = cv2.imread(source_path)
        if source_img is None:
            raise HTTPException(status_code=500, detail="无法读取图片")

        # 绘制白色矩形
        for rect in rects:
            x, y, w, h = int(rect["x"]), int(rect["y"]), int(rect["w"]), int(rect["h"])
            cv2.rectangle(source_img, (x, y), (x + w, y + h), (255, 255, 255), -1)

        # 保存结果（直接覆盖原预处理路径，若原本没有预处理图则新建）
        base, ext = os.path.splitext(img.file_path) if img.file_path else os.path.splitext(img.processed_file_path)
        processed_path = img.processed_file_path if img.processed_file_path else f"{base}_processed.png"
        cv2.imwrite(processed_path, source_img)

        # 更新数据库（确保 processed_file_path 指向该文件）
        with engine.connect() as conn:
            conn.execute(
                text("UPDATE answer_sheets SET processed_file_path = :path WHERE id = :image_id"),
                {"path": processed_path, "image_id": image_id}
            )
            conn.commit()

        return {"code": 1, "msg": "遮盖成功"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"遮盖图片失败: {str(e)}")
        raise HTTPException(status_code=500, detail="遮盖处理失败")

@router.post("/api/exams/{exam_id}/images/{image_id}/reset-mask")
def reset_image_mask(exam_id: int, image_id: int):
    """将处理图重置为未遮盖的预处理图（重新预处理原图）"""
    try:
        with engine.connect() as conn:
            img = conn.execute(
                text("SELECT file_path FROM answer_sheets WHERE id = :image_id AND exam_id = :exam_id"),
                {"image_id": image_id, "exam_id": exam_id}
            ).fetchone()
            if not img:
                raise HTTPException(status_code=404, detail="图片不存在")
            file_path = img.file_path

        # 获取题目分布（用于预处理分割线）
        with engine.connect() as conn:
            q_rows = conn.execute(
                text("""
                    SELECT eq.question_order, q.type
                    FROM exam_questions eq
                    JOIN questions q ON eq.question_id = q.id
                    WHERE eq.exam_id = :exam_id
                    ORDER BY eq.question_order
                """),
                {"exam_id": exam_id}
            ).fetchall()
            current_type = None
            questions_per_section = []
            section_types = []
            for row in q_rows:
                if row.type != current_type:
                    questions_per_section.append(0)
                    section_types.append(row.type)
                    current_type = row.type
                questions_per_section[-1] += 1

        # 获取布局（若存在）
        with engine.connect() as conn:
            layout_str = conn.execute(
                text("SELECT answer_sheet_layout FROM exams WHERE exam_id = :exam_id"),
                {"exam_id": exam_id}
            ).scalar()
        layout = None
        if layout_str:
            try:
                layout = json.loads(layout_str)
                if not isinstance(layout, list):
                    layout = None
            except:
                pass

        # 重新预处理
        processed_img = preprocess_answer_sheet(file_path, layout, questions_per_section, section_types)
        if processed_img is None:
            raise HTTPException(status_code=500, detail="预处理失败")

        base, ext = os.path.splitext(file_path)
        processed_path = f"{base}_processed.png"
        cv2.imwrite(processed_path, processed_img)

        # 更新数据库
        with engine.connect() as conn:
            conn.execute(
                text("UPDATE answer_sheets SET processed_file_path = :path WHERE id = :image_id"),
                {"path": processed_path, "image_id": image_id}
            )
            conn.commit()

        return {"code": 1, "msg": "已重置为原始预处理图"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"重置遮盖失败: {str(e)}")
        raise HTTPException(status_code=500, detail="重置失败")