from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
import logging
import asyncio
from sqlalchemy import text
from sqlalchemy.orm import Session
import os
import re
import requests
import base64
import json
from typing import List, Dict

from backend.database import engine, get_db
from backend.config import MM_MODEL_CONFIG

logger = logging.getLogger(__name__)

router = APIRouter()


class GradingJobStatusResponse(BaseModel):
    job_id: int
    exam_id: int
    status: str
    total_students: int
    processed_students: int
    created_at: str
    updated_at: str


class StartGradingResponse(BaseModel):
    code: int
    msg: str
    data: dict


AREA_HINT = """
本批答题卡图片已经用不同底色的半透明矩形划分了不同的题型区域，并在每个区域左上角标注了具体的题型名称（如“选择题区域”、“填空题区域”等）。
请根据每个区域标注的题型，从对应区域中识别属于该题型的小题答案。
区域在图片中从上到下依次排列，题号也是按顺序分布的。如果某道题的答案位于两个区域的分界附近，请结合上下文和题号明确归属，不要遗漏。
"""


# ==================== OCR 识别函数 ====================
def ocr_only(image_paths: List[str], questions: List[dict]) -> Dict[int, dict]:
    if not image_paths:
        return {}

    num_questions = len(questions)

    # 题型描述
    type_descriptions = []
    for q in questions:
        order = q['question_order']
        q_type = q.get('type', '主观题')
        if q_type in ('choice', '选择题'):
            desc = f"第{order}题：选择题，答案为一个字母"
        elif q_type in ('fill_blank', '填空题'):
            desc = f"第{order}题：填空题，答案很短"
        elif q_type in ('true_false', '判断题'):
            desc = f"第{order}题：判断题，答案为对/错或√/×"
        else:
            desc = f"第{order}题：主观题（简答/计算/论述），答案可能较长，必须完整提取所有手写文字、公式和代码"
        type_descriptions.append(desc)
    type_hint = "本次识别的题目类型如下：\n" + "\n".join(type_descriptions) + "\n"

    prompt = AREA_HINT + "\n" + type_hint + (
        "你是一个严格的光学字符识别（OCR）工具。\n"
        f"本次发送了 {len(image_paths)} 张答题卡图片，请按顺序阅读所有图片，忽略印刷体题目描述、表格、得分栏等无关内容。\n"
        "请识别每个小题的学生答案。\n"
        f"一共有 {num_questions} 道小题，题号从 1 到 {num_questions}。\n"
        "小题的题号是普通数字加标点，例如“1.”、“2.”、“3.”。每个这样的题号代表一道独立的小题。\n"
        "你必须根据图片上**印刷题号的物理位置**来确定每个答案的归属：寻找印刷题号（如“6.”），该题号之后、下一个印刷题号之前的手写内容即为该题答案；如果该区域内没有任何手写痕迹，则答案必须为空字符串。\n"
        "绝对不允许将位于下一个印刷题号之后的内容填到当前题号。\n"
        "例如，图片中印刷题号依次为“6.” “7.” “8.”，在“6.”和“7.”之间有一片空白，“7.”之后手写为“hello”，“8.”之后手写为“world”，则输出：\n"
        "{\"6\": \"\", \"7\": \"hello\", \"8\": \"world\"}\n"
        "而不是 {\"6\": \"hello\", \"7\": \"world\", \"8\": \"\"} 或任意错位。\n"
        "学生可能会手写题号，此时仍需根据手写题号的位置与印刷题号进行对照，若手写题号与印刷题号不对应，以手写题号对应的区域内容为准，但若无法确定，必须留空。\n"
        "注意：填空题的答案通常很短，可能是单个数字、字母或词语，但**也必须完整包含所有数学符号（如括号、区间、运算符号）**，请务必提取，不要忽略。\n"
        "尤其要注意：如果手写答案中包含花括号 {}、中括号 []、小括号 () 等，必须原样保留，它们是答案的一部分。例如答案 \"{1,2,3}\" 应识别为 \"{1,2,3}\"，而不是 \"1,2,3\"。\n"
        "对于填空题，如果多个小题的答案在同一行连续书写，即使中间的某个小题答案为空白，你也必须继续识别该行后面其他小题的答案，不得因为一个空白就忽略后续所有内容。\n"
        "绝对不要把题号本身（如手写的“1.”、“2.”）当作答案。如果某个位置只有孤立的数字和标点，且周围无其他内容，应视为题号，对应答案留空。\n"
        "特别重要：对于**主观题（简答题、论述题、计算题等）**，答案往往是多行文字、代码或公式，且可能包含多个小题号（如①、②、(1)、(2)等）。你必须**完整、精确地提取所有手写内容**，包括每个小题号后的答案，将所有小题的答案用换行符合并成一个字符串输出，即使书写潦草也不要遗漏。\n"
        "重要：你需要准确识别学生手写答案中的数学符号和公式，包括但不限于：\n"
        "  - 绝对值：|x|、||x||、|a-b| 等，用竖线表示，不要写成 abs(x) 或 abs()\n"
        "  - 范数：||x||、||x||_p\n"
        "  - 基本运算：+、-、×、÷、=、≈、≠、≤、≥、±、√、∛、∞\n"
        "  - 括号与大括号：()、[]、{}、⟨⟩、|| ||（绝对值/范数）\n"
        "  - 区间表示：如 (a,b)、[a,b]、(-∞,0] 等\n"
        "  - 希腊字母：α、β、γ、δ、ε、λ、μ、π、σ、τ、ω\n"
        "  - 上下标：x^2、y_n、a^{b}、e^{x}（用 ^ 和 _ 表示）\n"
        "  - 分数：a/b 或水平分数线（写作 (分子)/(分母)）\n"
        "  - 积分：∫、∬、∮\n"
        "  - 求和连乘：∑、∏\n"
        "  - 集合符号：∈、∉、⊂、⊆、∪、∩、∅\n"
        "  - 逻辑符号：⇒、⇔、∀、∃\n"
        "  - 矩阵：用方括号表示，如 [a b; c d]\n"
        "输出一个JSON对象，键为题号（字符串），值为对应的学生答案。例如：{\"1\": \"答案1\", \"2\": \"答案2\\n第二分点\", \"3\": \"\"}\n"
        "同一道小题的多个分点（如带圈数字①、②、括号数字(1)、(2)等）必须合并为一个字符串，使用换行符分隔。\n"
        "输出的答案中不要包含题号本身（例如不要输出“2、负实轴单位圆”，只需要输出“负实轴单位圆”）。\n"
        "若某道小题学生只写了题号却没有书写任何有效的答案内容（如大片空白），或者答案无法识别，则对应键的值必须是空字符串。\n"
        "特别重要：对于**选择题**，你必须为每个题号单独输出一个键值对，严禁将多个选择题的答案合并到一个键中！\n"
        "选择题的答案必须是单个大写字母，请特别注意区分容易混淆的字母，如 A/H、B/D、C/G 等。如果手写体不够清晰，请根据题号区域的上下文和常见选项规律进行判断，并选择最可能的字母。仍然无法确定时，输出空字符串。\n"
        "例如，如果图片中有四道选择题，答案分别是 'A', 'B', 'C', 'D'，你必须输出："
        "{\"1\": \"A\", \"2\": \"B\", \"3\": \"C\", \"4\": \"D\"}，而不是 {\"1\": \"A B C D\"} 或 {\"1\": \"A2.B3.C4.D\"}。\n"
        "每个题号只能对应一个答案，不能把一个题号的答案字符串中包含其他题号的标识。\n"
        "不要输出任何其他解释或标记。"
    )

    content = [{"text": prompt}]
    for path in image_paths:
        with open(path, "rb") as f:
            img_base64 = base64.b64encode(f.read()).decode("utf-8")
        mime_type = "image/jpeg" if not path.lower().endswith('.png') else "image/png"
        content.append({"image": f"data:{mime_type};base64,{img_base64}"})

    body = {
        "model": MM_MODEL_CONFIG["model"],
        "input": {"messages": [{"role": "user", "content": content}]},
        "parameters": {"result_format": "message", "temperature": 0.0}
    }
    headers = {
        "Authorization": f"Bearer {MM_MODEL_CONFIG['api_key']}",
        "Content-Type": "application/json"
    }

    raw_result = ""
    for attempt in range(MM_MODEL_CONFIG["max_retries"]):
        try:
            resp = requests.post(MM_MODEL_CONFIG["api_url"], headers=headers, json=body, timeout=MM_MODEL_CONFIG["timeout"])
            resp.raise_for_status()
            result = resp.json()
            raw_result = result["output"]["choices"][0]["message"]["content"][0]["text"]
            logger.info(f"OCR原始结果（完整）: {raw_result}")
            break
        except Exception as e:
            if attempt == MM_MODEL_CONFIG["max_retries"] - 1:
                logger.error(f"OCR API 调用最终失败: {e}")
                return {}
            logger.warning(f"OCR 重试 {attempt+1}: {e}")

    if not raw_result:
        return {}

    cleaned = re.sub(r'^```json\s*', '', raw_result.strip())
    cleaned = re.sub(r'\s*```$', '', cleaned)
    logger.info(f"清理后的内容: {cleaned}")

    try:
        data = json.loads(cleaned)
        if isinstance(data, list):
            logger.warning("模型返回数组，将按顺序映射到题号")
            data = {str(i+1): val for i, val in enumerate(data)}
        elif not isinstance(data, dict):
            match = re.search(r'\{.*\}', cleaned, re.DOTALL)
            if match:
                data = json.loads(match.group())
            else:
                data = {}
    except Exception as e:
        logger.error(f"OCR JSON解析失败: {e}, 原始内容: {raw_result}")
        data = {}

    def clean_answer(text: str) -> str:
        if not text:
            return ""
        placeholder_patterns = [
            r'^答案\d+$', r'^实际答案\d+$', r'^填空答案$', r'^示例答案$',
            r'^学生答案$', r'^答案$', r'^未识别$'
        ]
        for pat in placeholder_patterns:
            if re.match(pat, text.strip()):
                return ""
        return text

    result = {}
    for q in questions:
        order = q['question_order']
        key = str(order)
        answer = data.get(key, "")
        result[order] = {"exists": True, "answer": clean_answer(answer)}
    return result


# ==================== 纠错模型 ====================
def correct_answers_with_image(
    image_paths: List[str],
    original_answers: Dict[int, str],
    questions: List[dict]
) -> Dict[int, str]:
    if not image_paths:
        return {}

    q_descriptions = []
    for q in questions:
        order = q['question_order']
        q_type = q.get('type', 'essay')
        if q_type in ('choice', '选择题'):
            type_hint = "选择题，答案只能是一个英文字母(A/B/C/D等)，不要数字、汉字或其他符号"
        elif q_type in ('fill_blank', '填空题'):
            type_hint = "填空题，答案可能是词语、数字或短句"
        elif q_type in ('true_false', '判断题'):
            type_hint = "判断题，答案应为'正确'/'错误'或'√'/'×'"
        else:
            type_hint = "主观题，答案可能是较长的文字"
        q_descriptions.append(
            f"第{order}题（{type_hint}）：原识别结果 = '{original_answers.get(order, '')}'"
        )

    prompt = (
        "你是一个纠错工具，需要根据答题卡图片纠正OCR识别结果。\n"
        "以下是各题目的题型和原始识别结果，请结合题目类型判断原始答案是否合理，并给出最终答案。\n"
        "特别要求：选择题的答案必须只包含一个英文字母，不允许出现数字、汉字或标点。\n"
        + "\n".join(q_descriptions) +
        "\n\n请输出一个JSON对象，键为题号（字符串），值为纠正后的答案。"
        "如果无法识别，则对应值为空字符串。不要输出其他内容。"
    )

    content = [{"text": prompt}]
    for path in image_paths:
        with open(path, "rb") as f:
            img_base64 = base64.b64encode(f.read()).decode("utf-8")
        mime_type = "image/jpeg" if not path.lower().endswith('.png') else "image/png"
        content.append({"image": f"data:{mime_type};base64,{img_base64}"})

    body = {
        "model": MM_MODEL_CONFIG["model"],
        "input": {"messages": [{"role": "user", "content": content}]},
        "parameters": {"result_format": "message", "temperature": 0.1}
    }
    headers = {
        "Authorization": f"Bearer {MM_MODEL_CONFIG['api_key']}",
        "Content-Type": "application/json"
    }

    raw_result = ""
    for attempt in range(MM_MODEL_CONFIG["max_retries"]):
        try:
            resp = requests.post(MM_MODEL_CONFIG["api_url"], headers=headers, json=body,
                                 timeout=MM_MODEL_CONFIG["timeout"])
            resp.raise_for_status()
            result = resp.json()
            raw_result = result["output"]["choices"][0]["message"]["content"][0]["text"]
            logger.info(f"纠错模型返回: {raw_result}")
            break
        except Exception as e:
            if attempt == MM_MODEL_CONFIG["max_retries"] - 1:
                logger.error(f"纠错API调用最终失败: {e}")
                return {}
            logger.warning(f"纠错重试 {attempt+1}: {e}")

    if not raw_result:
        return {}

    cleaned = re.sub(r'^```json\s*', '', raw_result.strip())
    cleaned = re.sub(r'\s*```$', '', cleaned)
    try:
        data = json.loads(cleaned)
        if isinstance(data, list):
            logger.warning("纠错返回数组，转换为字典")
            data = {str(i+1): val for i, val in enumerate(data)}
        elif not isinstance(data, dict):
            match = re.search(r'\{.*\}', cleaned, re.DOTALL)
            if match:
                data = json.loads(match.group())
            else:
                data = {}
    except Exception as e:
        logger.error(f"纠错JSON解析失败: {e}, 原始内容: {raw_result}")
        data = {}

    corrected = {}
    for q in questions:
        order = q['question_order']
        key = str(order)
        corrected[order] = data.get(key, original_answers.get(order, ""))
    return corrected


def refine_subjective_answers(
    image_paths: List[str],
    original_answers: Dict[int, str],
    questions: List[dict]
) -> Dict[int, str]:
    """
    专门用于简答题/主观题的二次提取，强调完整提取，无视原始答案（如果原始答案过短）。
    """
    if not image_paths:
        return {}

    q_descriptions = []
    for q in questions:
        order = q['question_order']
        q_content = q.get('content', '')[:80]
        orig = original_answers.get(order, '')
        # 如果原答案超过30字符，可能已经较完整，提供给模型参考；否则提示原答案可能缺失
        hint = f"原识别结果（可能不完整） = '{orig}'" if len(orig) < 30 else f"原识别结果 = '{orig}'"
        q_descriptions.append(
            f"第{order}题（主观题）：题目内容：{q_content}\n{hint}"
        )

    prompt = (
        "你是一个补充提取工具，需要根据答题卡图片重新提取主观题（简答题/论述题等）的完整学生答案。\n"
        "请特别注意：该类题目答案中可能包含多个小题号（如①、②、(1)、(2)、a)、b) 等），"
        "你必须提取每一个小题号后的手写内容，并将它们按顺序用换行符连接成一个完整的字符串。\n"
        "如果答题区域内有大片手写文字，但原识别结果很短，说明原识别结果可能严重遗漏，你必须**完整扫描整个答题区域**，提取所有手写内容，即使书写潦草也不要遗漏。\n"
        "即使部分小题答案为空白，也要保留空行或明确标记，但最终返回的字符串中应包含所有能找到的小题答案。\n"
        "不要受原始识别结果的限制，如果两者冲突，以图片实际内容为准。\n"
        "以下是各题目的信息及原始识别结果，请给出完整的纠正后的答案。\n"
        + "\n".join(q_descriptions) +
        "\n\n请输出一个JSON对象，键为题号（字符串），值为完整的学生答案字符串（换行符用\\n表示）。"
        "如果某题完全无法识别，则对应值为空字符串。不要输出其他内容。"
    )

    content = [{"text": prompt}]
    for path in image_paths:
        with open(path, "rb") as f:
            img_base64 = base64.b64encode(f.read()).decode("utf-8")
        mime_type = "image/jpeg" if not path.lower().endswith('.png') else "image/png"
        content.append({"image": f"data:{mime_type};base64,{img_base64}"})

    body = {
        "model": MM_MODEL_CONFIG["model"],
        "input": {"messages": [{"role": "user", "content": content}]},
        "parameters": {"result_format": "message", "temperature": 0.1}  # 略微提高温度，鼓励更全面的输出
    }
    headers = {
        "Authorization": f"Bearer {MM_MODEL_CONFIG['api_key']}",
        "Content-Type": "application/json"
    }

    raw_result = ""
    for attempt in range(MM_MODEL_CONFIG["max_retries"]):
        try:
            resp = requests.post(MM_MODEL_CONFIG["api_url"], headers=headers, json=body,
                                 timeout=MM_MODEL_CONFIG["timeout"])
            resp.raise_for_status()
            result = resp.json()
            raw_result = result["output"]["choices"][0]["message"]["content"][0]["text"]
            logger.info(f"主观题补充提取返回: {raw_result}")
            break
        except Exception as e:
            if attempt == MM_MODEL_CONFIG["max_retries"] - 1:
                logger.error(f"主观题补充提取失败: {e}")
                return {}
            logger.warning(f"重试 {attempt+1}: {e}")

    if not raw_result:
        return {}

    cleaned = re.sub(r'^```json\s*', '', raw_result.strip())
    cleaned = re.sub(r'\s*```$', '', cleaned)
    try:
        data = json.loads(cleaned)
        if isinstance(data, list):
            data = {str(i+1): val for i, val in enumerate(data)}
        elif not isinstance(data, dict):
            match = re.search(r'\{.*\}', cleaned, re.DOTALL)
            if match:
                data = json.loads(match.group())
            else:
                data = {}
    except Exception as e:
        logger.error(f"主观题补充JSON解析失败: {e}")
        data = {}

    refined = {}
    for q in questions:
        order = q['question_order']
        key = str(order)
        refined[order] = data.get(key, original_answers.get(order, ""))
    return refined

# ==================== 评分 ====================
def score_only(question: dict, student_answer: str) -> float:
    if not student_answer or student_answer.strip() == "":
        logger.warning(f"题目 {question['id']} 学生答案为空，返回0分")
        return 0.0

    q_type = question.get('type', '主观题')
    reference = question.get('reference_answer', '')

    # 选择题与判断题：精确匹配，满分或零分
    if q_type in ['选择题', '判断题', 'choice', 'true_false']:
        def norm(s):
            s = s.strip().lower()
            s = re.sub(r'[^\w]', '', s)
            return s
        if norm(student_answer) == norm(reference):
            return 100.0
        else:
            logger.info(f"客观题匹配失败: 参考'{reference}' vs 学生'{student_answer}'")
            return 0.0

    # 填空题：模糊匹配
    if q_type in ['填空题', 'fill_blank']:
        def norm(s):
            s = s.strip().lower()
            s = re.sub(r'[^\w]', '', s)
            return s
        if norm(student_answer) == norm(reference):
            return 100.0

        def strip_chars(s):
            return re.sub(r'[^a-zA-Z0-9\u4e00-\u9fff]', '', s).lower()
        a = strip_chars(student_answer)
        r = strip_chars(reference)
        if a and r and (a == r or (len(a) >= 2 and len(r) >= 2 and (a in r or r in a))):
            logger.info(f"填空题模糊匹配成功: 参考'{reference}' vs 学生'{student_answer}'")
            return 100.0
        else:
            logger.info(f"填空题匹配失败: 参考'{reference}' vs 学生'{student_answer}'")
            return 0.0

    # 主观题：使用大模型评分
    prompt = f"""你是一位专业、公正的阅卷教师。请根据以下信息对学生的答案进行评分。

**题目内容**：
{question['content']}

**参考答案**（仅供你理解题意，不作为唯一评分标准）：
{reference}

**评分标准**：
{question.get('scoring_rules', '根据答案的正确性、完整性和逻辑清晰度给分')}


**学生答案**：
{student_answer}

**评分要求**：
1. 首先判断学生答案是否回答了题目所问：只要有相关尝试，即使表述不完善，也应给予基础分（至少30分）。
2. 若学生答案展现出清晰思路、合理步骤或部分正确结果，根据正确程度给分（70-90分）。
3. 完全正确且逻辑完整清晰的答案给满分（100分）。
4. 只有完全不相关、恶意作答或完全空白才给0分；学生若写了代码即使有问题也酌情给分（不低于40分）。
5. 参考答案仅为参考，不要求一致；鼓励创新解法，只要满足题目要求即可。
6. 请只返回一个0-100之间的数字分数，不要输出任何其他文字、解释或标点。"""

    body = {
        "model": MM_MODEL_CONFIG["model"],
        "input": {"messages": [{"role": "user", "content": [{"text": prompt}]}]},
        "parameters": {"result_format": "message", "temperature": 0.1}
    }
    headers = {
        "Authorization": f"Bearer {MM_MODEL_CONFIG['api_key']}",
        "Content-Type": "application/json"
    }

    try:
        resp = requests.post(MM_MODEL_CONFIG["api_url"], headers=headers, json=body, timeout=MM_MODEL_CONFIG["timeout"])
        resp.raise_for_status()
        result = resp.json()
        output_text = result["output"]["choices"][0]["message"]["content"][0]["text"]
        logger.info(f"评分模型返回: {output_text}")
        numbers = re.findall(r"\d+(?:\.\d+)?", output_text)
        if numbers:
            score = float(numbers[0])
            score = min(max(score, 0), 100)
            if score == 0.0 and student_answer.strip():
                logger.warning(f"题目 {question['id']} 模型返回0分但学生答案非空，使用默认分50")
                return 50.0
            return score
        else:
            match = re.search(r'"score":\s*(\d+(?:\.\d+)?)', output_text)
            if match:
                score = float(match.group(1))
                return min(max(score, 0), 100)
            logger.error(f"无法解析分数，返回默认分50")
            return 50.0
    except Exception as e:
        logger.error(f"评分调用失败: {e}")
        return 0.0


# ==================== 辅助处理函数 ====================
def merge_subjective_answers(questions: List[dict], answers: Dict[int, str]) -> Dict[int, str]:
    if not questions:
        return answers.copy()
    return answers


def reorder_answers_by_reference(questions: List[dict], answers: Dict[int, str]) -> Dict[int, str]:
    return answers


def split_combined_choices(questions: List[dict], answers: Dict[int, str]) -> Dict[int, str]:
    import re
    new_answers = answers.copy()
    choice_orders = [q['question_order'] for q in questions if q.get('type') in ['选择题', 'choice']]
    for q in questions:
        if q.get('type') not in ['选择题', 'choice']:
            continue
        order = q['question_order']
        text = answers.get(order, '')
        if not text:
            continue

        pattern = r'(\d+)[\.、，,\s]*([A-Za-z])'
        matches = list(re.finditer(pattern, text))
        if len(matches) > 1:
            for match in matches:
                num = int(match.group(1))
                letter = match.group(2).upper()
                if num in choice_orders:
                    new_answers[num] = letter
            continue

        pattern2 = r'([A-Za-z])(\d+)'
        matches2 = list(re.finditer(pattern2, text))
        if matches2:
            for match in matches2:
                letter = match.group(1).upper()
                num = int(match.group(2))
                if num in choice_orders:
                    new_answers[num] = letter
            continue

        if re.match(r'^[A-Za-z\.]+$', text):
            parts = text.split('.')
            for idx, part in enumerate(parts):
                if part and idx < len(choice_orders):
                    new_answers[choice_orders[idx]] = part.upper()
            continue

        letters = re.findall(r'([A-Za-z])', text)
        numbers = re.findall(r'(\d+)', text)
        if letters and numbers:
            for num_str, letter in zip(numbers, letters):
                num = int(num_str)
                if num in choice_orders:
                    new_answers[num] = letter.upper()
            if len(letters) > len(numbers) and choice_orders:
                new_answers[choice_orders[0]] = letters[0].upper()
            continue

        if re.fullmatch(r'[A-Za-z\s\.]+', text):
            letters = re.findall(r'[A-Za-z]', text)
            if len(letters) > 1:
                try:
                    start_idx = choice_orders.index(order)
                except ValueError:
                    start_idx = -1
                if start_idx >= 0 and start_idx + len(letters) <= len(choice_orders):
                    for i, letter in enumerate(letters):
                        target_order = choice_orders[start_idx + i]
                        new_answers[target_order] = letter.upper()
                    continue

        clean_text = re.sub(r'^\s*\d+[\.、:：）)]\s*', '', text).strip()
        if clean_text and clean_text != text:
            new_answers[order] = clean_text

    for order in choice_orders:
        ans = new_answers.get(order, '')
        if not ans:
            continue
        if re.fullmatch(r'[A-Za-z](?:\s*[\.\s]\s*[A-Za-z]){0,3}', ans):
            continue
        if len(ans) > 5 or re.search(r'[\u4e00-\u9fff\d]', ans):
            logger.warning(f"选择题 {order} 答案异常（疑似其他题目内容），已清空: '{ans}'")
            new_answers[order] = ''

    return new_answers


def split_combined_fillblanks(questions: List[dict], answers: Dict[int, str]) -> Dict[int, str]:
    """
    根据答案开头可能的手写题号，将答案归位到正确的填空题号上，并剥离题号前缀。
    若答案开头没有题号，则保持原顺序（通过后续的参考答案匹配再纠正）。
    """
    import re
    new_answers = answers.copy()
    fill_orders = [q['question_order'] for q in questions if q.get('type') in ['填空题', 'fill_blank']]
    if not fill_orders:
        return new_answers

    # 首先将所有填空题的答案置空，准备重新填充
    for order in fill_orders:
        new_answers[order] = ""

    # 处理原来每个题号下的答案文本
    for order in fill_orders:
        text = answers.get(order, '')
        if not text.strip():
            continue

        # 查找开头的手写题号（数字+标点）
        m = re.match(r'^\s*(\d+)\s*[\.、:：）)]\s*', text)
        if m:
            num = int(m.group(1))
            if num in fill_orders:
                # 剥离题号前缀，只保留答案内容
                remaining = re.sub(r'^\s*\d+\s*[\.、:：）)]\s*', '', text).strip()
                # 如果该题号尚未被填充，或者当前答案更合适（长度更长优先），则填充
                current = new_answers.get(num, "")
                if not current or len(remaining) > len(current):
                    new_answers[num] = remaining
                continue  # 已处理此文本，不再按原顺序保留

        # 如果没有题号前缀，保留在原题号（避免丢失）
        clean = re.sub(
            r'^\s*'
            r'(?:\(\s*\d+\s*\)|（\s*\d+\s*）|[①②③④⑤⑥⑦⑧⑨⑩]+|\d+[\.、:：）)\u00A0]\s*)+',
            '', text
        ).strip()
        if clean or re.fullmatch(r'\d+', text):  # 纯数字答案保留
            new_answers[order] = clean if clean else text
        # 否则保持为空（原逻辑）

    return new_answers


def match_fillblanks_to_reference(questions: List[dict], answers: Dict[int, str]) -> Dict[int, str]:
    """
    利用参考答案将填空题的非空答案匹配到正确的题号上，未匹配到的题号置空。
    当所有参考答案均为空时不执行任何操作，返回原答案。
    """
    import re
    fill_orders = [q['question_order'] for q in questions if q.get('type') in ['填空题', 'fill_blank']]
    if not fill_orders:
        return answers

    # 获取参考答案
    ref_map = {}
    for q in questions:
        if q.get('type') in ['填空题', 'fill_blank']:
            ref_map[q['question_order']] = q.get('reference_answer', '').strip()

    # 如果所有参考答案都为空，则不进行匹配
    if not any(ref for ref in ref_map.values()):
        return answers

    # 提取当前答案（只保留非空答案）
    ans_list = [(order, answers.get(order, '').strip()) for order in fill_orders]
    non_empty = [(order, ans) for order, ans in ans_list if ans]

    # 如果没有非空答案，直接返回全空
    if not non_empty:
        new_answers = answers.copy()
        for order in fill_orders:
            new_answers[order] = ""
        return new_answers

    # 相似度计算
    def sim(ans, ref):
        if not ref:
            return 0
        # 去除所有非字母数字中文的符号
        a = re.sub(r'[^a-zA-Z0-9\u4e00-\u9fff]', '', ans).lower()
        r = re.sub(r'[^a-zA-Z0-9\u4e00-\u9fff]', '', ref).lower()
        if a == r:
            return 3
        if a and r and (a in r or r in a):
            return 2
        # 完全匹配
        if ans.strip().lower() == ref.lower():
            return 3
        if ans.strip().lower() in ref.lower() or ref.lower() in ans.strip().lower():
            return 2
        return 0

    # 构建得分矩阵 (非空答案索引 × 题号索引)
    num_orders = len(fill_orders)
    scores = [[0] * num_orders for _ in range(len(non_empty))]
    for i, (_, ans) in enumerate(non_empty):
        for j, order in enumerate(fill_orders):
            scores[i][j] = sim(ans, ref_map.get(order, ''))

    # 贪心分配
    used_ans = set()
    used_order = set()
    result_map = {}  # order -> answer

    while len(used_ans) < len(non_empty):
        best_score = -1
        best_i = -1
        best_j = -1
        for i in range(len(non_empty)):
            if i in used_ans:
                continue
            for j in range(num_orders):
                if j in used_order:
                    continue
                if scores[i][j] > best_score:
                    best_score = scores[i][j]
                    best_i = i
                    best_j = j
        if best_score <= 0:
            break  # 没有有效匹配，剩余答案不会被分配（从而被置空）
        result_map[fill_orders[best_j]] = non_empty[best_i][1]
        used_ans.add(best_i)
        used_order.add(best_j)

    # 写回答案，未匹配的题号置空
    new_answers = answers.copy()
    for order in fill_orders:
        new_answers[order] = result_map.get(order, "")
    return new_answers


# ==================== 后台阅卷任务 ====================
async def process_grading(exam_id: int, job_id: int):
    logger.info(f"开始阅卷任务：exam_id={exam_id}, job_id={job_id}")
    try:
        with engine.connect() as conn:
            exam = conn.execute(
                text("SELECT exam_id FROM exams WHERE exam_id = :exam_id"),
                {"exam_id": exam_id}
            ).fetchone()
            if not exam:
                raise Exception(f"考试 {exam_id} 不存在")

            exam_total_score = conn.execute(
                text("SELECT total_score FROM exams WHERE exam_id = :exam_id"),
                {"exam_id": exam_id}
            ).scalar()

            students_result = conn.execute(
                text("""
                     SELECT s.student_id, s.name
                     FROM students s
                              INNER JOIN exam_students es ON s.student_id = es.student_id
                     WHERE es.exam_id = :exam_id
                     """),
                {"exam_id": exam_id}
            )
            students = [dict(row._mapping) for row in students_result.fetchall()]
            total_students = len(students)

            conn.execute(
                text("UPDATE grading_jobs SET total_students = :total, status = 'processing' WHERE id = :job_id"),
                {"total": total_students, "job_id": job_id}
            )
            conn.commit()

            questions_result = conn.execute(
                text("""
                     SELECT q.id,
                            q.type,
                            q.content,
                            q.reference_answer,
                            q.scoring_rules,
                            q.score as max_score,
                            eq.question_order,
                            q.parent_id
                     FROM questions q
                              INNER JOIN exam_questions eq ON q.id = eq.question_id
                     WHERE eq.exam_id = :exam_id
                     ORDER BY eq.question_order
                     """),
                {"exam_id": exam_id}
            )
            questions = [dict(row._mapping) for row in questions_result.fetchall()]

            if not questions:
                logger.warning(f"考试 {exam_id} 没有题目")
                conn.execute(
                    text("UPDATE grading_jobs SET status = 'failed' WHERE id = :job_id"),
                    {"job_id": job_id}
                )
                conn.commit()
                return

        processed = 0
        for student in students:
            student_id = student["student_id"]
            logger.info(f"处理学生 {student_id} - {student['name']}")

            with engine.connect() as conn:
                images = conn.execute(
                    text("""
                         SELECT COALESCE(processed_file_path, file_path) as file_path
                         FROM answer_sheets
                         WHERE exam_id = :exam_id
                           AND student_id = :student_id
                         ORDER BY page_order
                         """),
                    {"exam_id": exam_id, "student_id": student_id}
                ).fetchall()

            logger.info(f"学生 {student_id} - {student['name']} 共有 {len(images)} 张答题卡图片")

            if not images:
                logger.warning(f"学生 {student_id} 无答题卡图片，跳过")
                processed += 1
                with engine.connect() as conn:
                    conn.execute(
                        text("UPDATE grading_jobs SET processed_students = :processed WHERE id = :job_id"),
                        {"processed": processed, "job_id": job_id}
                    )
                    conn.commit()
                continue

            image_paths = [row.file_path for row in images]

            ocr_result = ocr_only(image_paths, questions)
            if ocr_result is None:
                ocr_result = {}
                logger.warning("ocr_only 返回 None，使用空字典")
            original_answers = {order: info["answer"] for order, info in ocr_result.items()}

            if all(len(ans) == 0 for ans in original_answers.values()):
                logger.warning("预处理图片OCR结果为空，尝试使用原始图片重新识别...")
                with engine.connect() as conn:
                    fallback_images = conn.execute(
                        text("""
                             SELECT file_path
                             FROM answer_sheets
                             WHERE exam_id = :exam_id
                               AND student_id = :student_id
                             ORDER BY page_order
                             """),
                        {"exam_id": exam_id, "student_id": student_id}
                    ).fetchall()
                fallback_paths = [row.file_path for row in fallback_images]
                ocr_result = ocr_only(fallback_paths, questions)
                if ocr_result is None:
                    ocr_result = {}
                    logger.warning("第二次 ocr_only 返回 None")
                original_answers = {order: info["answer"] for order, info in ocr_result.items()}

            # 拆分选择题答案
            split_answers = split_combined_choices(questions,
                                                   {order: info["answer"] for order, info in ocr_result.items()})
            for order, new_ans in split_answers.items():
                if new_ans:
                    ocr_result[order]["answer"] = new_ans
                    logger.info(f"拆分选择题 {order}: 新答案 = {new_ans}")

            # 拆分填空题答案（根据手写题号归位，仅去除题号前缀，不重排）
            split_fill_answers = split_combined_fillblanks(questions, {order: info["answer"] for order, info in
                                                                       ocr_result.items()})
            for order, new_ans in split_fill_answers.items():
                if new_ans != ocr_result[order]["answer"]:
                    ocr_result[order]["answer"] = new_ans
                    logger.info(f"拆分填空题 {order}: 新答案 = {new_ans}")

            # ===== 填空题答案匹配到参考答案位置 =====
            ocr_result = match_fillblanks_to_reference(questions,
                                                       {order: info["answer"] for order, info in ocr_result.items()})
            logger.info("填空题答案已根据参考答案进行匹配归位")
            # =========================================

            # 将 ocr_result 中所有值转换为 {"answer": str} 格式，保持数据结构一致
            for order in ocr_result:
                if isinstance(ocr_result[order], str):
                    ocr_result[order] = {"exists": True, "answer": ocr_result[order]}

            # ---------- 选择题答案格式验证与二次纠错 ----------
            choice_orders = [q['question_order'] for q in questions if q.get('type') in ('choice', '选择题')]
            invalid_choices = []
            need_fix_choices = []
            for order in choice_orders:
                ans = ocr_result.get(order, {}).get("answer", "")
                if not ans:
                    continue
                if not re.fullmatch(r'[A-Za-z]+', ans):
                    invalid_choices.append(order)
                    logger.warning(f"选择题 {order} 答案非法: '{ans}'")
                    continue
                if len(ans) > 1 and ans.upper() not in ('AB', 'BC', 'CD', 'DE'):
                    invalid_choices.append(order)
                    continue
                ref = ""
                for q in questions:
                    if q['question_order'] == order:
                        ref = q.get('reference_answer', '').strip()
                        break
                if ref and ans.upper() != ref.upper():
                    need_fix_choices.append(order)
                    logger.warning(f"选择题 {order} 与参考答案不符: 识别'{ans}' vs 参考'{ref}'")

            if invalid_choices:
                logger.info(f"发现 {len(invalid_choices)} 道选择题答案异常，调用纠错模型...")
                corrected_answers = correct_answers_with_image(image_paths,
                                                               {order: info["answer"] for order, info in
                                                                ocr_result.items()},
                                                               questions)
                for order, new_ans in corrected_answers.items():
                    if order in invalid_choices and new_ans and re.fullmatch(r'[A-Za-z]', new_ans):
                        logger.info(f"纠错覆盖选择题 {order}: '{ocr_result[order]['answer']}' -> '{new_ans}'")
                        ocr_result[order]["answer"] = new_ans.upper()
                    elif order in invalid_choices:
                        logger.warning(f"选择题 {order} 纠错后仍为非法答案，清空")
                        ocr_result[order]["answer"] = ""

            if need_fix_choices:
                logger.info(f"发现 {len(need_fix_choices)} 道选择题可能与参考答案不符，调用二次识别...")
                partial_questions = [q for q in questions if q['question_order'] in need_fix_choices]
                corrected_answers = correct_answers_with_image(image_paths,
                                                               {order: info["answer"] for order, info in
                                                                ocr_result.items()},
                                                               partial_questions)
                for order in need_fix_choices:
                    new_ans = corrected_answers.get(order, "")
                    if new_ans and re.fullmatch(r'[A-Za-z]', new_ans) and new_ans.upper() != ocr_result[order][
                        "answer"]:
                        logger.info(
                            f"二次识别覆盖选择题 {order}: '{ocr_result[order]['answer']}' -> '{new_ans.upper()}'")
                        ocr_result[order]["answer"] = new_ans.upper()

            # ---------- 主观题完整性补充（针对简答题小题号优化） ----------
            # 使用正向匹配，确保所有主观题类型都覆盖
            subjective_types = ('essay', 'calculation', '简答题', '计算题', '论述题', '主观题', 'subjective')
            subjective_orders = [q['question_order'] for q in questions if q.get('type') in subjective_types]
            if not subjective_orders:  # 如果正向没匹配到，再尝试反向排除（兜底）
                subjective_orders = [q['question_order'] for q in questions
                                     if q.get('type') not in ('choice', '选择题', 'fill_blank', '填空题', 'true_false',
                                                              '判断题')]
            if subjective_orders:
                subjective_questions = [q for q in questions if q['question_order'] in subjective_orders]
                current_answers = {order: ocr_result.get(order, {}).get("answer", "") for order in subjective_orders}

                # 第一次补充提取
                refined_answers = refine_subjective_answers(
                    image_paths,
                    current_answers,
                    subjective_questions
                )
                for order in subjective_orders:
                    new_ans = refined_answers.get(order, "")
                    if new_ans != current_answers.get(order, ""):
                        logger.info(f"主观题补充 {order}: 原'{current_answers[order][:50]}...' 更新为更完整版本")
                        ocr_result[order]["answer"] = new_ans
                        current_answers[order] = new_ans

                # 二次检查：对于答案长度仍然小于20字符的简答题，再次调用细化
                short_orders = [order for order in subjective_orders
                                if len(current_answers.get(order, '')) < 20]
                if short_orders:
                    logger.info(f"有 {len(short_orders)} 道主观题答案过短，进行强化二次提取...")
                    short_questions = [q for q in questions if q['question_order'] in short_orders]
                    second_refine = refine_subjective_answers(
                        image_paths,
                        {order: current_answers[order] for order in short_orders},
                        short_questions
                    )
                    for order in short_orders:
                        new_ans = second_refine.get(order, "")
                        if new_ans != current_answers.get(order, ""):
                            logger.info(
                                f"主观题二次强化 {order}: 答案长度从 {len(current_answers[order])} 增加到 {len(new_ans)}")
                            ocr_result[order]["answer"] = new_ans

                logger.info(f"主观题完整性补充完成，共处理 {len(subjective_orders)} 道题")
            # -------------------------------------------------------------

            # ---------- 全局填空题答案清洗（兜底） ----------
            for q in questions:
                if q.get('type') in ['填空题', 'fill_blank']:
                    order = q['question_order']
                    ans = ocr_result.get(order, {}).get("answer", "")
                    if ans:
                        cleaned = re.sub(
                            r'^\s*'
                            r'(?:\(\s*\d+\s*\)|（\s*\d+\s*）|[①②③④⑤⑥⑦⑧⑨⑩]+|\d+[\.、:：）)\u00A0]\s*)+',
                            '', ans
                        ).strip()
                        if cleaned and cleaned != ans:
                            logger.info(f"全局清洗填空题 {order}: '{ans}' -> '{cleaned}'")
                            ocr_result[order]["answer"] = cleaned

            # ---------- 手写题号智能清空 ----------
            total_questions = len(questions)
            for q in questions:
                order = q['question_order']
                ans = ocr_result.get(order, {}).get("answer", "")
                if not ans:
                    continue
                m = re.fullmatch(r'\s*(\d{1,3})\s*[\.、]\s*', ans)
                if m:
                    num_val = int(m.group(1))
                    if 1 <= num_val <= total_questions:
                        logger.info(f"题号 {order} 答案疑似手写题号，已清空: '{ans}'")
                        ocr_result[order]["answer"] = ""

            # ===== 诊断日志：输出当前填空题答案 =====
            fill_orders = [q['question_order'] for q in questions if q.get('type') in ['填空题', 'fill_blank']]
            for o in fill_orders:
                logger.info(f"诊断：填空题 {o} 最终答案 = '{ocr_result.get(o, {}).get('answer', '')}'")
            # ====================================

            # 评分
            total_score = 0.0
            for q in questions:
                qid = q["id"]
                order = q['question_order']
                student_answer = ocr_result.get(order, {}).get("answer", "")
                percent_score = score_only(q, student_answer)
                max_score = float(q.get("max_score", 100))
                actual_score = round((percent_score / 100.0) * max_score)
                actual_score = min(actual_score, max_score)
                total_score += actual_score

                with engine.connect() as conn:
                    conn.execute(
                        text("""
                             INSERT INTO student_scores (exam_id, student_id, question_id, score, student_answer)
                             VALUES (:exam_id, :student_id, :question_id, :score, :student_answer) ON DUPLICATE KEY
                             UPDATE
                                 score =
                             VALUES (score), student_answer =
                             VALUES (student_answer), updated_at = CURRENT_TIMESTAMP
                             """),
                        {
                            "exam_id": exam_id,
                            "student_id": student_id,
                            "question_id": qid,
                            "score": actual_score,
                            "student_answer": student_answer
                        }
                    )
                    conn.commit()

            if exam_total_score is not None and total_score > exam_total_score:
                logger.warning(
                    f"学生 {student_id} ({student['name']}) 总分 {total_score} 超过考试总分 {exam_total_score}")

            processed += 1
            with engine.connect() as conn:
                conn.execute(
                    text("UPDATE grading_jobs SET processed_students = :processed WHERE id = :job_id"),
                    {"processed": processed, "job_id": job_id}
                )
                conn.commit()

        with engine.connect() as conn:
            conn.execute(
                text("UPDATE grading_jobs SET status = 'completed' WHERE id = :job_id"),
                {"job_id": job_id}
            )
            conn.commit()
        logger.info(f"阅卷任务完成：exam_id={exam_id}, job_id={job_id}")

    except Exception as e:
        logger.exception(f"阅卷任务失败：exam_id={exam_id}, job_id={job_id}")
        with engine.connect() as conn:
            conn.execute(
                text("UPDATE grading_jobs SET status = 'failed' WHERE id = :job_id"),
                {"job_id": job_id}
            )
            conn.commit()


# ==================== API 端点 ====================
@router.post("/api/exams/{exam_id}/grade")
async def start_grading(exam_id: int):
    try:
        with engine.connect() as conn:
            exam = conn.execute(
                text("SELECT exam_id FROM exams WHERE exam_id = :exam_id"),
                {"exam_id": exam_id}
            ).fetchone()
            if not exam:
                raise HTTPException(status_code=404, detail=f"考试 {exam_id} 不存在")

            existing_job = conn.execute(
                text("SELECT id FROM grading_jobs WHERE exam_id = :exam_id AND status IN ('pending', 'processing')"),
                {"exam_id": exam_id}
            ).fetchone()
            if existing_job:
                raise HTTPException(status_code=400, detail="该考试已有阅卷任务正在进行中")

            result = conn.execute(
                text("INSERT INTO grading_jobs (exam_id, status) VALUES (:exam_id, 'pending')"),
                {"exam_id": exam_id}
            )
            conn.commit()
            job_id = result.lastrowid

        asyncio.create_task(process_grading(exam_id, job_id))

        return {
            "code": 1,
            "msg": "阅卷任务已启动",
            "data": {"job_id": job_id, "exam_id": exam_id, "status": "pending"}
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"启动阅卷失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"启动阅卷失败: {str(e)}")


@router.get("/api/grading/jobs/{job_id}")
async def get_grading_job_status(job_id: int):
    try:
        with engine.connect() as conn:
            job = conn.execute(
                text("""
                SELECT id, exam_id, status, total_students, processed_students, created_at, updated_at
                FROM grading_jobs
                WHERE id = :job_id
                """),
                {"job_id": job_id}
            ).fetchone()
            if not job:
                raise HTTPException(status_code=404, detail="任务不存在")

            return {
                "code": 1,
                "msg": "获取成功",
                "data": {
                    "job_id": job.id,
                    "exam_id": job.exam_id,
                    "status": job.status,
                    "total_students": job.total_students,
                    "processed_students": job.processed_students,
                    "created_at": job.created_at.isoformat() if job.created_at else None,
                    "updated_at": job.updated_at.isoformat() if job.updated_at else None
                }
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取任务状态失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取任务状态失败: {str(e)}")


@router.get("/api/exams/{exam_id}/grading-progress")
def get_grading_progress(exam_id: int):
    try:
        with engine.connect() as conn:
            total = conn.execute(
                text("SELECT COUNT(*) FROM exam_students WHERE exam_id = :exam_id"),
                {"exam_id": exam_id}
            ).scalar()
            graded = conn.execute(
                text("SELECT COUNT(DISTINCT student_id) FROM student_scores WHERE exam_id = :exam_id"),
                {"exam_id": exam_id}
            ).scalar()
        return {"code": 1, "data": {"total": total, "graded": graded}}
    except Exception as e:
        logger.error(f"获取阅卷进度失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))