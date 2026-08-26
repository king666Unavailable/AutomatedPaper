from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict
from sqlalchemy import text
import logging

from backend.database import engine

logger = logging.getLogger(__name__)

router = APIRouter()

# 题型归一化映射
TYPE_MAP = {
    "选择题": "选择题",
    "choice": "选择题",
    "填空题": "填空题",
    "fill_blank": "填空题",
    "判断题": "判断题",
    "true_false": "判断题",
}


def normalize_type(qtype):
    """将题型归一到中文名称，其余归为问答题"""
    if qtype in TYPE_MAP:
        return TYPE_MAP[qtype]
    return "问答题"


class QuestionAnalysisUpdate(BaseModel):
    knowledge_point: Optional[str] = None


class TypeAnalysisUpdate(BaseModel):
    question_type: str
    analysis: Optional[str] = ""


class OverallAnalysisUpdate(BaseModel):
    overall_analysis: Optional[str] = ""


@router.get("/api/exams/{exam_id}/analysis")
def get_exam_analysis(exam_id: int):
    """获取考试分析数据：各题得分统计、题型分析、整体分析"""
    try:
        with engine.connect() as conn:
            exam = conn.execute(
                text("SELECT exam_id, exam_name, overall_analysis FROM exams WHERE exam_id = :exam_id"),
                {"exam_id": exam_id}
            ).fetchone()
            if not exam:
                raise HTTPException(status_code=404, detail="考试不存在")

            # 参考学生总数
            student_count = conn.execute(
                text("SELECT COUNT(*) FROM exam_students WHERE exam_id = :exam_id"),
                {"exam_id": exam_id}
            ).scalar() or 0

            # 各题得分统计
            questions_result = conn.execute(
                text("""
                    SELECT eq.question_order, q.id, q.type, q.content, q.score as max_score,
                           q.knowledge_point, COUNT(ss.id) as scored_count, AVG(ss.score) as avg_score
                    FROM exam_questions eq
                    INNER JOIN questions q ON q.id = eq.question_id
                    LEFT JOIN student_scores ss ON ss.exam_id = eq.exam_id AND ss.question_id = eq.question_id
                    WHERE eq.exam_id = :exam_id
                    GROUP BY eq.question_order, q.id
                    ORDER BY eq.question_order
                """),
                {"exam_id": exam_id}
            )
            questions = []
            for row in questions_result.fetchall():
                max_score = float(row.max_score) if row.max_score is not None else 0
                avg_score = float(row.avg_score) if row.avg_score is not None else 0
                questions.append({
                    "question_id": row.id,
                    "question_order": row.question_order,
                    "type": normalize_type(row.type),
                    "content": row.content,
                    "knowledge_point": row.knowledge_point,
                    "max_score": max_score,
                    "avg_score": round(avg_score, 2),
                    "scored_count": row.scored_count or 0,
                    "student_count": student_count,
                    "rate": round((avg_score / max_score * 100), 2) if max_score > 0 else 0
                })

            # 题型分析
            type_result = conn.execute(
                text("SELECT question_type, analysis FROM exam_type_analyses WHERE exam_id = :exam_id"),
                {"exam_id": exam_id}
            )
            type_analyses: Dict[str, str] = {}
            for row in type_result.fetchall():
                type_analyses[row.question_type] = row.analysis or ""

            return {
                "code": 1,
                "msg": "获取成功",
                "data": {
                    "exam_name": exam.exam_name,
                    "overall_analysis": exam.overall_analysis or "",
                    "questions": questions,
                    "type_analyses": type_analyses
                }
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取考试分析失败 (exam_id={exam_id}): {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取考试分析失败: {str(e)}")


@router.put("/api/exams/{exam_id}/analysis/question/{question_id}")
def update_question_knowledge(exam_id: int, question_id: int, data: QuestionAnalysisUpdate):
    """更新某题的知识点"""
    try:
        with engine.connect() as conn:
            # 确认题目属于该考试
            exists = conn.execute(
                text("""
                    SELECT 1 FROM exam_questions
                    WHERE exam_id = :exam_id AND question_id = :question_id
                """),
                {"exam_id": exam_id, "question_id": question_id}
            ).fetchone()
            if not exists:
                raise HTTPException(status_code=404, detail="该考试中不存在此题目")

            conn.execute(
                text("UPDATE questions SET knowledge_point = :knowledge_point WHERE id = :question_id"),
                {"knowledge_point": data.knowledge_point, "question_id": question_id}
            )
            conn.commit()
            return {"code": 1, "msg": "知识点已保存"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"保存知识点失败 (question_id={question_id}): {str(e)}")
        raise HTTPException(status_code=500, detail=f"保存知识点失败: {str(e)}")


@router.put("/api/exams/{exam_id}/analysis/type")
def update_type_analysis(exam_id: int, data: TypeAnalysisUpdate):
    """保存某题型的分析"""
    try:
        with engine.connect() as conn:
            conn.execute(
                text("""
                    INSERT INTO exam_type_analyses (exam_id, question_type, analysis)
                    VALUES (:exam_id, :question_type, :analysis)
                    ON DUPLICATE KEY UPDATE analysis = :analysis
                """),
                {
                    "exam_id": exam_id,
                    "question_type": data.question_type,
                    "analysis": data.analysis
                }
            )
            conn.commit()
            return {"code": 1, "msg": "题型分析已保存"}
    except Exception as e:
        logger.error(f"保存题型分析失败 (type={data.question_type}): {str(e)}")
        raise HTTPException(status_code=500, detail=f"保存题型分析失败: {str(e)}")


@router.put("/api/exams/{exam_id}/analysis/overall")
def update_overall_analysis(exam_id: int, data: OverallAnalysisUpdate):
    """保存试卷整体分析"""
    try:
        with engine.connect() as conn:
            conn.execute(
                text("UPDATE exams SET overall_analysis = :overall_analysis WHERE exam_id = :exam_id"),
                {"overall_analysis": data.overall_analysis, "exam_id": exam_id}
            )
            conn.commit()
            return {"code": 1, "msg": "整体分析已保存"}
    except Exception as e:
        logger.error(f"保存整体分析失败 (exam_id={exam_id}): {str(e)}")
        raise HTTPException(status_code=500, detail=f"保存整体分析失败: {str(e)}")
