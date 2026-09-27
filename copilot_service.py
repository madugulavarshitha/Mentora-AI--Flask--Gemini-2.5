from database import get_db
from gemini_service import copilot_response_ai

def get_system_context_for_copilot() -> dict:
    """Gathers real-time snapshot of the database for the Mentor Copilot."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Projects summary
    cursor.execute('SELECT id, title, domain, difficulty, duration, required_skills FROM projects')
    projects = [dict(r) for r in cursor.fetchall()]
    
    # Assignments summary
    cursor.execute('''
    SELECT a.id, a.project_id, a.deadline, a.status,
           p.title as project_title,
           u_m.full_name as mentor_name,
           u_i.full_name as intern_name
    FROM assignments a
    JOIN projects p ON a.project_id = p.id
    JOIN users u_m ON a.mentor_id = u_m.id
    JOIN users u_i ON a.intern_id = u_i.id
    ''')
    assignments = [dict(r) for r in cursor.fetchall()]
    
    # Tasks summary
    cursor.execute('''
    SELECT t.id, t.title, t.deadline, t.status, a.id as assignment_id, p.title as project_title
    FROM tasks t
    JOIN assignments a ON t.assignment_id = a.id
    JOIN projects p ON a.project_id = p.id
    ''')
    tasks = [dict(r) for r in cursor.fetchall()]
    
    # Interns summary
    cursor.execute('''
    SELECT i.id, i.name, i.skills, i.workload, i.availability, u.email
    FROM interns i
    JOIN users u ON i.user_id = u.id
    ''')
    interns = [dict(r) for r in cursor.fetchall()]
    
    # Submissions summary
    cursor.execute('''
    SELECT s.id, s.title, s.submitted_at, s.status, u.full_name as intern_name, p.title as project_title
    FROM submissions s
    JOIN users u ON s.intern_id = u.id
    JOIN assignments a ON s.assignment_id = a.id
    JOIN projects p ON a.project_id = p.id
    ''')
    submissions = [dict(r) for r in cursor.fetchall()]
    
    conn.close()
    
    return {
        "projects_count": len(projects),
        "projects": projects,
        "assignments_count": len(assignments),
        "assignments": assignments,
        "tasks": tasks,
        "interns": interns,
        "submissions": submissions
    }

def ask_mentor_copilot(question: str) -> str:
    # Check if question is an intern onboarding / credential provisioning request
    q_lower = question.lower()
    if any(k in q_lower for k in ["add intern", "onboard intern", "create intern", "register intern", "provision intern", "create credentials"]):
        from intern_onboard_service import ai_parse_and_provision_interns
        ok, interns, err = ai_parse_and_provision_interns(question)
        if ok and interns:
            res = f"### 🤖 Intern Onboarding Agent Action Completed!\n\n"
            res += f"I have successfully provisioned **{len(interns)}** intern account(s) in the database and generated their access credentials:\n\n"
            for i, c in enumerate(interns, 1):
                res += f"#### 👤 {i}. {c['full_name']}\n"
                res += f"- **Portal Sign-In:** [`/intern/signin`](http://127.0.0.1:5000/intern/signin)\n"
                res += f"- **Username / Email:** `{c['email']}`\n"
                res += f"- **Temporary Password:** `{c['password']}`\n"
                res += f"- **Domain:** {c.get('department', 'Engineering')}\n"
                res += f"- **Skills:** {c.get('skills', 'AI & Web')}\n\n"
            res += f"> 💡 *You can copy these credentials and share them with the interns immediately. They can sign in at [`/intern/signin`](http://127.0.0.1:5000/intern/signin).*"
            return res

    context = get_system_context_for_copilot()
    return copilot_response_ai(question, context)
