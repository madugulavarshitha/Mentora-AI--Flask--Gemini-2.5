from database import get_db
from gemini_service import match_interns_ai
from project_service import get_project_by_id
from intern_onboard_service import calculate_tenure

def get_all_interns():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
    SELECT i.*, u.username, u.email, u.full_name, u.created_at,
           COALESCE(i.joining_date, DATE(u.created_at), DATE('now')) as joining_date,
           (SELECT COUNT(*) FROM assignments WHERE intern_id = u.id AND status NOT IN ('Completed')) as active_projects_count
    FROM interns i
    JOIN users u ON i.user_id = u.id
    ORDER BY u.full_name ASC
    ''')
    rows = cursor.fetchall()
    conn.close()
    interns_list = [dict(r) for r in rows]
    for r in interns_list:
        formatted_dt, tenure_str, raw_dt = calculate_tenure(r.get('joining_date') or r.get('created_at'))
        r['joining_date_formatted'] = formatted_dt
        r['tenure_display'] = tenure_str
        r['joining_date'] = raw_dt
    return interns_list

def get_intern_by_user_id(user_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
    SELECT i.*, u.username, u.email, u.full_name
    FROM interns i
    JOIN users u ON i.user_id = u.id
    WHERE i.user_id = ?
    ''', (user_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def update_intern_profile(user_id: int, skills: str, technologies: str, experience: str, workload: str, availability: str, github_url: str = None):
    conn = get_db()
    cursor = conn.cursor()
    if github_url is not None:
        cursor.execute('''
        UPDATE interns SET
            skills = ?, technologies = ?, experience = ?, workload = ?, availability = ?, github_url = ?
        WHERE user_id = ?
        ''', (skills, technologies, experience, workload, availability, github_url, user_id))
    else:
        cursor.execute('''
        UPDATE interns SET
            skills = ?, technologies = ?, experience = ?, workload = ?, availability = ?
        WHERE user_id = ?
        ''', (skills, technologies, experience, workload, availability, user_id))
    conn.commit()
    conn.close()

def update_intern_github(user_id: int, github_url: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
    UPDATE interns SET github_url = ? WHERE user_id = ?
    ''', (github_url.strip(), user_id))
    conn.commit()
    conn.close()

def match_interns_for_project(project_id: int):
    """
    Executes AI matching between project requirements and all registered interns.
    """
    project = get_project_by_id(project_id)
    if not project:
        return []
        
    interns = get_all_interns()
    if not interns:
        return []
        
    matched_results = match_interns_ai(project, interns)
    return matched_results
