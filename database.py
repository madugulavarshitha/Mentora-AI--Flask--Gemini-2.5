import sqlite3
import json
from datetime import datetime, date, timedelta
from werkzeug.security import generate_password_hash
from config import Config

def get_db():
    conn = sqlite3.connect(Config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    # 1. Users table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('admin', 'mentor', 'intern')),
        full_name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    ''')
    
    # 2. Mentors profile table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS mentors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER UNIQUE NOT NULL,
        department TEXT NOT NULL,
        expertise TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    ''')
    
    # 3. Interns profile table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS interns (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER UNIQUE NOT NULL,
        name TEXT NOT NULL,
        skills TEXT NOT NULL,
        technologies TEXT NOT NULL,
        experience TEXT NOT NULL,
        workload TEXT NOT NULL DEFAULT 'Low',
        availability TEXT NOT NULL DEFAULT 'Available',
        joining_date TEXT DEFAULT (DATE('now')),
        github_url TEXT DEFAULT '',
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    ''')
    try:
        cursor.execute("ALTER TABLE interns ADD COLUMN joining_date TEXT DEFAULT '2026-09-21';")
        conn.commit()
    except Exception:
        pass
    
    # 4. Projects table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        requirement TEXT NOT NULL,
        domain TEXT NOT NULL,
        difficulty TEXT NOT NULL,
        duration TEXT NOT NULL,
        required_skills TEXT NOT NULL,
        technologies TEXT,
        business_context TEXT,
        problem_statement TEXT,
        abstract TEXT,
        objectives TEXT,
        scope TEXT,
        functional_reqs TEXT,
        non_functional_reqs TEXT,
        expected_outcomes TEXT,
        deliverables TEXT,
        source TEXT DEFAULT 'ai',
        created_by INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
    );
    ''')
    try:
        cursor.execute("ALTER TABLE projects ADD COLUMN source TEXT DEFAULT 'ai';")
        conn.commit()
    except Exception:
        pass
    
    # 5. Technology recommendations table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS tech_recommendations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        recommendations_json TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
    );
    ''')
    
    # 6. Real-world scenarios table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS scenarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        scenario_json TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
    );
    ''')
    
    # 7. Assignments table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS assignments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        mentor_id INTEGER NOT NULL,
        intern_id INTEGER NOT NULL,
        assignment_date DATE NOT NULL,
        start_date DATE NOT NULL,
        deadline DATE NOT NULL,
        deliverables TEXT,
        github_repo_url TEXT DEFAULT '',
        status TEXT NOT NULL DEFAULT 'In Progress' CHECK(status IN ('Not Started', 'In Progress', 'On Track', 'Delayed', 'Submitted', 'Under Review', 'Completed', 'Critical')),
        progress_pct INTEGER DEFAULT 0,
        health_status TEXT DEFAULT 'HEALTHY',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
        FOREIGN KEY (mentor_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (intern_id) REFERENCES users(id) ON DELETE CASCADE
    );
    ''')
    
    # 8. Tasks table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        assignment_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        description TEXT,
        deadline DATE,
        status TEXT NOT NULL DEFAULT 'Pending' CHECK(status IN ('Pending', 'In Progress', 'Completed', 'Overdue')),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (assignment_id) REFERENCES assignments(id) ON DELETE CASCADE
    );
    ''')
    
    # 9. Sample Documents table (mentor reference files)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS sample_documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        file_path TEXT NOT NULL,
        evaluation_criteria TEXT NOT NULL,
        expected_sections TEXT NOT NULL,
        uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
    );
    ''')
    
    # 10. Submissions table (intern uploaded files)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS submissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        assignment_id INTEGER NOT NULL,
        intern_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        file_path TEXT NOT NULL,
        file_type TEXT NOT NULL,
        notes TEXT,
        github_repo_url TEXT DEFAULT '',
        submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        status TEXT NOT NULL DEFAULT 'Submitted' CHECK(status IN ('Submitted', 'Pending', 'Under Review', 'Evaluated', 'Needs Revision')),
        FOREIGN KEY (assignment_id) REFERENCES assignments(id) ON DELETE CASCADE,
        FOREIGN KEY (intern_id) REFERENCES users(id) ON DELETE CASCADE
    );
    ''')
    
    # 11. Evaluations table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS evaluations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        submission_id INTEGER UNIQUE NOT NULL,
        overall_score INTEGER NOT NULL,
        section_scores_json TEXT NOT NULL,
        missing_sections_json TEXT NOT NULL,
        errors_json TEXT NOT NULL,
        strengths_json TEXT NOT NULL,
        weaknesses_json TEXT NOT NULL,
        feedback_notes TEXT,
        evaluated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (submission_id) REFERENCES submissions(id) ON DELETE CASCADE
    );
    ''')
    
    # 12. Feedback (Mentor directly on project/assignment)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        assignment_id INTEGER NOT NULL,
        mentor_id INTEGER NOT NULL,
        intern_id INTEGER NOT NULL,
        feedback_text TEXT NOT NULL,
        category TEXT NOT NULL DEFAULT 'General' CHECK(category IN ('General', 'Code Quality', 'Design', 'Architecture', 'Meeting Notes')),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (assignment_id) REFERENCES assignments(id) ON DELETE CASCADE,
        FOREIGN KEY (mentor_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (intern_id) REFERENCES users(id) ON DELETE CASCADE
    );
    ''')
    
    # 13. Learning Resources (Self-Learning Hub: PDF, Doc, Text, Image, Video, Audio)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS learning_resources (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        intern_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        category TEXT NOT NULL DEFAULT 'General Upskilling',
        media_type TEXT NOT NULL CHECK(media_type IN ('pdf', 'doc', 'text', 'image', 'video', 'audio')),
        file_path TEXT,
        file_name TEXT,
        file_size INTEGER DEFAULT 0,
        content_text TEXT,
        external_url TEXT,
        tags TEXT DEFAULT '',
        ai_summary TEXT,
        ai_flashcards_json TEXT,
        ai_quiz_json TEXT,
        mastery_score INTEGER DEFAULT 0,
        is_favorite BOOLEAN DEFAULT 0,
        share_with_mentor BOOLEAN DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (intern_id) REFERENCES users(id) ON DELETE CASCADE
    );
    ''')

    # 14. Learning Goals & Skills Mastery Tracker
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS learning_goals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        intern_id INTEGER NOT NULL,
        skill_name TEXT NOT NULL,
        target_level TEXT NOT NULL DEFAULT 'Practitioner',
        progress_percent INTEGER DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'In Progress',
        target_date DATE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (intern_id) REFERENCES users(id) ON DELETE CASCADE
    );
    ''')

    # 15. Tab Sessions Table (For isolated multi-tab authentication)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS tab_sessions (
        sid TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        username TEXT NOT NULL,
        role TEXT NOT NULL,
        full_name TEXT NOT NULL,
        email TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    ''')

    # Schema Migrations
    try:
        cursor.execute("ALTER TABLE projects ADD COLUMN technologies TEXT")
    except Exception:
        pass

    try:
        cursor.execute("ALTER TABLE interns ADD COLUMN github_url TEXT DEFAULT ''")
    except Exception:
        pass

    try:
        cursor.execute("ALTER TABLE assignments ADD COLUMN github_repo_url TEXT DEFAULT ''")
    except Exception:
        pass

    try:
        cursor.execute("ALTER TABLE assignments ADD COLUMN demo_url TEXT DEFAULT ''")
    except Exception:
        pass

    try:
        cursor.execute("ALTER TABLE assignments ADD COLUMN doc_url TEXT DEFAULT ''")
    except Exception:
        pass

    try:
        cursor.execute("ALTER TABLE submissions ADD COLUMN github_repo_url TEXT DEFAULT ''")
    except Exception:
        pass

    try:
        cursor.execute("ALTER TABLE submissions ADD COLUMN demo_url TEXT DEFAULT ''")
    except Exception:
        pass

    try:
        cursor.execute("ALTER TABLE submissions ADD COLUMN doc_url TEXT DEFAULT ''")
    except Exception:
        pass

    conn.commit()
    conn.close()

def save_tab_session(sid: str, user_dict: dict):
    """Persists a tab-specific session in the database."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
    INSERT INTO tab_sessions (sid, user_id, username, role, full_name, email, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    ON CONFLICT(sid) DO UPDATE SET
        user_id = excluded.user_id,
        username = excluded.username,
        role = excluded.role,
        full_name = excluded.full_name,
        email = excluded.email,
        updated_at = CURRENT_TIMESTAMP
    ''', (
        sid,
        user_dict['user_id'],
        user_dict['username'],
        user_dict['role'],
        user_dict['full_name'],
        user_dict['email']
    ))
    conn.commit()
    conn.close()

def get_tab_session(sid: str) -> dict:
    """Retrieves session data for a given tab session ID."""
    if not sid:
        return None
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
    SELECT ts.*, u.password_hash 
    FROM tab_sessions ts
    JOIN users u ON ts.user_id = u.id
    WHERE ts.sid = ?
    ''', (sid,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return {
        'user_id': row['user_id'],
        'username': row['username'],
        'role': row['role'],
        'full_name': row['full_name'],
        'email': row['email']
    }

def delete_tab_session(sid: str):
    """Removes a tab session on logout."""
    if not sid:
        return
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM tab_sessions WHERE sid = ?', (sid,))
    conn.commit()
    conn.close()

def clear_all_data():
    """Clears all stored records from all tables to provide a completely fresh, clean database."""
    conn = get_db()
    cursor = conn.cursor()
    tables = [
        'tab_sessions', 'learning_goals', 'learning_resources', 'feedbacks', 'evaluations',
        'submissions', 'sample_documents', 'tasks', 'assignments',
        'scenarios', 'tech_recommendations', 'projects', 'interns', 'mentors', 'users'
    ]
    # Check if documents table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='documents'")
    if cursor.fetchone():
        tables.insert(0, 'documents')

    cursor.execute("PRAGMA foreign_keys = OFF;")
    for tbl in tables:
        try:
            cursor.execute(f"DELETE FROM {tbl};")
            cursor.execute(f"DELETE FROM sqlite_sequence WHERE name='{tbl}';")
        except Exception as e:
            print(f"Note on clearing {tbl}: {e}")
    cursor.execute("PRAGMA foreign_keys = ON;")
    conn.commit()
    conn.close()
    print("All website database tables have been completely cleared.")

def clean_upload_folders():
    """Removes previous demo upload files from all upload directories."""
    import shutil
    for folder in [Config.SUBMISSIONS_FOLDER, Config.SAMPLES_FOLDER, Config.UPSKILLING_FOLDER, Config.UPLOAD_FOLDER / 'documents']:
        if folder.exists():
            for item in folder.iterdir():
                try:
                    if item.is_file():
                        item.unlink()
                    elif item.is_dir() and item.name != 'extracted':
                        shutil.rmtree(item)
                except Exception as e:
                    print(f"Note on cleaning {item}: {e}")

def seed_db():
    """
    Seeds ONLY the 4 required production users:
    1. Mentor: Varshitha (varshitha@gmail.com / varshitha@123)
    2. Intern: Bhumika (bhumika@gmail.com / bhumika123)
    3. Intern: Deepika (deepika@gmail.com / deepika123)
    4. Intern: Lakshmi (lakshmi@gmail.com / lakshmi123)
    
    Creates 0 projects, 0 assignments, 0 tasks, 0 submissions, 0 evaluations.
    Safe and predictable — handles existing users without creating duplicates.
    """
    conn = get_db()
    cursor = conn.cursor()

    # Define exact 4 user accounts
    users_to_create = [
        {
            "role": "mentor",
            "full_name": "Varshitha",
            "email": "varshitha@gmail.com",
            "username": "varshitha",
            "password": "varshitha@123",
            "department": "Engineering",
            "expertise": "AI & Cloud Architecture (5+ Years)"
        },
        {
            "role": "intern",
            "full_name": "Bhumika",
            "email": "bhumika@gmail.com",
            "username": "bhumika",
            "password": "bhumika123",
            "skills": "Python, Machine Learning, Data Structures, Flask",
            "technologies": "Python, Flask, SQLite, HTML/CSS",
            "experience": "3rd",
            "joining_date": "2026-08-01"
        },
        {
            "role": "intern",
            "full_name": "Deepika",
            "email": "deepika@gmail.com",
            "username": "deepika",
            "password": "deepika123",
            "skills": "Python, Deep Learning, Computer Vision, SQL",
            "technologies": "Python, PyTorch, OpenCV, Flask, SQL",
            "experience": "4th",
            "joining_date": "2026-04-10"
        },
        {
            "role": "intern",
            "full_name": "Lakshmi",
            "email": "lakshmi@gmail.com",
            "username": "lakshmi",
            "password": "lakshmi123",
            "skills": "Python, Natural Language Processing, LLMs, REST APIs",
            "technologies": "Python, LangChain, Gemini API, Flask, SQL",
            "experience": "4th",
            "joining_date": "2026-06-15"
        }
    ]

    for u in users_to_create:
        cursor.execute("SELECT id FROM users WHERE email = ?", (u["email"],))
        existing = cursor.fetchone()
        
        pwd_hash = generate_password_hash(u["password"])
        
        if not existing:
            cursor.execute('''
            INSERT INTO users (username, password_hash, role, full_name, email)
            VALUES (?, ?, ?, ?, ?)
            ''', (u["username"], pwd_hash, u["role"], u["full_name"], u["email"]))
            user_id = cursor.lastrowid

            if u["role"] == "mentor":
                cursor.execute('''
                INSERT INTO mentors (user_id, department, expertise)
                VALUES (?, ?, ?)
                ''', (user_id, u["department"], u["expertise"]))
            elif u["role"] == "intern":
                cursor.execute('''
                INSERT INTO interns (user_id, name, skills, technologies, experience, workload, availability, joining_date)
                VALUES (?, ?, ?, ?, ?, 'Low', 'Available', ?)
                ''', (user_id, u["full_name"], u["skills"], u["technologies"], u["experience"], u.get("joining_date", "2026-08-01")))
        else:
            # Update password hash to ensure exact required credentials
            cursor.execute('''
            UPDATE users SET password_hash = ?, full_name = ?, username = ?
            WHERE id = ?
            ''', (pwd_hash, u["full_name"], u["username"], existing['id']))
            if u["role"] == "intern" and u.get("joining_date"):
                cursor.execute('''
                UPDATE interns SET joining_date = ?, experience = ? WHERE user_id = ?
                ''', (u["joining_date"], u["experience"], existing['id']))

    conn.commit()
    conn.close()
    print("Mentora AI clean user seed completed: 1 Mentor + 3 Interns ready.")

if __name__ == '__main__':
    init_db()
    clear_all_data()
    clean_upload_folders()
    seed_db()
    print("Database reset & initialized with only the 4 requested accounts.")
