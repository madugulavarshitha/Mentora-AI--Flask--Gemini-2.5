# 🌸 MENTORA AI — Intelligent Mentorship. Smarter Projects.

**AI-Powered Mentor–Intern Project Management & Evaluation Platform**

Built with **Python, Flask, Jinja2, pure CSS (Zero JavaScript), Google Gemini API, PostgreSQL/SQLite (SQLAlchemy), and RAG multi-agent orchestration**.

---

## 🎨 Visual Identity & Design Language

Inspired by modern, calm pastel workspace aesthetics:
- **Palette**: Primary Lavender (`#DCD6F7`), Soft Purple (`#7C5CFC`), Pastel Blue (`#C9E4F6`), Mint (`#CDEFE3`), Peach (`#FFDCC8`), Cream (`#FFFDF8`), Crisp White (`#FFFFFF`).
- **Layout**: Split-screen authentication, rounded cards (24px radius), soft shadows, and clean modern typography.
- **Zero JavaScript**: Pure CSS interactions, standard HTML5 forms, server-side validation.

---

## 🚀 Key Modules & Capabilities

1. **Dedicated Authentication Portals**:
   - `/` — Public Landing Page (Hero, Features, Overview)
   - `/mentor/signin` & `/mentor/signup` — Mentor Leadership Workspace
   - `/intern/signin` & `/intern/signup` — Intern Learning & Growth Workspace
2. **AI Project Generation (Gemini AI)**: Generates complete project curriculums (Problem Statement, Abstract, Objectives, Functional & Non-Functional Requirements, Scope, Deliverables).
3. **AI Technology Stack Recommendation**: Tailored programming languages, frameworks, databases, AI tools, and testing toolsets.
4. **Real-World Business Scenarios**: Synthesizes enterprise business context, challenges, user personas, and ROI benefits.
5. **AI Intern Matching Engine**: Semantic match scoring (0–100%), missing skill diagnostics, and workload risk assessment.
6. **Project Tracking & Health Matrix**: Progress tracking with `HEALTHY`, `NEEDS ATTENTION`, and `CRITICAL` diagnostic badges.
7. **Multi-Format Submissions & RAG Evaluation**: Upload **PDF**, **DOCX**, **XLSX**, and **TXT** files. Compares submissions against mentor reference benchmarks using semantic search.
8. **Actionable Feedback Reports**: Executive summaries, priority action items, required technical fixes, and approval status.
9. **Mentor AI Copilot**: Live context-aware conversational assistant.

---

## 💻 Quick Start & Running

### 1. Environment Setup
```bash
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure Environment (`.env`)
```env
SECRET_KEY=mentora-ai-master-secret-key-2025
GEMINI_API_KEY=your_gemini_api_key_here
DATABASE_URL=sqlite:///database.db
PORT=5000
```

### 3. Launch Application
```bash
python app.py
```
Open [http://127.0.0.1:5000](http://127.0.0.1:5000) in your browser.

---

## 🔑 Demo Accounts (Password: `password123`)

| Role | Username / Email | Dedicated Sign In |
| :--- | :--- | :--- |
| **Mentor** | `mentor1` / `sarah.jenkins@mentora.ai` | [/mentor/signin](http://127.0.0.1:5000/mentor/signin) |
| **Intern 1** | `intern_alex` / `alex.rivera@mentora.ai` | [/intern/signin](http://127.0.0.1:5000/intern/signin) |
| **Intern 2** | `intern_priya` / `priya.sharma@mentora.ai` | [/intern/signin](http://127.0.0.1:5000/intern/signin) |
