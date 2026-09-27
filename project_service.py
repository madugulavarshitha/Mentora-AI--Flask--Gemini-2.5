import json
from datetime import datetime, date
from database import get_db
from gemini_service import (
    recommend_technologies_ai,
    generate_scenario_ai,
    analyze_project_health_ai,
    enrich_project_blueprint
)

def create_project(data: dict, created_by: int) -> int:
    # Ensure all professional fields (Abstract, Problem Statement, Technologies) are enriched
    data = enrich_project_blueprint(data)
    
    def _to_str(val):
        if val is None:
            return ""
        if isinstance(val, (list, dict)):
            return json.dumps(val)
        return str(val)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
    INSERT INTO projects (
        title, requirement, domain, difficulty, duration, required_skills, technologies,
        business_context, problem_statement, abstract, objectives, scope,
        functional_reqs, non_functional_reqs, expected_outcomes, deliverables, source, created_by
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        _to_str(data.get('title', 'Untitled Project')) or 'Untitled Project',
        _to_str(data.get('requirement', '')),
        _to_str(data.get('domain', 'General')) or 'General',
        _to_str(data.get('difficulty', 'Intermediate')) or 'Intermediate',
        _to_str(data.get('duration', '4 Weeks')) or '4 Weeks',
        _to_str(data.get('required_skills', '')),
        _to_str(data.get('technologies', '')),
        _to_str(data.get('business_context', '')),
        _to_str(data.get('problem_statement', '')),
        _to_str(data.get('abstract', '')),
        _to_str(data.get('objectives', '')),
        _to_str(data.get('scope', '')),
        _to_str(data.get('functional_reqs', '')),
        _to_str(data.get('non_functional_reqs', '')),
        _to_str(data.get('expected_outcomes', '')),
        _to_str(data.get('deliverables', '')),
        _to_str(data.get('source', 'ai')) or 'ai',
        int(created_by) if created_by else None
    ))
    project_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return project_id

def update_project(project_id: int, data: dict):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
    UPDATE projects SET
        title = ?, requirement = ?, domain = ?, difficulty = ?, duration = ?,
        required_skills = ?, technologies = ?, business_context = ?, problem_statement = ?, abstract = ?,
        objectives = ?, scope = ?, functional_reqs = ?, non_functional_reqs = ?,
        expected_outcomes = ?, deliverables = ?
    WHERE id = ?
    ''', (
        data.get('title'),
        data.get('requirement'),
        data.get('domain'),
        data.get('difficulty'),
        data.get('duration'),
        data.get('required_skills'),
        data.get('technologies'),
        data.get('business_context'),
        data.get('problem_statement'),
        data.get('abstract'),
        data.get('objectives'),
        data.get('scope'),
        data.get('functional_reqs'),
        data.get('non_functional_reqs'),
        data.get('expected_outcomes'),
        data.get('deliverables'),
        project_id
    ))
    conn.commit()
    conn.close()

def delete_project(project_id: int) -> bool:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM projects WHERE id = ?', (project_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted

def get_project_by_id(project_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
    SELECT p.*, u.full_name as creator_name
    FROM projects p
    LEFT JOIN users u ON p.created_by = u.id
    WHERE p.id = ?
    ''', (project_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
        
    p = dict(row)
    # Check if project needs professional enrichment
    curr_abs = p.get('abstract') or ''
    curr_tech = p.get('technologies') or ''
    curr_prob = p.get('problem_statement') or ''
    
    is_sparse = (
        not curr_abs.strip()
        or not curr_tech.strip()
        or not curr_prob.strip()
        or not p.get('objectives')
    )
    
    if is_sparse:
        enriched = enrich_project_blueprint(p)
        try:
            update_project(project_id, enriched)
        except Exception:
            pass
        return enriched
        
    return p

def get_all_projects():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
    SELECT p.*, u.full_name as creator_name,
           (SELECT COUNT(*) FROM assignments WHERE project_id = p.id) as assignment_count
    FROM projects p
    LEFT JOIN users u ON p.created_by = u.id
    ORDER BY p.id DESC
    ''')
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

# --- Tech Recommendations ---
def get_or_generate_tech_recommendations(project_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT recommendations_json FROM tech_recommendations WHERE project_id = ? ORDER BY id DESC LIMIT 1', (project_id,))
    row = cursor.fetchone()
    
    if row and row['recommendations_json']:
        conn.close()
        return json.loads(row['recommendations_json'])
        
    # Generate via AI
    project = get_project_by_id(project_id)
    if not project:
        conn.close()
        return None
        
    rec = recommend_technologies_ai(project)
    cursor.execute('INSERT INTO tech_recommendations (project_id, recommendations_json) VALUES (?, ?)', (project_id, json.dumps(rec)))
    conn.commit()
    conn.close()
    return rec

# --- Real-World Scenarios ---
def get_or_generate_scenario(project_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT scenario_json FROM scenarios WHERE project_id = ? ORDER BY id DESC LIMIT 1', (project_id,))
    row = cursor.fetchone()
    
    if row and row['scenario_json']:
        conn.close()
        return json.loads(row['scenario_json'])
        
    project = get_project_by_id(project_id)
    if not project:
        conn.close()
        return None
        
    scenario = generate_scenario_ai(project)
    cursor.execute('INSERT INTO scenarios (project_id, scenario_json) VALUES (?, ?)', (project_id, json.dumps(scenario)))
    conn.commit()
    conn.close()
    return scenario

# --- Assignments ---
def create_assignment(project_id: int, mentor_id: int, intern_id: int, start_date: str, deadline: str, deliverables: str, github_repo_url: str = '', demo_url: str = '', doc_url: str = '') -> int:
    conn = get_db()
    cursor = conn.cursor()
    today_str = date.today().isoformat()
    cursor.execute('''
    INSERT INTO assignments (project_id, mentor_id, intern_id, assignment_date, start_date, deadline, deliverables, github_repo_url, demo_url, doc_url, status)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Not Started')
    ''', (project_id, mentor_id, intern_id, today_str, start_date, deadline, deliverables, (github_repo_url or '').strip(), (demo_url or '').strip(), (doc_url or '').strip()))
    assign_id = cursor.lastrowid
    
    # Also update intern availability/workload
    cursor.execute('''
    UPDATE interns SET workload = 'Medium', availability = 'Assigned' WHERE user_id = ?
    ''', (intern_id,))
    
    # Auto create initial setup task
    cursor.execute('''
    INSERT INTO tasks (assignment_id, title, description, deadline, status)
    VALUES (?, 'Project Setup & Technical Requirements Review', 'Review project objectives, setup local development environment, and configure repository.', ?, 'Pending')
    ''', (assign_id, start_date))
    
    conn.commit()
    conn.close()
    return assign_id

def update_assignment_github(assignment_id: int, github_repo_url: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
    UPDATE assignments SET github_repo_url = ? WHERE id = ?
    ''', ((github_repo_url or '').strip(), assignment_id))
    conn.commit()
    conn.close()

def update_assignment_links(assignment_id: int, github_repo_url: str = None, demo_url: str = None, doc_url: str = None):
    conn = get_db()
    cursor = conn.cursor()
    updates = []
    params = []
    if github_repo_url is not None:
        updates.append("github_repo_url = ?")
        params.append(github_repo_url.strip())
    if demo_url is not None:
        updates.append("demo_url = ?")
        params.append(demo_url.strip())
    if doc_url is not None:
        updates.append("doc_url = ?")
        params.append(doc_url.strip())
    
    if updates:
        params.append(assignment_id)
        cursor.execute(f'''
        UPDATE assignments SET {", ".join(updates)} WHERE id = ?
        ''', tuple(params))
        
        # Check if links became incomplete or complete
        cursor.execute('SELECT github_repo_url, demo_url, doc_url, status FROM assignments WHERE id = ?', (assignment_id,))
        row = cursor.fetchone()
        if row:
            has_all_links = bool(row['github_repo_url'] and row['github_repo_url'].strip() and 
                                 row['demo_url'] and row['demo_url'].strip() and 
                                 row['doc_url'] and row['doc_url'].strip())
            
            cursor.execute('SELECT COUNT(*) as total, SUM(CASE WHEN status = "Completed" THEN 1 ELSE 0 END) as done FROM tasks WHERE assignment_id = ?', (assignment_id,))
            t_counts = cursor.fetchone()
            all_tasks_done = bool(t_counts and t_counts['total'] > 0 and t_counts['done'] == t_counts['total'])
            
            # If status was Completed but even one link is now missing / deleted:
            if not has_all_links and row['status'] == 'Completed':
                cursor.execute('UPDATE assignments SET status = "In Progress" WHERE id = ?', (assignment_id,))
            elif has_all_links and all_tasks_done and row['status'] not in ['Completed', 'Submitted']:
                cursor.execute('UPDATE assignments SET status = "Completed" WHERE id = ?', (assignment_id,))
                
        conn.commit()
    conn.close()

def get_assignment_by_id(assignment_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
    SELECT a.*, p.title as project_title, p.domain, p.difficulty, p.duration, p.required_skills,
           p.problem_statement, p.deliverables as expected_deliverables,
           u_m.full_name as mentor_name, u_i.full_name as intern_name, u_i.email as intern_email,
           i.github_url as intern_github_url
    FROM assignments a
    JOIN projects p ON a.project_id = p.id
    JOIN users u_m ON a.mentor_id = u_m.id
    JOIN users u_i ON a.intern_id = u_i.id
    LEFT JOIN interns i ON u_i.id = i.user_id
    WHERE a.id = ?
    ''', (assignment_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_assignments_for_mentor(mentor_id: int = None):
    conn = get_db()
    cursor = conn.cursor()
    query = '''
    SELECT a.*, p.title as project_title, p.domain, p.difficulty, p.duration, p.problem_statement, p.abstract,
           u_m.full_name as mentor_name, u_i.full_name as intern_name,
           i.github_url as intern_github_url,
           (SELECT COUNT(*) FROM tasks WHERE assignment_id = a.id) as total_tasks,
           (SELECT COUNT(*) FROM tasks WHERE assignment_id = a.id AND status = 'Completed') as completed_tasks,
           (SELECT COUNT(*) FROM tasks WHERE assignment_id = a.id AND status = 'Overdue') as overdue_tasks,
           (SELECT COUNT(*) FROM submissions WHERE assignment_id = a.id) as submission_count,
           (SELECT id FROM submissions WHERE assignment_id = a.id ORDER BY id DESC LIMIT 1) as latest_submission_id,
           (SELECT status FROM submissions WHERE assignment_id = a.id ORDER BY id DESC LIMIT 1) as submission_status,
           (SELECT file_path FROM submissions WHERE assignment_id = a.id ORDER BY id DESC LIMIT 1) as submission_file_path,
           (SELECT demo_url FROM submissions WHERE assignment_id = a.id ORDER BY id DESC LIMIT 1) as submission_demo_url
    FROM assignments a
    JOIN projects p ON a.project_id = p.id
    JOIN users u_m ON a.mentor_id = u_m.id
    JOIN users u_i ON a.intern_id = u_i.id
    LEFT JOIN interns i ON u_i.id = i.user_id
    '''
    params = []
    if mentor_id:
        query += ' WHERE a.mentor_id = ?'
        params.append(mentor_id)
    query += ' ORDER BY a.id ASC'
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    
    results = []
    for r in rows:
        d = dict(r)
        total = d.get('total_tasks', 0)
        completed = d.get('completed_tasks', 0)
        d['progress_pct'] = int((completed / total * 100)) if total > 0 else 0
        
        # Determine Health Badge dynamically
        overdue = d.get('overdue_tasks', 0)
        if overdue >= 2 or d['status'] == 'Critical':
            d['health'] = 'CRITICAL'
            d['health_badge_class'] = 'health-red'
        elif overdue == 1 or d['status'] == 'Delayed' or (d['progress_pct'] < 50 and total > 2):
            d['health'] = 'NEEDS ATTENTION'
            d['health_badge_class'] = 'health-pink'
        else:
            d['health'] = 'HEALTHY'
            d['health_badge_class'] = 'health-mint'

        # Status badge class
        st = d.get('status', 'Not Started')
        if st == 'Not Started':
            d['status_badge_class'] = 'status-yellow'
        elif st == 'Submitted':
            d['status_badge_class'] = 'status-blue'
        elif st == 'Completed':
            d['status_badge_class'] = 'status-mint'
        elif st in ['Delayed', 'Critical']:
            d['status_badge_class'] = 'status-red'
        else:
            d['status_badge_class'] = 'status-purple'

        # Avatar mapping
        name_lower = (d.get('intern_name') or '').lower()
        if 'bhumika' in name_lower:
            d['avatar_url'] = '/static/images/intern-avatar-alex.png'
        elif 'deepika' in name_lower:
            d['avatar_url'] = '/static/images/intern-avatar-priya.png'
        elif 'lakshmi' in name_lower:
            d['avatar_url'] = '/static/images/intern-avatar-varshitha.png'
        else:
            d['avatar_url'] = '/static/images/intern-avatar-alex.png'

        # Project Icon & styling
        title = (d.get('project_title') or '').lower()
        if any(k in title for k in ['ai', 'nlp', 'bot', 'chat', 'agent']):
            d['project_icon'] = '🤖'
            d['icon_bg_class'] = 'icon-box-purple'
        elif any(k in title for k in ['medical', 'health', 'prescription']):
            d['project_icon'] = '💊'
            d['icon_bg_class'] = 'icon-box-pink'
        elif any(k in title for k in ['vision', 'traffic', 'image', 'city']):
            d['project_icon'] = '📊'
            d['icon_bg_class'] = 'icon-box-blue'
        elif any(k in title for k in ['data', 'analytics', 'science']):
            d['project_icon'] = '📈'
            d['icon_bg_class'] = 'icon-box-mint'
        else:
            d['project_icon'] = '📁'
            d['icon_bg_class'] = 'icon-box-blue'
            
        # Days left calculation
        deadline_str = d.get('deadline')
        if deadline_str:
            try:
                d_date = datetime.strptime(str(deadline_str), '%Y-%m-%d').date()
                diff = (d_date - date.today()).days
                if diff < 0:
                    d['days_left_text'] = f"{abs(diff)} days overdue"
                elif diff == 0:
                    d['days_left_text'] = "Due today"
                else:
                    d['days_left_text'] = f"{diff} days left"
            except Exception:
                d['days_left_text'] = "Deadline set"
        else:
            d['days_left_text'] = "Ongoing"

        results.append(d)
        
    return results

def get_assignments_for_intern(intern_user_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
    SELECT a.*, p.title as project_title, p.domain, p.difficulty, p.duration,
           p.problem_statement, p.abstract, p.deliverables as expected_deliverables,
           u_m.full_name as mentor_name,
           i.github_url as intern_github_url,
           (SELECT COUNT(*) FROM tasks WHERE assignment_id = a.id) as total_tasks,
           (SELECT COUNT(*) FROM tasks WHERE assignment_id = a.id AND status = 'Completed') as completed_tasks,
           (SELECT COUNT(*) FROM tasks WHERE assignment_id = a.id AND status = 'Overdue') as overdue_tasks,
           (SELECT id FROM submissions WHERE assignment_id = a.id ORDER BY id DESC LIMIT 1) as latest_submission_id,
           (SELECT status FROM submissions WHERE assignment_id = a.id ORDER BY id DESC LIMIT 1) as submission_status,
           (SELECT file_path FROM submissions WHERE assignment_id = a.id ORDER BY id DESC LIMIT 1) as submission_file_path,
           (SELECT demo_url FROM submissions WHERE assignment_id = a.id ORDER BY id DESC LIMIT 1) as submission_demo_url
    FROM assignments a
    JOIN projects p ON a.project_id = p.id
    JOIN users u_m ON a.mentor_id = u_m.id
    LEFT JOIN interns i ON a.intern_id = i.user_id
    WHERE a.intern_id = ?
    ORDER BY a.deadline ASC
    ''', (intern_user_id,))
    rows = cursor.fetchall()
    conn.close()
    
    results = []
    for r in rows:
        d = dict(r)
        total = d.get('total_tasks', 0)
        completed = d.get('completed_tasks', 0)
        
        has_github = bool(d.get('github_repo_url') and d.get('github_repo_url').strip())
        has_demo = bool((d.get('demo_url') and d.get('demo_url').strip()) or (d.get('submission_demo_url') and d.get('submission_demo_url').strip()))
        has_doc = bool(d.get('doc_url') and d.get('doc_url').strip())
        has_all_links = has_github and has_demo and has_doc
        
        d['has_all_links'] = has_all_links
        d['has_github'] = has_github
        d['has_demo'] = has_demo
        d['has_doc'] = has_doc
        
        if total > 0:
            raw_pct = int((completed / total * 100))
            if raw_pct == 100 and not has_all_links:
                d['progress_pct'] = min(raw_pct, 90)
                d['links_required_for_100'] = True
            else:
                d['progress_pct'] = raw_pct
                d['links_required_for_100'] = False
        else:
            d['progress_pct'] = 0
            d['links_required_for_100'] = False
        
        overdue = d.get('overdue_tasks', 0)
        if overdue >= 2 or d['status'] == 'Critical':
            d['health'] = 'CRITICAL'
            d['health_badge_class'] = 'badge-danger'
        elif overdue == 1 or d['status'] == 'Delayed':
            d['health'] = 'NEEDS ATTENTION'
            d['health_badge_class'] = 'badge-warning'
        else:
            d['health'] = 'HEALTHY'
            d['health_badge_class'] = 'badge-success'
            
        results.append(d)
    return results

# --- Tasks ---
def get_tasks_for_assignment(assignment_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
    SELECT * FROM tasks WHERE assignment_id = ? ORDER BY deadline ASC, id ASC
    ''', (assignment_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def create_task(assignment_id: int, title: str, description: str, deadline: str, status: str = 'Pending') -> int:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
    INSERT INTO tasks (assignment_id, title, description, deadline, status)
    VALUES (?, ?, ?, ?, ?)
    ''', (assignment_id, title, description, deadline, status))
    task_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return task_id

def update_task_status(task_id: int, new_status: str):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT assignment_id, status FROM tasks WHERE id = ?', (task_id,))
    task = cursor.fetchone()
    if not task:
        conn.close()
        return False, "Task not found."
        
    assign_id = task['assignment_id']
    
    # Check if marking Completed would lead to 100% progress
    if new_status == 'Completed':
        cursor.execute('SELECT github_repo_url, demo_url, doc_url FROM assignments WHERE id = ?', (assign_id,))
        assign_row = cursor.fetchone()
        
        cursor.execute('SELECT COUNT(*) as total, SUM(CASE WHEN status = "Completed" AND id != ? THEN 1 ELSE 0 END) as other_done FROM tasks WHERE assignment_id = ?', (task_id, assign_id))
        t_counts = cursor.fetchone()
        total_tasks = t_counts['total'] if t_counts else 0
        other_done = (t_counts['other_done'] or 0) if t_counts else 0
        
        # If completing this task makes all tasks completed (100%)
        if total_tasks > 0 and (other_done + 1) == total_tasks:
            has_github = bool(assign_row and assign_row['github_repo_url'] and assign_row['github_repo_url'].strip())
            has_demo = bool(assign_row and assign_row['demo_url'] and assign_row['demo_url'].strip())
            has_doc = bool(assign_row and assign_row['doc_url'] and assign_row['doc_url'].strip())
            
            if not (has_github and has_demo and has_doc):
                missing = []
                if not has_github: missing.append("GitHub Repository (🐙)")
                if not has_demo: missing.append("Live Demo Application (🌐)")
                if not has_doc: missing.append("Documentation / Doc Link (📄)")
                conn.close()
                return False, f"All 3 project links are mandatory to reach 100% progress and mark all tasks completed. Missing: {', '.join(missing)}."

    cursor.execute('''
    UPDATE tasks SET status = ? WHERE id = ?
    ''', (new_status, task_id))
    
    # Recalculate assignment progress & auto-update assignment status
    cursor.execute('SELECT COUNT(*) as total, SUM(CASE WHEN status = "Completed" THEN 1 ELSE 0 END) as done FROM tasks WHERE assignment_id = ?', (assign_id,))
    counts = cursor.fetchone()
    if counts and counts['total'] > 0:
        cursor.execute('SELECT github_repo_url, demo_url, doc_url, status FROM assignments WHERE id = ?', (assign_id,))
        assign_row = cursor.fetchone()
        has_all_links = bool(assign_row and assign_row['github_repo_url'] and assign_row['github_repo_url'].strip() and 
                             assign_row['demo_url'] and assign_row['demo_url'].strip() and 
                             assign_row['doc_url'] and assign_row['doc_url'].strip())
        
        if counts['done'] == counts['total'] and has_all_links:
            cursor.execute('UPDATE assignments SET status = "Completed" WHERE id = ? AND status != "Submitted"', (assign_id,))
        elif counts['done'] == counts['total'] and not has_all_links:
            # If all tasks are marked completed but links are missing / deleted, revert assignment from Completed
            if assign_row and assign_row['status'] == 'Completed':
                cursor.execute('UPDATE assignments SET status = "In Progress" WHERE id = ?', (assign_id,))
        elif counts['done'] > 0:
            cursor.execute('UPDATE assignments SET status = "In Progress" WHERE id = ? AND status = "Not Started"', (assign_id,))
            
    conn.commit()
    conn.close()
    return True, "Task status updated successfully."

# --- Health Calculation Details ---
def get_assignment_health_detail(assignment_id: int):
    assign = get_assignment_by_id(assignment_id)
    if not assign:
        return None
        
    tasks = get_tasks_for_assignment(assignment_id)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM submissions WHERE assignment_id = ? ORDER BY id DESC LIMIT 1', (assignment_id,))
    submission_row = cursor.fetchone()
    conn.close()
    
    submission_info = dict(submission_row) if submission_row else None
    
    # Run AI health analysis
    ai_health = analyze_project_health_ai(assign, tasks, submission_info)
    
    total = len(tasks)
    completed = sum(1 for t in tasks if t['status'] == 'Completed')
    overdue = sum(1 for t in tasks if t['status'] == 'Overdue')
    pending = total - completed
    progress_pct = int((completed / total * 100)) if total > 0 else 0
    
    return {
        "assignment": assign,
        "tasks": tasks,
        "total_tasks": total,
        "completed_tasks": completed,
        "overdue_tasks": overdue,
        "pending_tasks": pending,
        "progress_pct": progress_pct,
        "submission": submission_info,
        "ai_health": ai_health
    }

# ==========================================================
# DATASET / FILE IMPORT ENGINE (CSV, JSON, EXCEL, TXT)
# ==========================================================
import csv
import io

def parse_project_dataset(file_content: str, filename: str) -> list:
    """Parse projects from CSV, JSON, or text content."""
    projects = []
    fname_lower = filename.lower()
    
    # 1. JSON Import
    if fname_lower.endswith('.json'):
        try:
            data = json.loads(file_content)
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and (item.get('title') or item.get('problem_statement') or item.get('abstract')):
                        projects.append(_normalize_project_dict(item))
            elif isinstance(data, dict):
                # Could be {"projects": [...]} or a single project
                if 'projects' in data and isinstance(data['projects'], list):
                    for item in data['projects']:
                        projects.append(_normalize_project_dict(item))
                elif data.get('title') or data.get('problem_statement') or data.get('abstract'):
                    projects.append(_normalize_project_dict(data))
            return projects
        except Exception as e:
            print(f"[Dataset Import] JSON parse error: {e}")

    # 2. CSV Import
    if fname_lower.endswith('.csv') or ',' in file_content[:500]:
        try:
            reader = csv.DictReader(io.StringIO(file_content))
            for row in reader:
                norm_row = {k.strip().lower().replace(' ', '_'): v.strip() for k, v in row.items() if k}
                if any(norm_row.get(k) for k in ['title', 'project_title', 'name', 'problem_statement', 'abstract']):
                    projects.append(_normalize_project_dict(norm_row))
            if projects:
                return projects
        except Exception as e:
            print(f"[Dataset Import] CSV parse error: {e}")

    # 3. Text / Structured AI Extraction Fallback
    try:
        from gemini_service import call_gemini, clean_json_text
        prompt = f"""
Extract project details from this uploaded document/dataset:
---
{file_content[:4000]}
---
Return a JSON array of projects, each with keys:
"title", "problem_statement", "abstract", "technologies", "domain", "difficulty", "duration", "required_skills", "objectives", "scope", "functional_reqs", "expected_outcomes".
Output pure JSON only.
"""
        raw = call_gemini(prompt, "You are a Dataset Ingestion Specialist.")
        if raw:
            extracted = json.loads(clean_json_text(raw))
            if isinstance(extracted, list):
                for item in extracted:
                    projects.append(_normalize_project_dict(item))
            elif isinstance(extracted, dict) and extracted.get('title'):
                projects.append(_normalize_project_dict(extracted))
    except Exception as e:
        print(f"[Dataset Import] AI extractor error: {e}")

    return projects

def _normalize_project_dict(d: dict) -> dict:
    """Normalize field names from diverse dataset columns."""
    title = d.get('title') or d.get('project_title') or d.get('name') or 'Imported Project'
    problem = d.get('problem_statement') or d.get('problem') or d.get('problem_description') or ''
    abstract = d.get('abstract') or d.get('summary') or d.get('description') or ''
    tech = d.get('technologies') or d.get('tools') or d.get('tech_stack') or d.get('technology_stack') or ''
    skills = d.get('required_skills') or d.get('skills') or d.get('intern_skills') or tech
    domain = d.get('domain') or d.get('category') or d.get('field') or 'Artificial Intelligence'
    difficulty = d.get('difficulty') or d.get('level') or 'Intermediate'
    duration = d.get('duration') or d.get('timeline') or '6 Weeks'
    objectives = d.get('objectives') or d.get('goals') or ''
    scope = d.get('scope') or ''
    functional_reqs = d.get('functional_reqs') or d.get('requirements') or ''
    non_functional_reqs = d.get('non_functional_reqs') or ''
    expected_outcomes = d.get('expected_outcomes') or d.get('outcomes') or ''
    deliverables = d.get('deliverables') or 'Source Code, Architecture Blueprint, Test Suite, Docker Manifest'

    return {
        'title': title,
        'requirement': d.get('requirement') or problem or abstract,
        'domain': domain,
        'difficulty': difficulty,
        'duration': duration,
        'required_skills': skills,
        'business_context': d.get('business_context') or '',
        'problem_statement': problem,
        'abstract': abstract,
        'technologies': tech,
        'objectives': objectives,
        'scope': scope,
        'functional_reqs': functional_reqs,
        'non_functional_reqs': non_functional_reqs,
        'expected_outcomes': expected_outcomes,
        'deliverables': deliverables,
        'source': d.get('source') or 'manual'
    }

def import_projects_dataset(file_storage, user_id: int) -> tuple[int, list]:
    """Imports dataset file and saves projects to database. Returns (count, list of imported dicts)."""
    filename = getattr(file_storage, 'filename', '') or 'dataset.csv'
    raw_bytes = file_storage.read()
    try:
        content = raw_bytes.decode('utf-8')
    except UnicodeDecodeError:
        content = raw_bytes.decode('latin-1', errors='ignore')

    parsed_projects = parse_project_dataset(content, filename)
    saved_count = 0
    for p in parsed_projects:
        try:
            create_project(p, user_id)
            saved_count += 1
        except Exception as e:
            print(f"[Import Save Error] {e}")

    return saved_count, parsed_projects

