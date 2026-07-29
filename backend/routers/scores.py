from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session
import logging
from typing import Dict, Optional
from pydantic import BaseModel
from backend.database import engine, get_db
from fastapi.responses import StreamingResponse
import pandas as pd
import io
from urllib.parse import quote

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/api/exams/{exam_id}/scores")
def get_exam_scores(exam_id: int):
    try:
        with engine.connect() as conn:
            # 1. 考试信息
            exam = conn.execute(
                text("SELECT exam_id, exam_name, total_score, total_questions FROM exams WHERE exam_id = :exam_id"),
                {"exam_id": exam_id}
            ).fetchone()
            if not exam:
                raise HTTPException(status_code=404, detail=f"考试 {exam_id} 不存在")

            # 动态计算考试总分
            if exam.total_score is None:
                total_score_result = conn.execute(
                    text("""
                        SELECT COALESCE(SUM(q.score), 0) 
                        FROM questions q 
                        INNER JOIN exam_questions eq ON q.id = eq.question_id 
                        WHERE eq.exam_id = :exam_id
                    """),
                    {"exam_id": exam_id}
                ).scalar()
                exam_total = float(total_score_result) if total_score_result is not None else None
            else:
                exam_total = float(exam.total_score)

            exam_info = {
                "exam_id": exam.exam_id,
                "exam_name": exam.exam_name,
                "total_score": exam_total,
                "total_questions": exam.total_questions
            }

            # 2. 学生列表
            students_result = conn.execute(
                text("""
                SELECT s.student_id, s.name, s.student_number, s.class
                FROM students s
                INNER JOIN exam_students es ON s.student_id = es.student_id
                WHERE es.exam_id = :exam_id
                ORDER BY es.sort_order ASC, s.student_number ASC
                """),
                {"exam_id": exam_id}
            )
            students_list = [dict(row._mapping) for row in students_result.fetchall()]
            if not students_list:
                return {"code": 1, "msg": "获取成功", "data": {"exam_info": exam_info, "students": []}}

            # 3. 题目列表（包含满分）
            questions_result = conn.execute(
                text("""
                SELECT q.id, q.type, q.content, q.score as max_score, eq.question_order
                FROM questions q
                INNER JOIN exam_questions eq ON q.id = eq.question_id
                WHERE eq.exam_id = :exam_id
                ORDER BY eq.question_order
                """),
                {"exam_id": exam_id}
            )
            questions = [dict(row._mapping) for row in questions_result.fetchall()]

            # 4. 得分明细
            scores_result = conn.execute(
                text("""
                SELECT DISTINCT student_id, question_id, score, student_answer, recognition_correct, corrected_answer, manual_reviewed, updated_at
                FROM student_scores
                WHERE exam_id = :exam_id
                """),
                {"exam_id": exam_id}
            )
            scores_by_student: Dict[int, Dict[int, dict]] = {}
            graded_at_map = {}
            for row in scores_result.fetchall():
                sid = row.student_id
                if sid not in scores_by_student:
                    scores_by_student[sid] = {}
                scores_by_student[sid][row.question_id] = {
                    "score": float(row.score),
                    "student_answer": row.student_answer,
                    "recognition_correct": bool(row.recognition_correct) if row.recognition_correct is not None else True,
                    "corrected_answer": row.corrected_answer,
                    "manual_reviewed": bool(row.manual_reviewed) if row.manual_reviewed is not None else False,
                    "updated_at": row.updated_at
                }
                if sid not in graded_at_map or (row.updated_at and row.updated_at > graded_at_map[sid]):
                    graded_at_map[sid] = row.updated_at

            # 5. 组装学生数据
            student_data_list = []
            for student in students_list:
                sid = student["student_id"]
                student_scores = scores_by_student.get(sid, {})

                question_scores = []
                total_score = 0.0
                choice_total = 0.0
                fill_total = 0.0
                subjective_total = 0.0
                for q in questions:
                    qid = q["id"]
                    score_info = student_scores.get(qid)
                    score = score_info["score"] if score_info else None
                    if score is not None:
                        total_score += score
                        qtype = q["type"]
                        if qtype in ("选择题", "choice"):
                            choice_total += score
                        elif qtype in ("填空题", "fill_blank"):
                            fill_total += score
                        else:
                            subjective_total += score
                    question_scores.append({
                        "question_id": qid,
                        "question_order": q["question_order"],
                        "content": q["content"],
                        "type": q["type"],
                        "score": score,
                        "max_score": float(q["max_score"]) if q["max_score"] is not None else None,
                        "student_answer": score_info["student_answer"] if score_info else None,
                        "corrected_answer": score_info["corrected_answer"] if score_info else None,
                        "recognition_correct": score_info["recognition_correct"] if score_info else True,
                        "manual_reviewed": score_info["manual_reviewed"] if score_info else False
                    })

                if exam_total is not None and total_score > exam_total:
                    logger.warning(f"学生 {student['name']} 总分 {total_score} 超过考试总分 {exam_total}，已截断")
                    total_score = exam_total

                student_data = {
                    "student_id": sid,
                    "name": student["name"],
                    "student_number": student["student_number"],
                    "class": student["class"],
                    "total_score": total_score if total_score > 0 else None,
                    "choice_total": choice_total if choice_total > 0 else None,
                    "fill_total": fill_total if fill_total > 0 else None,
                    "subjective_total": subjective_total if subjective_total > 0 else None,
                    "question_scores": question_scores,
                    "graded_at": graded_at_map.get(sid).isoformat() if graded_at_map.get(sid) else None
                }
                student_data_list.append(student_data)

            # 6. 排名计算
            scored_students = [s for s in student_data_list if s["total_score"] is not None]
            scored_students.sort(key=lambda x: x["total_score"], reverse=True)
            rank = 1
            for i, s in enumerate(scored_students):
                if i > 0 and s["total_score"] != scored_students[i-1]["total_score"]:
                    rank = i + 1
                s["rank"] = rank
            for s in student_data_list:
                if s["total_score"] is None:
                    s["rank"] = None

            # 按学生ID升序排列，便于按顺序复核
            student_data_list.sort(key=lambda x: x["student_id"])

            return {
                "code": 1,
                "msg": "获取成功",
                "data": {
                    "exam_info": exam_info,
                    "students": student_data_list
                }
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取考试成绩失败 (exam_id={exam_id}): {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取考试成绩失败: {str(e)}")


class ScoreUpdate(BaseModel):
    score: float
    recognition_correct: Optional[bool] = None
    corrected_answer: Optional[str] = None
    manual_reviewed: Optional[bool] = None


@router.put("/api/exams/{exam_id}/scores/{student_id}/{question_id}")
def update_question_score(
    exam_id: int,
    student_id: int,
    question_id: int,
    data: ScoreUpdate,
    db: Session = Depends(get_db)
):
    try:
        with db as session:
            # 删除重复记录（保留最新）
            session.execute(
                text("""
                DELETE FROM student_scores
                WHERE exam_id = :exam_id AND student_id = :student_id AND question_id = :question_id
                AND id NOT IN (
                    SELECT * FROM (
                        SELECT MIN(id) FROM student_scores
                        WHERE exam_id = :exam_id AND student_id = :student_id AND question_id = :question_id
                    ) AS tmp
                )
                """),
                {"exam_id": exam_id, "student_id": student_id, "question_id": question_id}
            )

            update_fields = "score = VALUES(score)"
            values = {
                "exam_id": exam_id,
                "student_id": student_id,
                "question_id": question_id,
                "score": data.score
            }
            recognition_value = "TRUE"
            if data.recognition_correct is not None:
                update_fields += ", recognition_correct = VALUES(recognition_correct)"
                recognition_value = ":recognition_correct"
                values["recognition_correct"] = data.recognition_correct

            corrected_value = "NULL"
            if data.corrected_answer is not None:
                update_fields += ", corrected_answer = VALUES(corrected_answer)"
                corrected_value = ":corrected_answer"
                values["corrected_answer"] = data.corrected_answer

            manual_reviewed_value = "NULL"
            if data.manual_reviewed is not None:
                update_fields += ", manual_reviewed = VALUES(manual_reviewed)"
                manual_reviewed_value = ":manual_reviewed"
                values["manual_reviewed"] = 1 if data.manual_reviewed else 0

            session.execute(
                text(f"""
                INSERT INTO student_scores (exam_id, student_id, question_id, score, recognition_correct, corrected_answer, manual_reviewed)
                VALUES (:exam_id, :student_id, :question_id, :score, {recognition_value}, {corrected_value}, {manual_reviewed_value})
                ON DUPLICATE KEY UPDATE {update_fields}, updated_at = CURRENT_TIMESTAMP
                """),
                values
            )
            session.commit()
            return {"code": 1, "msg": "分数更新成功"}
    except Exception as e:
        logger.error(f"更新分数失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"更新分数失败: {str(e)}")


@router.get("/api/exams/{exam_id}/subjective-questions")
def get_subjective_questions(exam_id: int):
    """获取考试中的所有主观题（问答题）"""
    try:
        with engine.connect() as conn:
            exam = conn.execute(
                text("SELECT exam_id FROM exams WHERE exam_id = :exam_id"),
                {"exam_id": exam_id}
            ).fetchone()
            if not exam:
                raise HTTPException(status_code=404, detail="考试不存在")

            result = conn.execute(
                text("""
                    SELECT q.id, q.content, q.reference_answer, q.scoring_rules, q.score as max_score, eq.question_order
                    FROM questions q
                    INNER JOIN exam_questions eq ON q.id = eq.question_id
                    WHERE eq.exam_id = :exam_id
                      AND q.type NOT IN ('选择题', '填空题', '判断题', 'choice', 'fill_blank', 'true_false')
                    ORDER BY eq.question_order
                """),
                {"exam_id": exam_id}
            )
            questions = []
            for row in result.fetchall():
                questions.append({
                    "id": row.id,
                    "question_order": row.question_order,
                    "content": row.content,
                    "reference_answer": row.reference_answer,
                    "scoring_rules": row.scoring_rules,
                    "max_score": float(row.max_score) if row.max_score is not None else 0
                })
            return {"code": 1, "msg": "获取成功", "data": questions}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取主观题失败 (exam_id={exam_id}): {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取主观题失败: {str(e)}")


@router.get("/api/exams/{exam_id}/scores/{question_id}/students")
def get_question_students(exam_id: int, question_id: int):
    """获取某道主观题下所有学生的作答信息"""
    try:
        with engine.connect() as conn:
            exam = conn.execute(
                text("SELECT exam_id FROM exams WHERE exam_id = :exam_id"),
                {"exam_id": exam_id}
            ).fetchone()
            if not exam:
                raise HTTPException(status_code=404, detail="考试不存在")

            # 题目信息
            question = conn.execute(
                text("""
                    SELECT q.id, q.content, q.reference_answer, q.scoring_rules, q.score as max_score, eq.question_order
                    FROM questions q
                    INNER JOIN exam_questions eq ON q.id = eq.question_id
                    WHERE eq.exam_id = :exam_id AND q.id = :question_id
                """),
                {"exam_id": exam_id, "question_id": question_id}
            ).fetchone()
            if not question:
                raise HTTPException(status_code=404, detail="题目不存在")

            # 所有学生
            students_result = conn.execute(
                text("""
                    SELECT s.student_id, s.student_number, s.name, s.class, es.sort_order
                    FROM students s
                    INNER JOIN exam_students es ON s.student_id = es.student_id
                    WHERE es.exam_id = :exam_id
                    ORDER BY es.sort_order ASC, s.student_number ASC
                """),
                {"exam_id": exam_id}
            )
            students = [dict(row._mapping) for row in students_result.fetchall()]

            # 得分信息
            scores_result = conn.execute(
                text("""
                    SELECT student_id, score, student_answer, corrected_answer, recognition_correct, manual_reviewed
                    FROM student_scores
                    WHERE exam_id = :exam_id AND question_id = :question_id
                """),
                {"exam_id": exam_id, "question_id": question_id}
            )
            score_map = {}
            for row in scores_result.fetchall():
                score_map[row.student_id] = {
                    "score": float(row.score) if row.score is not None else None,
                    "student_answer": row.student_answer,
                    "corrected_answer": row.corrected_answer,
                    "recognition_correct": bool(row.recognition_correct) if row.recognition_correct is not None else True,
                    "manual_reviewed": bool(row.manual_reviewed) if row.manual_reviewed is not None else False
                }

            result = []
            for s in students:
                sid = s["student_id"]
                score_info = score_map.get(sid, {})
                result.append({
                    "student_id": sid,
                    "student_number": s["student_number"],
                    "name": s["name"],
                    "class": s["class"],
                    "score": score_info.get("score"),
                    "student_answer": score_info.get("student_answer"),
                    "corrected_answer": score_info.get("corrected_answer"),
                    "recognition_correct": score_info.get("recognition_correct", True),
                    "manual_reviewed": score_info.get("manual_reviewed", False)
                })

            return {
                "code": 1,
                "msg": "获取成功",
                "data": {
                    "question": {
                        "id": question.id,
                        "question_order": question.question_order,
                        "content": question.content,
                        "reference_answer": question.reference_answer,
                        "scoring_rules": question.scoring_rules,
                        "max_score": float(question.max_score) if question.max_score is not None else 0
                    },
                    "students": result
                }
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取题目学生作答失败 (exam_id={exam_id}, question_id={question_id}): {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取学生作答失败: {str(e)}")


@router.get("/api/exams/{exam_id}/export")
def export_exam_scores(exam_id: int):
    """导出考试成绩为 Excel 文件"""
    try:
        with engine.connect() as conn:
            exam = conn.execute(
                text("SELECT exam_id, exam_name, total_score FROM exams WHERE exam_id = :exam_id"),
                {"exam_id": exam_id}
            ).fetchone()
            if not exam:
                raise HTTPException(status_code=404, detail="考试不存在")

            students_result = conn.execute(
                text("""
                    SELECT s.student_id, s.student_number, s.name, s.class,
                           COALESCE(SUM(ss.score), 0) as total_score
                    FROM students s
                    INNER JOIN exam_students es ON s.student_id = es.student_id
                    LEFT JOIN student_scores ss ON ss.student_id = s.student_id AND ss.exam_id = :exam_id
                    WHERE es.exam_id = :exam_id
                    GROUP BY s.student_id
                    ORDER BY total_score DESC
                """),
                {"exam_id": exam_id}
            )
            students = []
            for row in students_result:
                students.append({
                    "student_id": row.student_id,
                    "student_number": row.student_number,
                    "name": row.name,
                    "class": getattr(row, 'class'),
                    "total_score": row.total_score
                })

            questions_result = conn.execute(
                text("""
                    SELECT q.id, q.content, eq.question_order, q.score as max_score
                    FROM questions q
                    INNER JOIN exam_questions eq ON q.id = eq.question_id
                    WHERE eq.exam_id = :exam_id
                    ORDER BY eq.question_order
                """),
                {"exam_id": exam_id}
            )
            questions = [dict(row._mapping) for row in questions_result.fetchall()]

            scores_result = conn.execute(
                text("""
                    SELECT student_id, question_id, score
                    FROM student_scores
                    WHERE exam_id = :exam_id
                """),
                {"exam_id": exam_id}
            )
            score_map = {}
            for row in scores_result:
                sid = row.student_id
                qid = row.question_id
                if sid not in score_map:
                    score_map[sid] = {}
                score_map[sid][qid] = row.score

            # 构建导出数据
            rows = []
            for student in students:
                row_data = {
                    "学号": student["student_number"],
                    "姓名": student["name"],
                    "班级": student["class"],
                    "总分": student["total_score"]
                }
                for q in questions:
                    qid = q["id"]
                    score = score_map.get(student["student_id"], {}).get(qid, "")
                    row_data[f"第{q['question_order']}题 ({q['max_score']}分)"] = score
                rows.append(row_data)

            df = pd.DataFrame(rows)
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, sheet_name="成绩表", index=False)
                worksheet = writer.sheets["成绩表"]
                for i, col in enumerate(df.columns):
                    max_len = max(df[col].astype(str).map(len).max(), len(col)) + 2
                    worksheet.set_column(i, i, min(max_len, 30))
            output.seek(0)

            filename = f"exam_{exam.exam_name}_{exam_id}_scores.xlsx"
            encoded_filename = quote(filename)
            return StreamingResponse(
                output,
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"}
            )
    except Exception as e:
        logger.error(f"导出成绩失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"导出失败: {str(e)}")


@router.get("/api/exams/{exam_id}/export-objective")
def export_objective_answers(exam_id: int):
    """导出选择题和填空题的学生答案到 Excel"""
    try:
        with engine.connect() as conn:
            # 1. 获取考试信息
            exam = conn.execute(
                text("SELECT exam_id, exam_name FROM exams WHERE exam_id = :exam_id"),
                {"exam_id": exam_id}
            ).fetchone()
            if not exam:
                raise HTTPException(status_code=404, detail="考试不存在")

            # 2. 获取该考试的所有客观题（选择题、填空题）
            questions_result = conn.execute(
                text("""
                    SELECT q.id, q.content, q.reference_answer, eq.question_order
                    FROM questions q
                    INNER JOIN exam_questions eq ON q.id = eq.question_id
                    WHERE eq.exam_id = :exam_id
                        AND q.type IN ('选择题', '填空题', 'choice', 'fill_blank')
                    ORDER BY eq.question_order
                """),
                {"exam_id": exam_id}
            )
            questions = [dict(row._mapping) for row in questions_result.fetchall()]
            if not questions:
                raise HTTPException(status_code=400, detail="该考试没有选择题或填空题")

            # 3. 获取所有学生（已关联该考试）
            students_result = conn.execute(
                text("""
                    SELECT s.student_id, s.student_number, s.name, s.class
                    FROM students s
                    INNER JOIN exam_students es ON s.student_id = es.student_id
                    WHERE es.exam_id = :exam_id
                    ORDER BY es.sort_order
                """),
                {"exam_id": exam_id}
            )
            students = [dict(row._mapping) for row in students_result.fetchall()]
            if not students:
                raise HTTPException(status_code=400, detail="该考试没有学生")

            # 4. 获取每个学生每道客观题的答案和得分
            scores_result = conn.execute(
                text("""
                    SELECT student_id, question_id, student_answer, score
                    FROM student_scores
                    WHERE exam_id = :exam_id
                """),
                {"exam_id": exam_id}
            )
            answer_map = {}
            for row in scores_result:
                sid = row.student_id
                qid = row.question_id
                if sid not in answer_map:
                    answer_map[sid] = {}
                answer_map[sid][qid] = {
                    "answer": row.student_answer or "",
                    "score": row.score
                }

            # 5. 构建 Excel 数据
            rows = []
            for student in students:
                sid = student["student_id"]
                row_data = {
                    "学号": student["student_number"],
                    "姓名": student["name"],
                    "班级": student["class"],
                }
                for q in questions:
                    qid = q["id"]
                    info = answer_map.get(sid, {}).get(qid, {})
                    row_data[f"第{q['question_order']}题\n学生答案"] = info.get("answer", "")
                    row_data[f"第{q['question_order']}题\n参考答案"] = q["reference_answer"] or ""
                    row_data[f"第{q['question_order']}题\n得分"] = info.get("score", "")
                rows.append(row_data)

            df = pd.DataFrame(rows)
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, sheet_name="客观题答案", index=False)
                # 调整列宽
                worksheet = writer.sheets["客观题答案"]
                for i, col in enumerate(df.columns):
                    max_len = max(df[col].astype(str).map(len).max(), len(col)) + 2
                    worksheet.set_column(i, i, min(max_len, 30))
            output.seek(0)

            filename = f"exam_{exam.exam_name}_{exam_id}_objective_answers.xlsx"
            encoded_filename = quote(filename)
            return StreamingResponse(
                output,
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"}
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"导出客观题答案失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"导出失败: {str(e)}")

@router.get("/api/exams/{exam_id}/export-subjective")
def export_subjective_answers(exam_id: int):
    """导出主观题（简答题/计算题等）的学生答案到 Excel"""
    try:
        with engine.connect() as conn:
            # 1. 获取考试信息
            exam = conn.execute(
                text("SELECT exam_id, exam_name FROM exams WHERE exam_id = :exam_id"),
                {"exam_id": exam_id}
            ).fetchone()
            if not exam:
                raise HTTPException(status_code=404, detail="考试不存在")

            # 2. 获取该考试的所有主观题（排除选择题、填空题、判断题）
            questions_result = conn.execute(
                text("""
                    SELECT q.id, q.content, q.reference_answer, eq.question_order
                    FROM questions q
                    INNER JOIN exam_questions eq ON q.id = eq.question_id
                    WHERE eq.exam_id = :exam_id
                        AND q.type NOT IN ('选择题', '填空题', '判断题', 'choice', 'fill_blank', 'true_false')
                    ORDER BY eq.question_order
                """),
                {"exam_id": exam_id}
            )
            questions = [dict(row._mapping) for row in questions_result.fetchall()]
            if not questions:
                raise HTTPException(status_code=400, detail="该考试没有主观题")

            # 3. 获取所有学生（已关联该考试）
            students_result = conn.execute(
                text("""
                    SELECT s.student_id, s.student_number, s.name, s.class
                    FROM students s
                    INNER JOIN exam_students es ON s.student_id = es.student_id
                    WHERE es.exam_id = :exam_id
                    ORDER BY es.sort_order
                """),
                {"exam_id": exam_id}
            )
            students = [dict(row._mapping) for row in students_result.fetchall()]
            if not students:
                raise HTTPException(status_code=400, detail="该考试没有学生")

            # 4. 获取每个学生每道主观题的答案和得分
            scores_result = conn.execute(
                text("""
                    SELECT student_id, question_id, student_answer, score
                    FROM student_scores
                    WHERE exam_id = :exam_id
                """),
                {"exam_id": exam_id}
            )
            answer_map = {}
            for row in scores_result:
                sid = row.student_id
                qid = row.question_id
                if sid not in answer_map:
                    answer_map[sid] = {}
                answer_map[sid][qid] = {
                    "answer": row.student_answer or "",
                    "score": row.score
                }

            # 5. 构建 Excel 数据
            rows = []
            for student in students:
                sid = student["student_id"]
                row_data = {
                    "学号": student["student_number"],
                    "姓名": student["name"],
                    "班级": student["class"],
                }
                for q in questions:
                    qid = q["id"]
                    info = answer_map.get(sid, {}).get(qid, {})
                    row_data[f"第{q['question_order']}题\n题目内容"] = q["content"] or ""
                    row_data[f"第{q['question_order']}题\n学生答案"] = info.get("answer", "")
                    row_data[f"第{q['question_order']}题\n参考答案"] = q["reference_answer"] or ""
                    row_data[f"第{q['question_order']}题\n得分"] = info.get("score", "")
                rows.append(row_data)

            df = pd.DataFrame(rows)
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, sheet_name="主观题答案", index=False)
                worksheet = writer.sheets["主观题答案"]
                for i, col in enumerate(df.columns):
                    max_len = max(df[col].astype(str).map(len).max(), len(col)) + 2
                    worksheet.set_column(i, i, min(max_len, 50))
            output.seek(0)

            filename = f"exam_{exam.exam_name}_{exam_id}_subjective_answers.xlsx"
            encoded_filename = quote(filename)
            return StreamingResponse(
                output,
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"}
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"导出主观题答案失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"导出失败: {str(e)}")