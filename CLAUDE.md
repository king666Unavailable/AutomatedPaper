# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

试卷图片分析和AI阅卷实验平台 (Automated Paper Grading & Analysis Platform). A Vue 3 + Vite frontend and FastAPI Python backend for managing exams, students, questions, answer-sheet images, and AI-assisted grading.

## Common Commands

### One-shot setup

- Initialize MySQL database: `mysql -u root -p exam_platform < backend/schema.sql`
- Install backend dependencies: `cd backend && python -m venv venv && source venv/bin/activate && pip install -r requirements.txt`
- Install frontend dependencies: `cd frontend && npm install`

### Run during development

- Backend: `cd backend && source venv/bin/activate && python app_main.py` (runs on http://localhost:8001)
- Frontend: `cd frontend && npm run dev` (runs on http://localhost:5173)
- Both services plus MySQL: `./start.sh` (creates venv if missing, installs deps, starts FastAPI and Vite; logs to `backend.log` and `frontend.log`)
- Stop services: `./stop.sh` (reads `backend.pid` and `frontend.pid`)

### Build

- Frontend production build: `cd frontend && npm run build`
- Preview production build: `cd frontend && npm run preview`

### Tests

No test framework is configured. There is no command to run tests or a single test.

## Architecture

### Backend

- Entry point: `backend/app_main.py`. Registers all routers and mounts `backend/uploads` at `/uploads`.
- Routers live in `backend/routers/`: `auth`, `exams`, `students`, `questions`, `answers`, `grading`, `scores`.
- Database layer: `backend/database.py` creates a SQLAlchemy engine from `DATABASE_CONFIG` in `backend/config.py`. `backend/models.py` defines ORM classes, but most routers execute raw SQL through `engine.connect()` rather than using the ORM session.
- Legacy file: `backend/main.py` is a minimal FastAPI stub on port 8000 and is not the active entry point.
- Configuration: `backend/config.py` holds `DATABASE_CONFIG`, `UPLOAD_DIR`, and `MM_MODEL_CONFIG` (multimodal model API key and endpoint).

### Frontend

- Entry point: `frontend/src/main.js` creates a Vue 3 app, loads `vue-router`, and installs Element Plus.
- Routing: `frontend/src/router/index.js` defines `/home`, `/login`, and `/exam/:exam_id`.
- The exam detail page `frontend/src/views/ExamDetail.vue` hosts tab components under `frontend/src/views/exam/`: `StudentManager.vue`, `QuestionManager.vue`, `AnswerManager.vue`, `AIGradingConsole.vue`, `ScoreManager.vue`.
- API calls in the frontend use hardcoded full URLs such as `http://localhost:8001/api/...`, so the Vite proxy configured in `frontend/vite.config.js` is bypassed.

### Database

- MySQL database `exam_platform`.
- Core tables: `exams`, `students`, `exam_students`, `questions`, `exam_questions`, `users`, `answer_sheets`, `student_scores`, `grading_jobs`.
- `student_scores.student_answer` stores the OCR-recognized student answer text; `recognition_correct` is a manual annotation flag for the recognition result.
- `students` and `questions` are global resource pools. An exam links to them through `exam_students` and `exam_questions`, allowing reuse across exams.

### AI grading and image handling

- `backend/routers/answers.py` receives answer-sheet images and stores them under `backend/uploads/answer_sheets/{exam_id}`. It also performs OpenCV preprocessing (EXIF orientation, skew correction, orientation detection).
- `backend/routers/grading.py` invokes the Qwen VL multimodal model configured in `MM_MODEL_CONFIG` to perform OCR and scoring.
- `backend/routers/scores.py` aggregates per-student, per-question scores from `student_scores`.

## Important notes

- `backend/config.py` contains a hardcoded multimodal API key. Avoid committing modifications that expose or leak this credential.
- Uploaded images are served statically from `/uploads`, relative to the backend working directory.
- Recent commits show active development in answer-sheet management, AI grading, score export, and name-matched import flows; check `backend/routers/answers.py`, `backend/routers/grading.py`, and `backend/routers/scores.py` for the latest behavior.
