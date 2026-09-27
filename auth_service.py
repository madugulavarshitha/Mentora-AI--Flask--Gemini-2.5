from werkzeug.security import generate_password_hash, check_password_hash
from database import get_db

def register_mentor(full_name: str, email: str, password: str, organization: str = 'Mentora Enterprise', department: str = 'Engineering', specialization: str = 'AI & Cloud', years_of_experience: str = '5+ Years'):
    conn = get_db()
    cursor = conn.cursor()
    
    # Check if user exists
    cursor.execute("SELECT id FROM users WHERE email = ? OR username = ?", (email, email))
    if cursor.fetchone():
        conn.close()
        return None, "An account with this email address already exists."

    username = email.split('@')[0]
    pwd_hash = generate_password_hash(password)
    
    cursor.execute('''
    INSERT INTO users (username, password_hash, role, full_name, email)
    VALUES (?, ?, 'mentor', ?, ?)
    ''', (username, pwd_hash, full_name, email))
    user_id = cursor.lastrowid
    
    cursor.execute('''
    INSERT INTO mentors (user_id, department, expertise)
    VALUES (?, ?, ?)
    ''', (user_id, department, f"{specialization} ({years_of_experience})"))
    
    conn.commit()
    conn.close()
    return user_id, None

def register_intern(full_name: str, email: str, password: str, college: str = 'Engineering College', course: str = 'Computer Science', year_of_study: str = 'Final Year', skills: str = 'Python, AI', technologies: str = 'Python, Flask, SQL', experience: str = 'Intermediate'):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT id FROM users WHERE email = ? OR username = ?", (email, email))
    if cursor.fetchone():
        conn.close()
        return None, "An account with this email address already exists."

    username = email.split('@')[0]
    pwd_hash = generate_password_hash(password)
    
    cursor.execute('''
    INSERT INTO users (username, password_hash, role, full_name, email)
    VALUES (?, ?, 'intern', ?, ?)
    ''', (username, pwd_hash, full_name, email))
    user_id = cursor.lastrowid
    
    cursor.execute('''
    INSERT INTO interns (user_id, name, skills, technologies, experience, workload, availability)
    VALUES (?, ?, ?, ?, ?, 'Low', 'Available')
    ''', (user_id, full_name, skills, technologies, f"{experience} ({college}, {course})"))
    
    conn.commit()
    conn.close()
    return user_id, None

def authenticate_user(identifier: str, password: str, required_role: str = None):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE username = ? OR email = ?', (identifier, identifier))
    user = cursor.fetchone()
    conn.close()
    
    if not user:
        return None, "No account found matching those credentials."
        
    if not check_password_hash(user['password_hash'], password):
        return None, "Invalid password. Please verify and try again."
        
    if required_role and user['role'] != required_role and user['role'] != 'admin':
        return None, f"This portal is for {required_role}s only. Please switch to the {user['role']} sign-in page."
        
    return dict(user), None
