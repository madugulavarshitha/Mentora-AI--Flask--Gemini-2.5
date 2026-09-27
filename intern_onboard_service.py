import re
import secrets
import string
import json
import datetime
from werkzeug.security import generate_password_hash
from database import get_db
from config import Config

def calculate_tenure(joining_date_val):
    """
    Calculates formatted date and tenure duration in months / days.
    Returns: (formatted_date: str, tenure_str: str, raw_date: str)
    e.g. ("15 Jan 2026", "8 months in company", "2026-01-15")
    """
    if not joining_date_val:
        today = datetime.date.today()
        return today.strftime("%d %b %Y"), "< 1 month", today.strftime("%Y-%m-%d")
    
    try:
        if isinstance(joining_date_val, datetime.datetime):
            join_dt = joining_date_val.date()
        elif isinstance(joining_date_val, datetime.date):
            join_dt = joining_date_val
        elif isinstance(joining_date_val, str):
            clean_str = joining_date_val.split(' ')[0].split('T')[0]
            parts = [int(p) for p in clean_str.split('-')]
            join_dt = datetime.date(parts[0], parts[1], parts[2])
        else:
            today = datetime.date.today()
            return str(joining_date_val), "1 month", today.strftime("%Y-%m-%d")
            
        today = datetime.date.today()
        
        # Calculate months difference
        total_months = (today.year - join_dt.year) * 12 + (today.month - join_dt.month)
        if today.day < join_dt.day:
            total_months = max(0, total_months - 1)
            
        days_diff = (today - join_dt).days
        
        if total_months <= 0:
            if days_diff <= 0:
                tenure_str = "Joined today"
            elif days_diff == 1:
                tenure_str = "1 day"
            elif days_diff < 30:
                tenure_str = f"{days_diff} days (< 1 mo)"
            else:
                tenure_str = "1 month"
        elif total_months == 1:
            tenure_str = "1 month"
        else:
            tenure_str = f"{total_months} months"
            
        formatted_date = join_dt.strftime("%d %b %Y")
        return formatted_date, tenure_str, join_dt.strftime("%Y-%m-%d")
    except Exception:
        return str(joining_date_val), "1 month", str(joining_date_val)

def generate_secure_password(length: int = 10) -> str:
    """Generates a secure, human-friendly password (e.g. Mentor#2026!7k)"""
    adjectives = ["Nova", "Apex", "Spark", "Swift", "Bright", "Prime", "Quantum", "Echo", "Atlas", "Zenith"]
    adj = secrets.choice(adjectives)
    num = secrets.randbelow(900) + 100
    special = secrets.choice(["!", "@", "#", "$", "%", "&", "*"])
    char_suffix = secrets.choice(string.ascii_uppercase) + secrets.choice(string.ascii_lowercase)
    return f"{adj}#{num}{special}{char_suffix}"

def provision_intern(
    full_name: str,
    email: str,
    password: str = None,
    department: str = "Engineering",
    skills: str = "Python, Web Development",
    technologies: str = "Python, Flask, SQL, HTML/CSS",
    experience: str = "3rd",
    project_id: int = None,
    joining_date: str = None
) -> tuple:
    """
    Creates a new user and intern profile, generates credentials if not provided,
    and optionally assigns to a project.
    Returns: (success: bool, credential_data: dict, error_msg: str)
    """
    full_name = (full_name or "").strip()
    email = (email or "").strip().lower()
    
    if not full_name:
        return False, None, "Full name is required."
    if not email or "@" not in email:
        return False, None, "A valid email address is required."
        
    plain_password = password.strip() if password and password.strip() else generate_secure_password()
    username = email.split('@')[0]
    
    if not joining_date or not str(joining_date).strip():
        joining_date = datetime.date.today().strftime("%Y-%m-%d")
    else:
        joining_date = str(joining_date).strip()
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Check if user already exists
        cursor.execute("SELECT id, full_name, email FROM users WHERE email = ? OR username = ?", (email, username))
        existing = cursor.fetchone()
        if existing:
            # If username conflicts with different email, generate unique username
            if existing['email'] != email:
                username = f"{username}_{secrets.randbelow(999)}"
            else:
                conn.close()
                return False, None, f"An account with email '{email}' already exists."

        # Insert into users table
        pwd_hash = generate_password_hash(plain_password)
        cursor.execute('''
            INSERT INTO users (username, password_hash, role, full_name, email)
            VALUES (?, ?, 'intern', ?, ?)
        ''', (username, pwd_hash, full_name, email))
        user_id = cursor.lastrowid
        
        # Insert into interns table
        cursor.execute('''
            INSERT INTO interns (user_id, name, skills, technologies, experience, workload, availability, joining_date)
            VALUES (?, ?, ?, ?, ?, 'Low', 'Available', ?)
        ''', (user_id, full_name, skills, technologies, experience, joining_date))
        intern_id = cursor.lastrowid
        
        project_title = None
        # Optionally assign project if provided
        if project_id:
            cursor.execute("SELECT id, title FROM projects WHERE id = ?", (project_id,))
            proj = cursor.fetchone()
            if proj:
                project_title = proj['title']
                cursor.execute('''
                    INSERT INTO assignments (project_id, intern_id, role, status, progress, start_date)
                    VALUES (?, ?, 'Core Intern', 'Active', 0, CURRENT_DATE)
                ''', (project_id, intern_id))
        
        conn.commit()
        conn.close()
        
        formatted_date, tenure_str, raw_date = calculate_tenure(joining_date)
        
        credential_data = {
            "user_id": user_id,
            "intern_id": intern_id,
            "full_name": full_name,
            "username": username,
            "email": email,
            "password": plain_password,
            "role": "intern",
            "department": department,
            "skills": skills,
            "technologies": technologies,
            "experience": experience,
            "joining_date": raw_date,
            "joining_date_formatted": formatted_date,
            "tenure_display": tenure_str,
            "project_id": project_id,
            "project_title": project_title,
            "login_url": "/intern/signin"
        }
        return True, credential_data, None

    except Exception as e:
        conn.rollback()
        conn.close()
        return False, None, f"Database error during intern provisioning: {str(e)}"


def reset_intern_credentials(user_id: int) -> tuple:
    """Generates a new secure password for an existing intern."""
    new_password = generate_secure_password()
    pwd_hash = generate_password_hash(new_password)
    
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, full_name, email, username FROM users WHERE id = ? AND role = 'intern'", (user_id,))
        user = cursor.fetchone()
        if not user:
            conn.close()
            return False, None, "Intern user not found."
            
        cursor.execute("UPDATE users SET password_hash = ? WHERE id = ?", (pwd_hash, user_id))
        conn.commit()
        conn.close()
        
        data = {
            "user_id": user['id'],
            "full_name": user['full_name'],
            "email": user['email'],
            "username": user['username'],
            "new_password": new_password,
            "login_url": "/intern/signin"
        }
        return True, data, None
    except Exception as e:
        conn.rollback()
        conn.close()
        return False, None, f"Error resetting credentials: {str(e)}"


def delete_intern_account(user_id: int) -> tuple:
    """Deletes an intern's user account and associated profile."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, full_name FROM users WHERE id = ? AND role = 'intern'", (user_id,))
        user = cursor.fetchone()
        if not user:
            conn.close()
            return False, "Intern not found."
            
        cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
        conn.close()
        return True, None
    except Exception as e:
        conn.rollback()
        conn.close()
        return False, str(e)


def get_all_interns_with_stats() -> list:
    """Returns all interns with assigned projects, joining date, tenure and status."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT 
            u.id as user_id,
            u.full_name,
            u.email,
            u.username,
            u.created_at,
            i.id as intern_id,
            i.skills,
            i.technologies,
            i.experience,
            i.workload,
            i.availability,
            COALESCE(i.joining_date, DATE(u.created_at), DATE('now')) as joining_date,
            COUNT(DISTINCT a.id) as assigned_projects_count,
            GROUP_CONCAT(DISTINCT p.title) as project_titles
        FROM users u
        JOIN interns i ON u.id = i.user_id
        LEFT JOIN assignments a ON i.id = a.intern_id
        LEFT JOIN projects p ON a.project_id = p.id
        WHERE u.role = 'intern'
        GROUP BY u.id
        ORDER BY u.created_at DESC
    ''')
    rows = [dict(row) for row in cursor.fetchall()]
    for r in rows:
        formatted_dt, tenure_str, raw_dt = calculate_tenure(r.get('joining_date') or r.get('created_at'))
        r['joining_date_formatted'] = formatted_dt
        r['tenure_display'] = tenure_str
        r['joining_date'] = raw_dt
    conn.close()
    return rows


def ai_parse_and_provision_interns(prompt_text: str, default_project_id: int = None) -> tuple:
    """
    Uses AI (Gemini or structured smart parser) to parse natural language or bulk intern roster,
    provisions each intern in the database, and returns the credentials summary.
    """
    if not prompt_text or not prompt_text.strip():
        return False, [], "Please provide intern details or a prompt."

    parsed_candidates = []
    
    # 1. Try Gemini API extraction if available
    try:
        from gemini_service import call_gemini, clean_json_text
        ai_prompt = f"""You are an HR & Mentorship Data Extraction Agent.
Extract all intern details from the following user prompt into a JSON array of objects.

User Input:
\"\"\"{prompt_text}\"\"\"

Return ONLY valid JSON format with this exact structure:
[
  {{
    "full_name": "Full Name",
    "email": "email@example.com",
    "department": "Engineering / AI / Web / Mobile / Data Science / UI/UX / Cloud",
    "skills": "Key skills separated by commas",
    "technologies": "Tools / tech stack separated by commas",
    "experience": "1st / 2nd / 3rd / 4th / Graduate",
    "joining_date": "YYYY-MM-DD"
  }}
]

If email is missing in the prompt, generate a reasonable email like firstname.lastname@mentora.edu.
If joining date is missing, use current date or infer from months mentioned.
Experience must be one of: 1st, 2nd, 3rd, 4th, Graduate."""
        raw_text = call_gemini(ai_prompt)
        if raw_text:
            cleaned = clean_json_text(raw_text)
            data = json.loads(cleaned)
            if isinstance(data, list):
                parsed_candidates = data
    except Exception as e:
        print(f"[AI Provision Parse Info] Regex parser active: {e}")

    # 2. Fallback Smart Rule-Based Parser if AI didn't return candidates
    if not parsed_candidates:
        lines = prompt_text.strip().split('\n')
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Extract email if present
            email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', line)
            email = email_match.group(0) if email_match else ""
            
            # Remove email from line to get name & skills
            clean_line = re.sub(r'[\w\.-]+@[\w\.-]+\.\w+', '', line)
            parts = re.split(r'[-–,|;:]', clean_line)
            parts = [p.strip() for p in parts if p.strip()]
            
            name = parts[0] if len(parts) > 0 else "New Intern"
            # Clean up bullet points, numbers, "Add intern" phrases
            name = re.sub(r'^(?:add\s+intern|intern\s*\d*|\d+[\.\)]|\*|-)\s*', '', name, flags=re.IGNORECASE).strip()
            if not name:
                name = "Intern Candidate"
                
            if not email:
                email_name = re.sub(r'[^a-zA-Z0-9]', '.', name.lower()).strip('.')
                email = f"{email_name}@mentora.edu"
                
            skills = parts[1] if len(parts) > 1 else "Python, Web Development"
            dept = parts[2] if len(parts) > 2 else "Engineering"
            
            parsed_candidates.append({
                "full_name": name,
                "email": email,
                "department": dept,
                "skills": skills,
                "technologies": skills,
                "experience": "3rd"
            })

    if not parsed_candidates:
        return False, [], "Could not parse any intern information from the input."

    # Provision each parsed intern
    created_interns = []
    errors = []
    
    for item in parsed_candidates:
        fn = item.get("full_name", "Intern")
        em = item.get("email", "")
        dept = item.get("department", "Engineering")
        sk = item.get("skills", "Python, Web")
        tech = item.get("technologies", sk)
        exp = item.get("experience", "3rd")
        j_date = item.get("joining_date")
        
        ok, creds, err = provision_intern(
            full_name=fn,
            email=em,
            password=None, # auto-generate strong password
            department=dept,
            skills=sk,
            technologies=tech,
            experience=exp,
            project_id=default_project_id,
            joining_date=j_date
        )
        if ok:
            created_interns.append(creds)
        else:
            errors.append(f"{fn} ({em}): {err}")
            
    if created_interns:
        return True, created_interns, "; ".join(errors) if errors else None
    else:
        return False, [], "; ".join(errors) if errors else "Failed to provision interns."


def send_intern_credentials_email(
    to_email: str,
    full_name: str,
    username: str,
    password: str,
    login_url: str = "http://127.0.0.1:5000/intern/signin",
    project_title: str = None,
    mentor_name: str = "Technical Mentor",
    mentor_email: str = None
) -> tuple:
    """
    Sends a beautifully formatted onboarding email containing login credentials,
    portal URL, and instructions to the intern.
    Returns: (success: bool, message: str, real_smtp: bool)
    """
    import os
    to_email = (to_email or "").strip()
    if not to_email or "@" not in to_email:
        return False, "Invalid intern email address.", False

    full_name = full_name or "Intern"
    username = username or to_email.split('@')[0]
    subject = f"🎓 Welcome to MENTORA AI — Your Intern Credentials & Portal Sign-In"

    # Project detail snippet if assigned
    project_snippet = f"\n• Assigned Project: {project_title}" if project_title else ""
    project_snippet_html = f"""
    <tr>
      <td style="padding: 8px 12px; font-size: 13px; color: #64748B; font-weight: 600;">Assigned Project:</td>
      <td style="padding: 8px 12px; font-size: 13px; color: #633DF4; font-weight: 700;">{project_title}</td>
    </tr>
    """ if project_title else ""

    plain_body = f"""Dear {full_name},

Welcome to the MENTORA AI Mentorship Program!

Your intern workspace account has been successfully provisioned. You can now log in to the portal to view your assigned projects, collaborate with your mentor, submit project milestones, and use the AI Copilot.

======================================================================
YOUR MENTORA AI PORTAL CREDENTIALS
======================================================================
• Portal Sign-In URL : {login_url}
• Login Email        : {to_email}
• Username           : {username}
• Temporary Password : {password}{project_snippet}
======================================================================

GETTING STARTED NEXT STEPS:
1. Open the portal sign-in page: {login_url}
2. Enter your email/username and password.
3. Review your assigned tasks, milestones, and learning vault.
4. If you have any questions or need guidance, reply directly to this email.

Best regards,

{mentor_name}
Lead Technical Mentor & Evaluator
MENTORA AI Intelligent Mentorship Platform
Smartbridge Mentorship Network
"""

    html_body = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Welcome to MENTORA AI</title>
</head>
<body style="font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, Helvetica, Arial, sans-serif; background-color: #F8FAFC; margin: 0; padding: 30px 15px; color: #1E293B;">
  <div style="max-width: 600px; margin: 0 auto; background: #FFFFFF; border-radius: 18px; overflow: hidden; border: 1px solid #E2DCF8; box-shadow: 0 10px 30px rgba(99, 61, 244, 0.08);">
    
    <!-- Top Gradient Header -->
    <div style="background: linear-gradient(135deg, #633DF4 0%, #7F56D9 50%, #4F46E5 100%); padding: 32px 28px; text-align: center; color: #FFFFFF;">
      <div style="display: inline-block; background: rgba(255, 255, 255, 0.2); padding: 6px 14px; border-radius: 20px; font-size: 12px; font-weight: 700; letter-spacing: 0.5px; margin-bottom: 12px; text-transform: uppercase;">
        🤖 Mentora AI Workspace
      </div>
      <h1 style="margin: 0; font-size: 24px; font-weight: 800; letter-spacing: -0.5px;">Welcome to MENTORA AI</h1>
      <p style="margin: 8px 0 0 0; font-size: 14px; opacity: 0.9;">Your Intern Account & Login Credentials are Ready</p>
    </div>

    <!-- Main Content Body -->
    <div style="padding: 28px;">
      <p style="font-size: 15px; line-height: 1.6; color: #334155; margin-top: 0;">
        Hello <strong>{full_name}</strong>,
      </p>
      <p style="font-size: 14px; line-height: 1.6; color: #475569;">
        We are thrilled to welcome you to the <strong>MENTORA AI Mentorship Program</strong>. Your dedicated intern workspace account has been created by your mentor.
      </p>

      <!-- Credentials Box -->
      <div style="background: #FAF8FF; border: 1.5px solid #DED7F9; border-radius: 14px; padding: 20px; margin: 24px 0;">
        <div style="font-size: 13px; font-weight: 800; color: #633DF4; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 14px; display: flex; align-items: center; gap: 6px;">
          🔑 Official Portal Access Credentials
        </div>
        <table style="width: 100%; border-collapse: collapse;">
          <tr style="border-bottom: 1px solid #EAE6FC;">
            <td style="padding: 8px 12px; font-size: 13px; color: #64748B; font-weight: 600; width: 38%;">Portal Link:</td>
            <td style="padding: 8px 12px; font-size: 13px; color: #0F172A; font-weight: 700;">
              <a href="{login_url}" style="color: #633DF4; text-decoration: underline;">{login_url}</a>
            </td>
          </tr>
          <tr style="border-bottom: 1px solid #EAE6FC;">
            <td style="padding: 8px 12px; font-size: 13px; color: #64748B; font-weight: 600;">Email / Username:</td>
            <td style="padding: 8px 12px; font-size: 13px; color: #0F172A; font-weight: 700; font-family: monospace;">{to_email}</td>
          </tr>
          <tr style="border-bottom: 1px solid #EAE6FC;">
            <td style="padding: 8px 12px; font-size: 13px; color: #64748B; font-weight: 600;">Password:</td>
            <td style="padding: 8px 12px; font-size: 14px; color: #633DF4; font-weight: 800; font-family: monospace; background: #EDE8FD; border-radius: 6px;">{password}</td>
          </tr>
          {project_snippet_html}
        </table>
      </div>

      <!-- Action Button -->
      <div style="text-align: center; margin: 28px 0;">
        <a href="{login_url}" style="display: inline-block; background: linear-gradient(135deg, #633DF4 0%, #7F56D9 100%); color: #FFFFFF; padding: 14px 32px; border-radius: 12px; font-size: 14px; font-weight: 700; text-decoration: none; box-shadow: 0 4px 14px rgba(99, 61, 244, 0.3);">
          🚀 Sign In to Your Intern Workspace
        </a>
      </div>

      <!-- Quick Steps -->
      <div style="background: #F8FAFC; border-radius: 12px; padding: 16px; margin-top: 24px;">
        <div style="font-size: 12.5px; font-weight: 700; color: #334155; margin-bottom: 8px;">Next Steps:</div>
        <ol style="margin: 0; padding-left: 20px; font-size: 12.5px; color: #64748B; line-height: 1.6;">
          <li>Click the link above to log in to your account.</li>
          <li>Review your assigned project objectives and task roadmap.</li>
          <li>Submit milestone documents to receive automated AI feedback.</li>
          <li>Explore the AI Self-Learning Knowledge Vault for curated resources.</li>
        </ol>
      </div>

      <!-- Sign Off -->
      <div style="margin-top: 28px; padding-top: 18px; border-top: 1px solid #F1F5F9; font-size: 13px; color: #475569;">
        <p style="margin: 0 0 4px 0;">Best regards,</p>
        <p style="margin: 0; font-weight: 700; color: #1E293B;">{mentor_name}</p>
        <p style="margin: 0; font-size: 12px; color: #64748B;">Technical Mentor & Evaluator • MENTORA AI</p>
      </div>

    </div>

    <!-- Footer -->
    <div style="background: #FAF8FF; padding: 14px 28px; text-align: center; font-size: 11px; color: #94A3B8; border-top: 1px solid #EAE6FC;">
      © 2026 MENTORA AI • Smartbridge Intelligent Mentorship Workspace
    </div>

  </div>
</body>
</html>
"""

    smtp_host = os.getenv('SMTP_HOST')
    smtp_port = int(os.getenv('SMTP_PORT', 587))
    smtp_user = os.getenv('SMTP_USER')
    smtp_pass = os.getenv('SMTP_PASS')
    smtp_from = os.getenv('SMTP_FROM', mentor_email or smtp_user or 'noreply@mentora.ai')

    real_smtp = False
    if smtp_host and smtp_user and smtp_pass:
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart

            msg = MIMEMultipart('alternative')
            msg['From'] = f"MENTORA AI <{smtp_from}>"
            msg['To'] = to_email
            msg['Subject'] = subject

            part1 = MIMEText(plain_body, 'plain')
            part2 = MIMEText(html_body, 'html')
            msg.attach(part1)
            msg.attach(part2)

            server = smtplib.SMTP(smtp_host, smtp_port, timeout=10)
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_from, [to_email], msg.as_string())
            server.quit()
            real_smtp = True
            print(f"[SMTP Success] Credentials email dispatched to {to_email}")
        except Exception as e:
            print(f"[SMTP Error] Failed to send email to {to_email}: {e}")
    else:
        print(f"[Email Dispatch Simulated] Credentials ready for {full_name} <{to_email}> (Login URL: {login_url})")

    return True, f"Login credentials successfully sent to {to_email}!", real_smtp


def batch_send_credentials_emails(
    interns: list,
    login_url: str = "http://127.0.0.1:5000/intern/signin",
    mentor_name: str = "Technical Mentor",
    mentor_email: str = None
) -> tuple:
    """Dispatches credentials emails to a list of provisioned interns."""
    successes = []
    errors = []
    
    for item in interns:
        to_email = item.get('email', '')
        fn = item.get('full_name', 'Intern')
        un = item.get('username', to_email.split('@')[0] if to_email else '')
        pwd = item.get('password') or item.get('new_password', '')
        proj = item.get('project_title')
        
        if not to_email or not pwd:
            errors.append(f"Missing email or password for {fn}")
            continue
            
        ok, msg, real_smtp = send_intern_credentials_email(
            to_email=to_email,
            full_name=fn,
            username=un,
            password=pwd,
            login_url=login_url,
            project_title=proj,
            mentor_name=mentor_name,
            mentor_email=mentor_email
        )
        if ok:
            successes.append(to_email)
        else:
            errors.append(f"{fn} ({to_email}): {msg}")
            
    return len(successes), successes, errors

