from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends
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

def deskew_image(image: np.ndarray) -> np.ndarray:
    """自动检测倾斜角度并旋转校正"""
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
    """温和增强对比度并轻量锐化"""
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
    """检测划线、涂抹并 inpaint 修复"""
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
    """
    调用多模态视觉模型检测答题卡上各题型区域的纵向分界位置。
    返回区域分界 y 像素坐标列表（长度 = 题型数 - 1），若失败返回 None。
    """
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

        # 解析 JSON 数组
        cleaned = re.sub(r'^```json\s*', '', raw.strip())
        cleaned = re.sub(r'\s*```$', '', cleaned)
        ratios = json.loads(cleaned)
        if not isinstance(ratios, list) or len(ratios) != num_sections - 1:
            return None

        # 转换为像素 y 坐标（基于当前图片高度）
        img = cv2.imread(image_path)
        if img is None:
            return None
        h = img.shape[0]
        y_coords = [int(r * h) for r in ratios if 0 < r < 1]
        # 确保递增且过滤掉太靠近边缘的值
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
    """
    绘制半透明底色区域并标注题型名称。
    若提供 divider_ys，则直接使用这些 y 坐标作为区域边界；否则均分图像高度。
    """
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
    """简单线条分割（无底色），用于手动布局或默认三等分"""
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
    """
    完整预处理：倾斜校正 → 增强 → 划痕遮盖 → 自动检测/均分区域 → 绘制标注。
    """
    img = cv2.imread(image_path)
    if img is None:
        logger.error(f"无法读取图片: {image_path}")
        return None

    img = deskew_image(img)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = enhance_text_clarity(gray)
    gray = detect_and_remove_strikethroughs(gray)
    result = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

    # 尝试使用 VLM 自动检测分割线（可通过配置关闭）
    auto_dividers = None
    if questions_per_section and MM_MODEL_CONFIG.get("enable_region_detection", False):
        auto_dividers = detect_regions_with_vlm(image_path, questions_per_section)

    if questions_per_section:
        if auto_dividers and len(auto_dividers) >= len(questions_per_section) - 1:
            result = draw_question_regions(result, questions_per_section,
                                           section_types, divider_ys=auto_dividers)
        else:
            result = draw_question_regions(result, questions_per_section, section_types)
    elif layout:
        result = draw_question_dividers(result, layout)
    else:
        result = draw_question_dividers(result)

    return result


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
        student_ids: List[int] = Form(...)
):
    if len(student_ids) == 1 and len(files) > 1:
        student_ids = student_ids * len(files)
    elif len(student_ids) != len(files):
        raise HTTPException(status_code=400, detail="文件数量与学生ID数量不匹配")

    try:
        with engine.connect() as conn:
            exam = conn.execute(
                text("SELECT exam_id, answer_sheet_layout FROM exams WHERE exam_id = :exam_id"),
                {"exam_id": exam_id}
            ).fetchone()
            if not exam:
                raise HTTPException(status_code=404, detail=f"考试 {exam_id} 不存在")
            exam_layout = exam.answer_sheet_layout
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"验证考试失败: {str(e)}")
        raise HTTPException(status_code=500, detail="验证考试失败")

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