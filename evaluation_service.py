import os
import json
from pathlib import Path
from database import get_db
from gemini_service import evaluate_submission_ai, generate_feedback_ai
from config import Config

def extract_text_from_file(file_path: str) -> str:
    """
    Extracts text content safely from Word Documents (.docx, .doc), RTF, PDF, XLSX, and text files.
    """
    full_path = Path(file_path)
    if not full_path.is_absolute():
        full_path = Config.BASE_DIR / file_path
        
    if not full_path.exists():
        return f"[File not found: {file_path}]"

    suffix = full_path.suffix.lower()
    
    # 1. Plain Text / Markdown / Code / JSON / CSV
    if suffix in ['.txt', '.md', '.json', '.py', '.html', '.css', '.csv']:
        try:
            with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()
        except Exception as e:
            return f"[Error reading text file: {e}]"
            
    # 2. PDF Files (PyMuPDF / fitz with PyPDF fallback)
    elif suffix == '.pdf':
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(full_path)
            text_chunks = []
            for page in doc:
                text_chunks.append(page.get_text())
            doc.close()
            return "\n".join(text_chunks)
        except Exception:
            try:
                import pypdf
                reader = pypdf.PdfReader(full_path)
                return "\n".join([page.extract_text() or '' for page in reader.pages])
            except Exception as e:
                return f"[Error extracting PDF text: {e}]"
            
    # 3. Modern Word Documents (.docx) - Paragraphs & Tables
    elif suffix == '.docx':
        try:
            import docx
            doc = docx.Document(full_path)
            text_chunks = []
            for p in doc.paragraphs:
                if p.text.strip():
                    text_chunks.append(p.text.strip())
            for table in doc.tables:
                for row in table.rows:
                    row_cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                    if row_cells:
                        text_chunks.append(" | ".join(row_cells))
            return "\n".join(text_chunks)
        except Exception as e:
            return f"[Error extracting DOCX text: {e}]"

    # 4. Legacy Word Documents (.doc) & RTF
    elif suffix in ['.doc', '.rtf']:
        try:
            with open(full_path, 'rb') as f:
                content = f.read()
            import re
            # Extract printable ASCII/UTF-8 byte sequences of length >= 4
            strings = re.findall(rb'[\x20-\x7E\t\n\r]{4,}', content)
            decoded = [s.decode('utf-8', errors='ignore').strip() for s in strings if len(s.decode('utf-8', errors='ignore').strip()) > 3]
            # Filter binary header tags
            clean_lines = [line for line in decoded if not line.startswith(('CompObj', 'WordDocument', 'SummaryInformation', 'DocumentSummaryInformation', '{\\rtf'))]
            if clean_lines:
                return "\n".join(clean_lines)
            return f"[Legacy Word Doc binary content extracted: {len(decoded)} tokens]"
        except Exception as e:
            return f"[Error extracting legacy Word DOC text: {e}]"

    # 5. Excel Spreadsheets (.xlsx, .xls)
    elif suffix in ['.xlsx', '.xls']:
        try:
            import openpyxl
            wb = openpyxl.load_workbook(full_path, data_only=True)
            lines = []
            for sheet in wb.sheetnames:
                ws = wb[sheet]
                lines.append(f"--- Sheet: {sheet} ---")
                for row in ws.iter_rows(values_only=True):
                    row_vals = [str(v) for v in row if v is not None]
                    if row_vals:
                        lines.append(" | ".join(row_vals))
            return "\n".join(lines)
        except Exception as e:
            return f"[Error extracting Excel data: {e}]"
            
    return f"[Unsupported file format: {suffix}]"

def save_sample_document(project_id: int, file_path: str, title: str, criteria: str, expected_sections: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
    INSERT INTO sample_documents (project_id, title, file_path, evaluation_criteria, expected_sections)
    VALUES (?, ?, ?, ?, ?)
    ''', (project_id, title, file_path, criteria, expected_sections))
    conn.commit()
    doc_id = cursor.lastrowid
    conn.close()
    return doc_id

def create_intern_submission(assignment_id: int, intern_id: int, title: str, file_path: str, file_type: str, notes: str = "", github_repo_url: str = ""):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
    INSERT INTO submissions (assignment_id, intern_id, title, file_path, file_type, notes, github_repo_url, status)
    VALUES (?, ?, ?, ?, ?, ?, ?, 'Submitted')
    ''', (assignment_id, intern_id, title, file_path, file_type, notes, (github_repo_url or '').strip()))
    sub_id = cursor.lastrowid
    
    # Update assignment status to 'Submitted' and update repo URL if provided
    if github_repo_url and github_repo_url.strip():
        cursor.execute('''
        UPDATE assignments SET status = 'Submitted', github_repo_url = ? WHERE id = ?
        ''', (github_repo_url.strip(), assignment_id))
    else:
        cursor.execute('''
        UPDATE assignments SET status = 'Submitted' WHERE id = ?
        ''', (assignment_id,))
    
    conn.commit()
    conn.close()
    return sub_id

def run_submission_evaluation(submission_id: int) -> dict:
    """
    Extracts text from intern submission & cross-checks against the project sample doc / specification standard,
    runs AI evaluation, and saves both evaluation and feedback records.
    """
    conn = get_db()
    cursor = conn.cursor()
    
    # Get submission details with assignment & project metadata
    cursor.execute('''
    SELECT s.*, a.project_id, a.mentor_id, u.full_name as intern_name, p.title as project_title,
           p.abstract, p.problem_statement, p.objectives, p.scope, p.deliverables, p.technologies, p.required_skills
    FROM submissions s
    JOIN assignments a ON s.assignment_id = a.id
    JOIN users u ON s.intern_id = u.id
    JOIN projects p ON a.project_id = p.id
    WHERE s.id = ?
    ''', (submission_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None
    submission = dict(row)
        
    project_id = submission['project_id']

    # 1. Look for uploaded sample document for this project in sample_documents
    cursor.execute('''
    SELECT * FROM sample_documents WHERE project_id = ? ORDER BY id DESC LIMIT 1
    ''', (project_id,))
    sample_doc_row = cursor.fetchone()
    sample_doc = dict(sample_doc_row) if sample_doc_row else None
    
    sample_text = ""
    sample_doc_name = ""
    criteria = "Technical accuracy, architecture completeness, security considerations, testing coverage, and deliverable quality."
    expected_sections = "Executive Summary, System Architecture, Functional Flow, Security, Testing, Deliverables"

    if sample_doc:
        sample_text = extract_text_from_file(sample_doc['file_path'])
        sample_doc_name = sample_doc.get('title') or "Mentor Reference Blueprint Document"
        criteria = sample_doc.get('evaluation_criteria') or criteria
        expected_sections = sample_doc.get('expected_sections') or expected_sections
    else:
        # 2. Check documents table for project reference / specification docs
        cursor.execute('''
        SELECT * FROM documents WHERE project_id = ? AND approval_status = 'Approved' ORDER BY id DESC LIMIT 1
        ''', (project_id,))
        repo_doc_row = cursor.fetchone()
        repo_doc = dict(repo_doc_row) if repo_doc_row else None
        if repo_doc:
            sample_text = extract_text_from_file(repo_doc['file_path'])
            sample_doc_name = repo_doc.get('title')
        else:
            # 3. Build comprehensive authoritative specification blueprint from project definitions
            sample_doc_name = f"Official Project Blueprint: {submission['project_title']}"
            proj_abstract = submission['abstract'] or 'Industry-standard enterprise project'
            proj_problem = submission['problem_statement'] or 'Standard engineering challenge'
            proj_objectives = submission['objectives'] or "1. Implement solution architecture\n2. Deliver functional modules\n3. Pass testing suite"
            proj_scope = submission['scope'] or 'Full stack implementation'
            proj_deliverables = submission['deliverables'] or 'Code repository, system architecture doc, unit tests, deployment manifest'
            proj_tech = submission['technologies'] or 'Modern fullstack architecture'

            sample_text = f"""# {submission['project_title']} - Master Project Specification Standard
## Abstract:
{proj_abstract}

## Problem Statement:
{proj_problem}

## Key Objectives:
{proj_objectives}

## Scope & Functional Requirements:
{proj_scope}

## Expected Deliverables:
{proj_deliverables}

## Target Technologies:
{proj_tech}
"""

    # Extract intern submission text from Word doc / PDF / TXT
    sub_text = extract_text_from_file(submission['file_path'])
    if not sub_text or sub_text.startswith("[Error") or sub_text.startswith("[File not found"):
        sub_text = f"Submission Title: {submission['title']}\nNotes: {submission['notes']}\nFile Type: {submission['file_type']}"

    # Append GitHub / Demo link info if provided in submission or assignment
    if submission.get('github_repo_url'):
        sub_text += f"\n\nConnected GitHub Repository: {submission['github_repo_url']}"

    # Run AI evaluation with sample document cross-checking
    eval_result = evaluate_submission_ai(
        submission_text=sub_text,
        sample_text=sample_text,
        criteria=criteria,
        expected_sections=expected_sections,
        sample_doc_name=sample_doc_name
    )
    
    # Save Evaluation
    cursor.execute('''
    INSERT OR REPLACE INTO evaluations (
        submission_id, overall_score, section_scores_json, missing_sections_json,
        errors_json, strengths_json, weaknesses_json, recommendations_json
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        submission_id,
        eval_result.get('overall_score', 80),
        json.dumps(eval_result.get('section_scores', [])),
        json.dumps(eval_result.get('missing_sections', [])),
        json.dumps(eval_result.get('errors', [])),
        json.dumps(eval_result.get('strengths', [])),
        json.dumps(eval_result.get('weaknesses', [])),
        json.dumps(eval_result.get('recommendations', []))
    ))
    eval_id = cursor.lastrowid or cursor.execute("SELECT id FROM evaluations WHERE submission_id = ?", (submission_id,)).fetchone()['id']

    # Generate and Save Feedback
    feedback_result = generate_feedback_ai(eval_result)
    cursor.execute('''
    INSERT OR REPLACE INTO feedbacks (
        evaluation_id, summary, strengths_json, weaknesses_json,
        required_corrections_json, priority_corrections_json, final_recommendation
    ) VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (
        eval_id,
        feedback_result.get('summary', ''),
        json.dumps(feedback_result.get('strengths', [])),
        json.dumps(feedback_result.get('weaknesses', [])),
        json.dumps(feedback_result.get('required_corrections', [])),
        json.dumps(feedback_result.get('priority_corrections', [])),
        feedback_result.get('final_recommendation', 'Approved with Minor Revisions')
    ))

    # Update submission status
    cursor.execute("UPDATE submissions SET status = 'Evaluated' WHERE id = ?", (submission_id,))
    cursor.execute("UPDATE assignments SET status = 'Under Review' WHERE id = ?", (submission['assignment_id'],))
    
    conn.commit()
    conn.close()
    return {"evaluation_id": eval_id, "eval_result": eval_result, "feedback_result": feedback_result}

def get_submission_evaluation(submission_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
    SELECT e.*, s.title as submission_title, s.file_path, s.file_type, s.notes, s.submitted_at,
           u.full_name as intern_name, p.title as project_title, a.id as assignment_id
    FROM evaluations e
    JOIN submissions s ON e.submission_id = s.id
    JOIN assignments a ON s.assignment_id = a.id
    JOIN users u ON s.intern_id = u.id
    JOIN projects p ON a.project_id = p.id
    WHERE e.submission_id = ?
    ''', (submission_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    
    data = dict(row)
    data['section_scores'] = json.loads(data['section_scores_json']) if data['section_scores_json'] else []
    data['missing_sections'] = json.loads(data['missing_sections_json']) if data['missing_sections_json'] else []
    data['errors'] = json.loads(data['errors_json']) if data['errors_json'] else []
    data['strengths'] = json.loads(data['strengths_json']) if data['strengths_json'] else []
    data['weaknesses'] = json.loads(data['weaknesses_json']) if data['weaknesses_json'] else []
    data['recommendations'] = json.loads(data['recommendations_json']) if data['recommendations_json'] else []
    return data

def get_feedback_for_evaluation(eval_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
    SELECT f.*, e.overall_score, s.title as submission_title, u.full_name as intern_name, p.title as project_title
    FROM feedbacks f
    JOIN evaluations e ON f.evaluation_id = e.id
    JOIN submissions s ON e.submission_id = s.id
    JOIN assignments a ON s.assignment_id = a.id
    JOIN users u ON s.intern_id = u.id
    JOIN projects p ON a.project_id = p.id
    WHERE f.evaluation_id = ?
    ''', (eval_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    
    data = dict(row)
    data['strengths'] = json.loads(data['strengths_json']) if data['strengths_json'] else []
    data['weaknesses'] = json.loads(data['weaknesses_json']) if data['weaknesses_json'] else []
    data['required_corrections'] = json.loads(data['required_corrections_json']) if data['required_corrections_json'] else []
    data['priority_corrections'] = json.loads(data['priority_corrections_json']) if data['priority_corrections_json'] else []
    return data
