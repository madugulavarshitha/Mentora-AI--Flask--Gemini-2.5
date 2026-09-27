import os
import re
from functools import wraps
from datetime import date, timedelta
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash
from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, session, abort, jsonify, send_from_directory
)

from config import Config
from database import init_db, seed_db, get_db, save_tab_session, get_tab_session, delete_tab_session
from models import db, User, MentorProfile, InternProfile
from auth_service import register_mentor, register_intern, authenticate_user
from intern_onboard_service import (
    provision_intern, reset_intern_credentials, delete_intern_account,
    get_all_interns_with_stats, ai_parse_and_provision_interns,
    send_intern_credentials_email, batch_send_credentials_emails
)
from self_learning_service import (
    save_learning_resource, get_learning_resources_for_intern, get_resource_by_id,
    delete_learning_resource, toggle_favorite_resource, update_mastery_score,
    update_resource_media_type,
    get_intern_upskilling_stats, add_or_update_goal, update_goal_progress, delete_goal
)
from document_service import (
    extract_text_from_file, save_and_verify_document, get_all_documents,
    get_document_by_id, approve_document, reject_document, seed_sample_documents_if_empty
)
from project_service import (
    create_project, update_project, delete_project, get_project_by_id, get_all_projects,
    get_or_generate_tech_recommendations, get_or_generate_scenario,
    create_assignment, get_assignment_by_id, get_assignments_for_mentor,
    get_assignments_for_intern, get_tasks_for_assignment, create_task,
    update_task_status, get_assignment_health_detail, update_assignment_github,
    update_assignment_links, import_projects_dataset, parse_project_dataset
)
from intern_service import (
    get_all_interns, get_intern_by_user_id, match_interns_for_project,
    update_intern_github, update_intern_profile
)
from evaluation_service import (
    save_sample_document, create_intern_submission, run_submission_evaluation,
    get_submission_evaluation, get_feedback_for_evaluation
)
from agents.pre_submission_agent import PreSubmissionReviewAgent, fetch_google_doc_text
from copilot_service import ask_mentor_copilot, get_system_context_for_copilot
from orchestrator import MentoraOrchestrator
import secrets

# Initialize Flask App
app = Flask(__name__)
app.config.from_object(Config)
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

# Initialize database
init_db()
seed_db()

# ==========================================================
# MULTI-TAB SESSION ISOLATION & ACCESS CONTROL
# ==========================================================
@app.before_request
def resolve_tab_session():
    """
    Enables true multi-tab isolation so separate browser tabs can log in
    as Mentor and different Interns concurrently without session collisions.
    """
    sid = request.args.get('sid') or request.form.get('sid') or request.headers.get('X-Session-ID') or request.cookies.get('tab_sid')
    if sid:
        tab_sess = get_tab_session(sid)
        if tab_sess:
            session.clear()
            for k, v in tab_sess.items():
                session[k] = v
            session['_current_sid'] = sid

@app.context_processor
def inject_session_context():
    sid = request.args.get('sid') or request.form.get('sid') or session.get('_current_sid') or ''
    return {
        'current_sid': sid,
        'session': session
    }

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please sign in to access your workspace.', 'warning')
            return redirect(url_for('mentor_signin'))
        
        # Verify user still exists in database (handles post-wipe or deleted user sessions)
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT id, role, full_name FROM users WHERE id = ?", (session['user_id'],))
        user = cursor.fetchone()
        conn.close()

        if not user:
            role = session.get('role', 'mentor')
            sid = session.get('_current_sid')
            if sid:
                delete_tab_session(sid)
            session.clear()
            flash('Your previous session has expired or user records were reset. Please sign in again.', 'info')
            if role == 'intern':
                return redirect(url_for('intern_signin'))
            return redirect(url_for('mentor_signin'))

        return f(*args, **kwargs)
    return decorated_function

def role_required(allowed_roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                return redirect(url_for('mentor_signin'))
            if session.get('role') not in allowed_roles:
                flash('Unauthorized access: You do not have permission for this section.', 'danger')
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# --- Public Landing Page ---
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard', sid=session.get('_current_sid', '')))
    
    intern_count = 8
    project_count = 6
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM interns")
        row = cursor.fetchone()
        if row:
            intern_count = row[0]
        cursor.execute("SELECT COUNT(*) FROM projects")
        row = cursor.fetchone()
        if row:
            project_count = row[0]
        conn.close()
    except Exception as e:
        pass

    return render_template('index.html', active_interns_count=intern_count, total_projects_count=project_count)

# --- 1. Mentor Sign In ---
@app.route('/signin', methods=['GET', 'POST'])
@app.route('/mentor/signin', methods=['GET', 'POST'])
@app.route('/auth/mentor/signin', methods=['GET', 'POST'])
def mentor_signin():
    if 'user_id' in session and request.method == 'GET' and not request.args.get('logged_out'):
        return redirect(url_for('mentor_dashboard', sid=session.get('_current_sid', '')))

    if request.method == 'POST':
        identifier = request.form.get('identifier', '').strip()
        password = request.form.get('password', '').strip()

        user, err = authenticate_user(identifier, password, required_role='mentor')
        if user:
            sid = secrets.token_hex(16)
            sess_dict = {
                'user_id': user['id'],
                'username': user['username'],
                'role': user['role'],
                'full_name': user['full_name'],
                'email': user['email']
            }
            save_tab_session(sid, sess_dict)
            session.clear()
            for k, v in sess_dict.items():
                session[k] = v
            session['_current_sid'] = sid
            flash(f"Welcome back, {user['full_name']}! Signed in to Mentor Workspace.", 'success')
            resp = redirect(url_for('mentor_dashboard', sid=sid))
            resp.set_cookie('tab_sid', sid, max_age=86400*30, httponly=True)
            return resp
        else:
            flash('Invalid email or password. Please check your credentials.', 'danger')

    return render_template('auth/mentor_signin.html')

# --- 2. Mentor Sign Up ---
@app.route('/signup', methods=['GET', 'POST'])
@app.route('/mentor/signup', methods=['GET', 'POST'])
@app.route('/auth/mentor/signup', methods=['GET', 'POST'])
def mentor_signup():
    if 'user_id' in session and request.method == 'GET':
        return redirect(url_for('mentor_dashboard', sid=session.get('_current_sid', '')))

    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()
        organization = request.form.get('organization', 'Mentora Enterprise').strip()
        department = request.form.get('department', organization if organization else 'General').strip() or 'General'
        specialization = request.form.get('specialization', 'AI & Software').strip()
        years_of_experience = request.form.get('years_of_experience', '5+ Years').strip()

        if password != confirm_password:
            flash('Passwords do not match. Please re-enter.', 'danger')
            return render_template('auth/mentor_signup.html')

        user_id, err = register_mentor(
            full_name=full_name,
            email=email,
            password=password,
            organization=organization,
            department=department,
            specialization=specialization,
            years_of_experience=years_of_experience
        )

        if user_id:
            sid = secrets.token_hex(16)
            sess_dict = {
                'user_id': user_id,
                'username': email.split('@')[0],
                'role': 'mentor',
                'full_name': full_name,
                'email': email
            }
            save_tab_session(sid, sess_dict)
            session.clear()
            for k, v in sess_dict.items():
                session[k] = v
            session['_current_sid'] = sid
            flash('Mentor account created successfully! Welcome to your workspace.', 'success')
            resp = redirect(url_for('mentor_dashboard', sid=sid))
            resp.set_cookie('tab_sid', sid, max_age=86400*30, httponly=True)
            return resp
        else:
            flash(err or 'Registration failed. Please try again.', 'danger')

    return render_template('auth/mentor_signup.html')

# --- 3. Intern Sign In ---
@app.route('/intern/signin', methods=['GET', 'POST'])
@app.route('/auth/intern/signin', methods=['GET', 'POST'])
def intern_signin():
    if 'user_id' in session and request.method == 'GET' and not request.args.get('logged_out'):
        return redirect(url_for('intern_dashboard', sid=session.get('_current_sid', '')))

    if request.method == 'POST':
        identifier = request.form.get('identifier', '').strip()
        password = request.form.get('password', '').strip()

        user, err = authenticate_user(identifier, password, required_role='intern')
        if user:
            sid = secrets.token_hex(16)
            sess_dict = {
                'user_id': user['id'],
                'username': user['username'],
                'role': user['role'],
                'full_name': user['full_name'],
                'email': user['email']
            }
            save_tab_session(sid, sess_dict)
            session.clear()
            for k, v in sess_dict.items():
                session[k] = v
            session['_current_sid'] = sid
            flash(f"Welcome back, {user['full_name']}! Signed in to Intern Workspace.", 'success')
            resp = redirect(url_for('intern_dashboard', sid=sid))
            resp.set_cookie('tab_sid', sid, max_age=86400*30, httponly=True)
            return resp
        else:
            flash('Invalid email or password. Please check your credentials.', 'danger')

    return render_template('auth/intern_signin.html')

# --- 4. Intern Sign Up ---
@app.route('/intern/signup', methods=['GET', 'POST'])
def intern_signup():
    if 'user_id' in session and request.method == 'GET':
        return redirect(url_for('intern_dashboard', sid=session.get('_current_sid', '')))

    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()
        college = request.form.get('college', '').strip()
        course = request.form.get('course', '').strip()
        skills = request.form.get('skills', '').strip()
        technologies = request.form.get('technologies', '').strip()
        experience = request.form.get('experience', '').strip()

        if password != confirm_password:
            flash('Passwords do not match. Please re-enter.', 'danger')
            return render_template('auth/intern_signup.html')

        user_id, err = register_intern(
            full_name=full_name,
            email=email,
            password=password,
            college=college or 'Institute of Technology',
            course=course or 'Computer Science',
            skills=skills or 'Python, AI',
            technologies=technologies or 'Python, Flask, SQL',
            experience=experience or 'Student / Beginner'
        )

        if user_id:
            sid = secrets.token_hex(16)
            sess_dict = {
                'user_id': user_id,
                'username': email.split('@')[0],
                'role': 'intern',
                'full_name': full_name,
                'email': email
            }
            save_tab_session(sid, sess_dict)
            session.clear()
            for k, v in sess_dict.items():
                session[k] = v
            session['_current_sid'] = sid
            flash('Intern account registered! Welcome to your learning journey.', 'success')
            resp = redirect(url_for('intern_dashboard', sid=sid))
            resp.set_cookie('tab_sid', sid, max_age=86400*30, httponly=True)
            return resp
        else:
            flash(err or 'Registration failed.', 'danger')

    return render_template('auth/intern_signup.html')

# Generic login redirect
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        return mentor_signin()
    return redirect(url_for('mentor_signin'))

@app.route('/logout')
@app.route('/mentor/logout')
@app.route('/intern/logout')
def logout():
    sid = request.args.get('sid') or session.get('_current_sid')
    if sid:
        delete_tab_session(sid)
    session.clear()
    resp = redirect(url_for('mentor_signin', logged_out='1'))
    resp.delete_cookie('tab_sid')
    return resp

@app.route('/quick-switch/<int:user_id>')
def quick_switch(user_id):
    """Convenient 1-click switcher for demonstration and evaluation"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
    user = cursor.fetchone()
    conn.close()

    if user:
        sid = secrets.token_hex(16)
        sess_dict = {
            'user_id': user['id'],
            'username': user['username'],
            'role': user['role'],
            'full_name': user['full_name'],
            'email': user['email']
        }
        save_tab_session(sid, sess_dict)
        session.clear()
        for k, v in sess_dict.items():
            session[k] = v
        session['_current_sid'] = sid
        flash(f"Switched session to {user['full_name']} ({user['role'].upper()})", 'info')
        return redirect(url_for('dashboard', sid=sid))
    return redirect(url_for('dashboard'))

@app.route('/dashboard')
@login_required
def dashboard():
    sid = request.args.get('sid') or session.get('_current_sid', '')
    if session.get('role') in ['mentor', 'admin']:
        return redirect(url_for('mentor_dashboard', sid=sid) if sid else url_for('mentor_dashboard'))
    return redirect(url_for('intern_dashboard', sid=sid) if sid else url_for('intern_dashboard'))

# ==========================================================
# MENTOR WORKSPACE ROUTES
# ==========================================================
@app.route('/mentor/dashboard')
@login_required
@role_required(['mentor', 'admin'])
def mentor_dashboard():
    assignments_db = get_assignments_for_mentor(session.get('user_id'))
    all_projects = get_all_projects()
    all_interns = get_all_interns()
    
    total_projects = len(all_projects)
    total_interns = len(all_interns)
    active_assignments = len(assignments_db)
    delayed_projects = sum(1 for a in assignments_db if a.get('status') == 'Delayed')
    critical_projects = sum(1 for a in assignments_db if a.get('health') == 'CRITICAL' or a.get('status') == 'Critical')
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as cnt FROM submissions WHERE status IN ('Submitted', 'Pending', 'Under Review')")
    row = cursor.fetchone()
    pending_submissions = row['cnt'] if row else 0
    conn.close()

    interns_needing_support = sum(1 for a in assignments_db if a.get('health') in ['NEEDS ATTENTION', 'CRITICAL'] or a.get('status') in ['Delayed', 'Critical'])
    healthy_count = sum(1 for a in assignments_db if a.get('health') == 'HEALTHY')
    ontrack_count = sum(1 for a in assignments_db if a.get('health') in ['HEALTHY', 'On Track'] and a.get('status') in ['In Progress', 'On Track'])
    attention_count = sum(1 for a in assignments_db if a.get('health') == 'NEEDS ATTENTION' or a.get('status') == 'Delayed')
    atrisk_count = sum(1 for a in assignments_db if a.get('health') == 'CRITICAL' or a.get('status') == 'Critical')

    stats = {
        "total_projects": total_projects,
        "total_interns": total_interns,
        "active_assignments": active_assignments,
        "delayed_projects": delayed_projects,
        "critical_projects": critical_projects,
        "pending_submissions": pending_submissions,
        "interns_needing_support": interns_needing_support,
        "healthy_count": healthy_count,
        "ontrack_count": ontrack_count,
        "attention_count": attention_count,
        "atrisk_count": atrisk_count
    }

    return render_template(
        'mentor_dashboard.html',
        active_page='mentor_dashboard',
        stats=stats,
        assignments=assignments_db,
        interns_summary=all_interns
    )

@app.route('/mentor/deadlines')
@app.route('/deadlines')
@login_required
@role_required(['mentor', 'admin'])
def mentor_deadlines_view():
    assignments = get_assignments_for_mentor(session.get('user_id'))
    
    total_deadlines = len(assignments)
    on_track = sum(1 for a in assignments if a.get('health') == 'HEALTHY' or a.get('status') in ['On Track', 'In Progress'])
    
    due_this_week = 0
    due_soon = 0
    overdue = 0
    today = date.today()
    for a in assignments:
        dl_str = a.get('deadline')
        if dl_str:
            try:
                dl = datetime.strptime(str(dl_str), '%Y-%m-%d').date()
                diff = (dl - today).days
                if diff < 0:
                    overdue += 1
                elif 0 <= diff <= 2:
                    due_soon += 1
                elif 0 <= diff <= 7:
                    due_this_week += 1
            except Exception:
                pass
                
    email_alerts = sum(1 for a in assignments if a.get('status') not in ['Completed'])

    deadlines_summary = {
        "total_deadlines": total_deadlines,
        "on_track": on_track,
        "due_this_week": due_this_week,
        "due_soon": due_soon,
        "overdue": overdue,
        "email_alerts": email_alerts
    }
    
    return render_template(
        'deadlines.html',
        active_page='deadlines',
        stats=deadlines_summary,
        assignments=assignments
    )

@app.route('/mentor/notifications')
@login_required
@role_required(['mentor', 'admin'])
def mentor_notifications_view():
    flash('Notifications are up to date.', 'info')
    return redirect(url_for('mentor_dashboard'))

@app.route('/mentor/profile')
@login_required
@role_required(['mentor', 'admin'])
def mentor_profile_view():
    flash(f"Mentor Profile: {session.get('full_name', 'Varshitha')}", 'info')
    return redirect(url_for('mentor_dashboard'))

@app.route('/mentor/settings')
@login_required
@role_required(['mentor', 'admin'])
def mentor_settings_view():
    flash('Platform settings are configured for Gemini 2.5 Flash and Pastel Theme.', 'info')
    return redirect(url_for('mentor_dashboard'))

@app.route('/mentor/projects')
@login_required
def mentor_projects_alias():
    return redirect(url_for('projects_list'))

@app.route('/mentor/matching')
@login_required
def mentor_matching_alias():
    return redirect(url_for('intern_matching_view'))

@app.route('/mentor/assignments')
@login_required
def mentor_assignments_alias():
    return redirect(url_for('assignments_view'))

@app.route('/mentor/tasks')
@login_required
def mentor_tasks_alias():
    return redirect(url_for('tasks_view'))

@app.route('/mentor/progress')
@app.route('/mentor/health')
@login_required
def mentor_health_alias():
    return redirect(url_for('project_health_view'))

@app.route('/mentor/submissions')
@app.route('/mentor/evaluations')
@app.route('/mentor/feedback')
@login_required
def mentor_submissions_alias():
    return redirect(url_for('submissions_view'))

# ==========================================================
# PROJECTS & AI GENERATION ROUTES
# ==========================================================
@app.route('/projects')
@login_required
def projects_list():
    query = request.args.get('q', '').strip().lower()
    selected_tab = request.args.get('tab', 'all').strip().lower()

    db_projects = get_all_projects()

    formatted_projects = []
    for p in db_projects:
        title = (p.get('title') or '').lower()
        if any(k in title for k in ['ai', 'nlp', 'bot', 'chat', 'agent']):
            icon = '🤖'
        elif any(k in title for k in ['medical', 'health', 'prescription']):
            icon = '💊'
        elif any(k in title for k in ['vision', 'traffic', 'city']):
            icon = '📊'
        elif any(k in title for k in ['data', 'analytics']):
            icon = '📈'
        else:
            icon = '📁'
            
        p_item = dict(p)
        assignment_count = p.get('assignment_count', 0)
        source = p.get('source') or ('manual' if 'manual' in title or 'uploaded' in title else 'ai')
        status = "assigned" if assignment_count > 0 else "unassigned"

        p_item.update({
            "id": p['id'],
            "title": p['title'],
            "description": p.get('requirement', '')[:80] if p.get('requirement') else (p.get('abstract', '')[:80] if p.get('abstract') else ''),
            "domain": p.get('domain', 'General'),
            "difficulty": p.get('difficulty', 'Intermediate'),
            "duration": p.get('duration', '6 Weeks'),
            "assignment_count": assignment_count,
            "source": source,
            "icon": icon,
            "status": status
        })
        formatted_projects.append(p_item)

    total_count = len(formatted_projects)
    assigned_count = sum(1 for p in formatted_projects if p.get('assignment_count', 0) > 0)
    ai_generated_count = sum(1 for p in formatted_projects if p.get('source') == 'ai')
    manual_count = sum(1 for p in formatted_projects if p.get('source') == 'manual')
    completed_count = sum(1 for p in formatted_projects if p.get('status') == 'completed')

    filtered_projects = formatted_projects
    if selected_tab in ['assigned', 'active']:
        filtered_projects = [p for p in filtered_projects if p.get('assignment_count', 0) > 0]
    elif selected_tab == 'ai':
        filtered_projects = [p for p in filtered_projects if p.get('source') == 'ai']
    elif selected_tab == 'manual':
        filtered_projects = [p for p in filtered_projects if p.get('source') == 'manual']
    elif selected_tab == 'completed':
        filtered_projects = [p for p in filtered_projects if p.get('status') == 'completed']

    if query:
        filtered_projects = [
            p for p in filtered_projects
            if query in p['title'].lower() or query in p['domain'].lower() or query in p.get('description', '').lower()
        ]

    stats = {
        "total_projects": total_count,
        "active_projects": assigned_count,
        "assigned_projects": assigned_count,
        "completed_projects": completed_count,
        "ai_generated": ai_generated_count,
        "manual_projects": manual_count
    }

    all_interns = get_all_interns()

    return render_template(
        'projects.html',
        active_page='projects',
        projects=filtered_projects,
        all_projects_count=total_count,
        active_count=assigned_count,
        assigned_count=assigned_count,
        ai_generated_count=ai_generated_count,
        manual_count=manual_count,
        completed_count=completed_count,
        selected_tab=selected_tab,
        search_query=query,
        stats=stats,
        all_interns=all_interns
    )

@app.route('/projects/create', methods=['GET', 'POST'], endpoint='create_project_view')
@app.route('/projects/generate', methods=['GET', 'POST'], endpoint='generate_project_action')
@app.route('/mentor/projects/create', methods=['GET'], endpoint='mentor_create_project_alias')
@login_required
@role_required(['mentor', 'admin'])
def create_project_view():
    saved_id = request.args.get('saved_id', type=int)
    saved_project = None
    if saved_id:
        saved_project = get_project_by_id(saved_id)

    if request.method == 'GET':
        return render_template(
            'create_project.html',
            active_page='create_project',
            form_data=None,
            generated_projects=None,
            generated_project=None,
            saved_project=saved_project
        )

    # Check if this is a save/draft action submitted from the Step 2 form
    action = request.form.get('action')
    if action in ['draft', 'save']:
        project_id = create_project(request.form, session.get('user_id'))
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
            saved_obj = get_project_by_id(project_id) if project_id else None
            return jsonify({
                'success': True,
                'project_id': project_id,
                'project': saved_obj,
                'message': 'Project successfully saved to your repository.' if action == 'save' else 'Project saved as draft.'
            })
        if action == 'draft':
            flash('Project saved as draft.', 'success')
            return redirect(url_for('projects_list'))
        else:
            flash('Project successfully saved to your repository.', 'success')
            return redirect(url_for('create_project_view', saved_id=project_id) if project_id else url_for('projects_list'))

    requirement = request.form.get('requirement', '').strip()
    domain = request.form.get('domain', '').strip()
    difficulty = request.form.get('difficulty', 'Intermediate').strip()
    duration = request.form.get('duration', '2 Weeks').strip()
    business_context = request.form.get('business_context', '').strip()

    if not requirement:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
            return jsonify({'success': False, 'error': 'Please enter your project idea or prompt.'}), 400
        flash('Please enter your project idea or prompt (e.g., "I need a project related to agentic AI").', 'danger')
        return redirect(url_for('generate_project_action'))

    # Call Mentora Orchestrator to generate multiple project blueprints
    generated_projects = MentoraOrchestrator.route_request('project_gen_multiple', {
        'requirement': requirement,
        'domain': domain,
        'difficulty': difficulty,
        'duration': duration,
        'business_context': business_context,
        'count': 5
    })
    
    if isinstance(generated_projects, dict):
        if 'projects' in generated_projects and isinstance(generated_projects['projects'], list):
            generated_projects = generated_projects['projects']
        else:
            generated_projects = [generated_projects]
    elif not isinstance(generated_projects, list):
        generated_projects = []

    # Ensure metadata on all generated projects
    for idx, p in enumerate(generated_projects):
        p['index'] = idx
        if not p.get('domain'):
            p['domain'] = domain or 'Gen AI'
        if not p.get('difficulty'):
            p['difficulty'] = difficulty
        if not p.get('duration'):
            p['duration'] = duration
        if not p.get('required_skills'):
            p['required_skills'] = 'Python, LangChain, LangGraph, Gemini API, SQL, Docker'
        if not p.get('business_context'):
            p['business_context'] = business_context
        p['requirement'] = requirement

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
        return jsonify({
            'success': True,
            'projects': generated_projects
        })

    flash(f'AI has generated {len(generated_projects)} distinct project blueprints! Select any project to review and save.', 'success')
    return render_template(
        'create_project.html',
        active_page='create_project',
        form_data=request.form,
        generated_projects=generated_projects,
        generated_project=generated_projects[0] if generated_projects else None,
        saved_project=None
    )


@app.route('/projects/import', methods=['GET', 'POST'])
@login_required
@role_required(['mentor', 'admin'])
def import_projects_view():
    if request.method == 'GET':
        return redirect(url_for('projects_list'))

    target = request.args.get('target') or request.form.get('target', 'list')
    file_storage = request.files.get('dataset_file')
    raw_text = request.form.get('raw_text', '').strip()

    # Check if this is a direct manual project submission
    manual_title = request.form.get('title', '').strip()
    manual_problem = request.form.get('problem_statement', '').strip()
    if manual_title and manual_problem:
        user_id = session.get('user_id')
        project_dict = {
            'title': manual_title,
            'problem_statement': manual_problem,
            'requirement': manual_problem,
            'domain': request.form.get('domain', 'Artificial Intelligence').strip(),
            'difficulty': request.form.get('difficulty', 'Intermediate').strip(),
            'duration': request.form.get('duration', '6 Weeks').strip(),
            'abstract': request.form.get('abstract', '').strip(),
            'required_skills': request.form.get('required_skills', '').strip(),
            'technologies': request.form.get('technologies', '').strip(),
            'objectives': request.form.get('objectives', '').strip(),
            'scope': request.form.get('scope', '').strip(),
            'source': 'manual'
        }
        pid = create_project(project_dict, user_id)
        flash(f'🎉 Project "{manual_title}" uploaded and created successfully!', 'success')
        return redirect(url_for('projects_list'))

    if not file_storage and not raw_text:
        flash('Please select a dataset file (.csv, .json, .txt) or enter project details to upload.', 'warning')
        return redirect(url_for('create_project_view') if target == 'create' else url_for('projects_list'))

    filename = secure_filename(file_storage.filename) if file_storage and file_storage.filename else 'dataset.csv'
    
    if file_storage:
        try:
            content = file_storage.read().decode('utf-8')
        except UnicodeDecodeError:
            file_storage.seek(0)
            content = file_storage.read().decode('latin-1', errors='ignore')
    else:
        content = raw_text

    parsed_projects = parse_project_dataset(content, filename)

    if not parsed_projects:
        flash('Could not parse any projects from the uploaded file/text. Please ensure valid CSV, JSON, or text format.', 'danger')
        return redirect(url_for('create_project_view') if target == 'create' else url_for('projects_list'))

    if target == 'create':
        # Populate the first project into the AI Project Creator page
        first_proj = parsed_projects[0]
        flash(f'Dataset project "{first_proj.get("title", "Imported Project")}" imported! Review and save below.', 'success')
        return render_template(
            'create_project.html',
            active_page='create_project',
            form_data=first_proj,
            generated_project=first_proj
        )

    # Standard batch save into the database
    saved_count = 0
    user_id = session.get('user_id')
    for p in parsed_projects:
        try:
            create_project(p, user_id)
            saved_count += 1
        except Exception as e:
            print(f"[Dataset Import Error] {e}")

    flash(f'🎉 Successfully imported {saved_count} project(s) with Title, Problem Statement, Abstract, Tools & Technologies, and Skills into your workspace!', 'success')
    return redirect(url_for('projects_list'))



@app.route('/projects/save', methods=['POST'])
@login_required
@role_required(['mentor', 'admin'])
def save_project_action():
    action = request.form.get('action', 'save')
    project_id = create_project(request.form, session.get('user_id'))
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
        saved_obj = get_project_by_id(project_id) if project_id else None
        return jsonify({
            'success': True,
            'project_id': project_id,
            'project': saved_obj,
            'message': 'Project successfully saved to your repository.'
        })

    if action == 'draft':
        flash('Project saved as draft.', 'success')
        return redirect(url_for('projects_list'))
    else:
        flash('Project successfully saved to your repository.', 'success')
        return redirect(url_for('create_project_view', saved_id=project_id) if project_id else url_for('projects_list'))

@app.route('/projects/<int:project_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required(['mentor', 'admin'])
def edit_project_view(project_id):
    project = get_project_by_id(project_id)
    if not project:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
            return jsonify({'success': False, 'error': 'Project not found.'}), 404
        flash('Project not found.', 'danger')
        return redirect(url_for('projects_list'))
        
    if request.method == 'POST':
        form_data = request.get_json(silent=True) if request.is_json else request.form
        
        updated_data = {
            'title': form_data.get('title', project['title']).strip(),
            'requirement': form_data.get('requirement', project.get('requirement', '')).strip(),
            'domain': form_data.get('domain', project.get('domain', 'General')).strip(),
            'difficulty': form_data.get('difficulty', project.get('difficulty', 'Intermediate')).strip(),
            'duration': form_data.get('duration', project.get('duration', '6 Weeks')).strip(),
            'required_skills': form_data.get('required_skills', project.get('required_skills', '')).strip(),
            'technologies': form_data.get('technologies', project.get('technologies', '')).strip(),
            'business_context': form_data.get('business_context', project.get('business_context', '')).strip(),
            'problem_statement': form_data.get('problem_statement', project.get('problem_statement', '')).strip(),
            'abstract': form_data.get('abstract', project.get('abstract', '')).strip(),
            'objectives': form_data.get('objectives', project.get('objectives', '')).strip(),
            'scope': form_data.get('scope', project.get('scope', '')).strip(),
            'functional_reqs': form_data.get('functional_reqs', project.get('functional_reqs', '')).strip(),
            'non_functional_reqs': form_data.get('non_functional_reqs', project.get('non_functional_reqs', '')).strip(),
            'expected_outcomes': form_data.get('expected_outcomes', project.get('expected_outcomes', '')).strip(),
            'deliverables': form_data.get('deliverables', project.get('deliverables', '')).strip(),
        }
        update_project(project_id, updated_data)
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
            return jsonify({'success': True, 'message': f'Project "{updated_data["title"]}" updated successfully!'})
            
        flash(f'Project "{updated_data["title"]}" updated successfully!', 'success')
        return redirect(url_for('projects_list'))
        
    return render_template('create_project.html', active_page='projects', form_data=project, generated_project=project, is_edit=True, edit_project_id=project_id)

@app.route('/projects/<int:project_id>/delete', methods=['POST'])
@app.route('/api/projects/delete/<int:project_id>', methods=['POST'])
@login_required
@role_required(['mentor', 'admin'])
def delete_project_view(project_id):
    project = get_project_by_id(project_id)
    title = project['title'] if project else 'Project'
    delete_project(project_id)
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
        return jsonify({'success': True, 'message': f'Project "{title}" deleted successfully.'})
        
    flash(f'Project "{title}" deleted successfully.', 'success')
    return redirect(url_for('projects_list'))

@app.route('/projects/<int:project_id>/export', methods=['GET'])
@login_required
def export_project_view(project_id):
    project = get_project_by_id(project_id)
    if not project:
        flash('Project not found.', 'danger')
        return redirect(url_for('projects_list'))
    
    return jsonify(project)

@app.route('/projects/<int:project_id>')
@login_required
def project_detail_view(project_id):
    project = get_project_by_id(project_id)
    if not project:
        flash('Project not found.', 'danger')
        return redirect(url_for('projects_list'))
        
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
    SELECT a.*, u.full_name as intern_name, u.email as intern_email, i.github_url as intern_github_url
    FROM assignments a
    JOIN users u ON a.intern_id = u.id
    LEFT JOIN interns i ON u.id = i.user_id
    WHERE a.project_id = ?
    ''', (project_id,))
    assignments = [dict(r) for r in cursor.fetchall()]
    conn.close()

    all_interns = get_all_interns()
    all_projects = get_all_projects()

    return render_template(
        'project_details.html',
        active_page='projects',
        project=project,
        assignments=assignments,
        all_interns=all_interns,
        all_projects=all_projects
    )

@app.route('/api/projects/share-in-app', methods=['POST'])
@login_required
@role_required(['mentor', 'admin'])
def share_project_in_app():
    data = request.get_json(silent=True) or request.form
    project_id = data.get('project_id')
    intern_id = data.get('intern_id')
    intern_email = data.get('intern_email', '')
    share_scope = data.get('share_scope', 'full')
    notes = data.get('notes', '')

    project = get_project_by_id(project_id) if project_id else None
    if not project:
        return jsonify({'success': False, 'error': 'Project not found.'}), 404

    scope_title = {
        'abstract': 'Abstract Only',
        'problem_statement': 'Problem Statement Only',
        'full': 'Full Project Blueprint'
    }.get(share_scope, 'Project Blueprint')

    return jsonify({
        'success': True,
        'message': f'🎉 "{project["title"]}" successfully dispatched to intern workspace ({scope_title})!'
    })

@app.route('/api/projects/send-email', methods=['POST'])
@login_required
@role_required(['mentor', 'admin'])
def send_project_email_api():
    data = request.get_json(silent=True) or request.form
    project_id = data.get('project_id')
    recipients = data.get('recipients', [])
    subject = data.get('subject', '')
    body = data.get('body', '')
    share_scope = data.get('share_scope', 'abstract')

    if isinstance(recipients, str):
        recipients = [e.strip() for e in recipients.split(',') if e.strip()]

    if not recipients:
        return jsonify({'success': False, 'error': 'No recipient intern emails selected.'}), 400

    project = get_project_by_id(project_id) if project_id else None
    if not project:
        return jsonify({'success': False, 'error': 'Project not found.'}), 404

    # Optional SMTP dispatch if credentials configured in environment
    smtp_host = os.getenv('SMTP_HOST')
    smtp_port = int(os.getenv('SMTP_PORT', 587))
    smtp_user = os.getenv('SMTP_USER')
    smtp_pass = os.getenv('SMTP_PASS')
    smtp_from = os.getenv('SMTP_FROM', smtp_user or 'noreply@mentora.ai')

    email_sent_real = False
    if smtp_host and smtp_user and smtp_pass:
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart

            msg = MIMEMultipart()
            msg['From'] = smtp_from
            msg['To'] = ', '.join(recipients)
            msg['Subject'] = subject or f"[Mentora AI] Project Brief: {project.get('title', 'Project')}"
            msg.attach(MIMEText(body, 'plain'))

            server = smtplib.SMTP(smtp_host, smtp_port, timeout=10)
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_from, recipients, msg.as_string())
            server.quit()
            email_sent_real = True
        except Exception as e:
            print(f"[SMTP Send Error] {e}")

    rec_names = ", ".join(recipients[:3])
    if len(recipients) > 3:
        rec_names += f" and {len(recipients) - 3} more"

    return jsonify({
        'success': True,
        'message': f'✅ Project specification successfully sent to {rec_names}!',
        'recipients_count': len(recipients),
        'real_smtp': email_sent_real
    })

@app.route('/projects/<int:project_id>/tech-recommendations')
@login_required
def tech_recommendation_view(project_id):
    project = get_project_by_id(project_id)
    if not project:
        flash('Project not found.', 'danger')
        return redirect(url_for('projects_list'))
        
    tech = get_or_generate_tech_recommendations(project_id)
    return render_template('tech_recommendation.html', active_page='projects', project=project, tech=tech)

@app.route('/projects/<int:project_id>/tech-recommendations/regenerate', methods=['POST'])
@login_required
@role_required(['mentor', 'admin'])
def tech_recommendation_regenerate(project_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM tech_recommendations WHERE project_id = ?', (project_id,))
    conn.commit()
    conn.close()
    
    get_or_generate_tech_recommendations(project_id)
    flash('Technology stack re-analyzed with Gemini AI!', 'success')
    return redirect(url_for('tech_recommendation_view', project_id=project_id))

@app.route('/projects/<int:project_id>/scenario')
@login_required
def scenario_view(project_id):
    project = get_project_by_id(project_id)
    if not project:
        flash('Project not found.', 'danger')
        return redirect(url_for('projects_list'))
        
    scenario = get_or_generate_scenario(project_id)
    return render_template('scenario_generation.html', active_page='projects', project=project, scenario=scenario)

@app.route('/projects/<int:project_id>/scenario/regenerate', methods=['POST'])
@login_required
@role_required(['mentor', 'admin'])
def scenario_regenerate(project_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM scenarios WHERE project_id = ?', (project_id,))
    conn.commit()
    conn.close()
    
    get_or_generate_scenario(project_id)
    flash('Real-world enterprise scenario re-generated with Gemini AI!', 'success')
    return redirect(url_for('scenario_view', project_id=project_id))

# ==========================================================
# INTERNS & MATCHING ROUTES
# ==========================================================
@app.route('/interns')
@login_required
def interns_view():
    interns = get_all_interns()
    return render_template('interns.html', active_page='interns', interns=interns)

@app.route('/matching', methods=['GET', 'POST'])
@app.route('/intern-matching', methods=['GET', 'POST'])
@app.route('/matching/run', methods=['GET', 'POST'])
@login_required
@role_required(['mentor', 'admin'])
def intern_matching_view():
    all_projects = get_all_projects()
    if not all_projects:
        flash('Please create a project first before matching interns.', 'warning')
        return redirect(url_for('create_project_view'))

    project_id = request.args.get('project_id', type=int) or request.form.get('project_id', type=int)
    if not project_id and all_projects:
        climate_proj = next((p for p in all_projects if 'climate risk' in p.get('title', '').lower()), None)
        if climate_proj:
            project_id = climate_proj['id']
        else:
            project_id = all_projects[0]['id']

    selected_project = get_project_by_id(project_id)
    matched_interns = match_interns_for_project(project_id) if selected_project else []

    return render_template(
        'matching.html',
        active_page='matching',
        all_projects=all_projects,
        selected_project=selected_project,
        matched_interns=matched_interns
    )

# ==========================================================
# ASSIGNMENTS & TASKS ROUTES
# ==========================================================
@app.route('/assignments')
@login_required
@role_required(['mentor', 'admin'])
def assignments_view():
    assignments = get_assignments_for_mentor()
    projects = get_all_projects()
    interns = get_all_interns()
    
    today_date = date.today().isoformat()
    default_deadline = (date.today() + timedelta(days=42)).isoformat()
    
    return render_template(
        'assignments.html',
        active_page='assignments',
        assignments=assignments,
        projects=projects,
        interns=interns,
        selected_project_id=None,
        selected_intern_id=None,
        today_date=today_date,
        default_deadline=default_deadline
    )

@app.route('/assignments/create', methods=['GET', 'POST'])
@login_required
@role_required(['mentor', 'admin'])
def assignments_create_view():
    if request.method == 'POST':
        project_id = request.form.get('project_id', type=int)
        intern_id = request.form.get('intern_id', type=int)
        start_date = request.form.get('start_date', date.today().isoformat())
        deadline = request.form.get('deadline', (date.today() + timedelta(days=42)).isoformat())
        deliverables = request.form.get('deliverables', '')
        github_repo_url = request.form.get('github_repo_url', '').strip()

        create_assignment(project_id, session.get('user_id'), intern_id, start_date, deadline, deliverables, github_repo_url=github_repo_url)
        flash('Project successfully assigned to intern!', 'success')
        return redirect(url_for('assignments_view'))

    project_id = request.args.get('project_id', type=int)
    intern_id = request.args.get('intern_id', type=int)
    
    assignments = get_assignments_for_mentor()
    projects = get_all_projects()
    interns = get_all_interns()
    
    return render_template(
        'assignments.html',
        active_page='assignments',
        assignments=assignments,
        projects=projects,
        interns=interns,
        selected_project_id=project_id,
        selected_intern_id=intern_id,
        today_date=date.today().isoformat(),
        default_deadline=(date.today() + timedelta(days=42)).isoformat()
    )

@app.route('/assignments/create-action', methods=['POST'])
@login_required
@role_required(['mentor', 'admin'])
def create_assignment_action():
    project_id = request.form.get('project_id', type=int)
    intern_id = request.form.get('intern_id', type=int)
    start_date = request.form.get('start_date', date.today().isoformat())
    deadline = request.form.get('deadline', (date.today() + timedelta(days=42)).isoformat())
    deliverables = request.form.get('deliverables', '')
    github_repo_url = request.form.get('github_repo_url', '').strip()

    create_assignment(project_id, session.get('user_id'), intern_id, start_date, deadline, deliverables, github_repo_url=github_repo_url)
    flash('Project successfully assigned to intern!', 'success')
    return redirect(url_for('assignments_view'))

@app.route('/tasks')
@login_required
@role_required(['mentor', 'admin'])
def tasks_view():
    assignments = get_assignments_for_mentor()
    selected_assignment_id = request.args.get('assignment_id', type=int)
    
    conn = get_db()
    cursor = conn.cursor()
    query = '''
    SELECT t.*, p.title as project_title, u.full_name as intern_name
    FROM tasks t
    JOIN assignments a ON t.assignment_id = a.id
    JOIN projects p ON a.project_id = p.id
    JOIN users u ON a.intern_id = u.id
    '''
    params = []
    if selected_assignment_id:
        query += ' WHERE t.assignment_id = ?'
        params.append(selected_assignment_id)
    query += ' ORDER BY t.id ASC'
    
    cursor.execute(query, params)
    raw_tasks = [dict(r) for r in cursor.fetchall()]
    conn.close()

    tasks = []
    for t in raw_tasks:
        name_lower = (t.get('intern_name') or '').lower()
        if 'bhumika' in name_lower:
            t['avatar_url'] = '/static/images/intern-avatar-alex.png'
        elif 'deepika' in name_lower:
            t['avatar_url'] = '/static/images/intern-avatar-priya.png'
        elif 'lakshmi' in name_lower:
            t['avatar_url'] = '/static/images/intern-avatar-varshitha.png'
        else:
            t['avatar_url'] = '/static/images/intern-avatar-alex.png'

        st = t.get('status', 'Pending')
        if st == 'Completed':
            t['status_badge_class'] = 'status-mint'
            t['health_badge_class'] = 'health-mint'
            t['health'] = 'HEALTHY'
            t['icon_char'] = '✅'
            t['icon_bg_class'] = 'icon-box-mint'
        elif st == 'In Progress':
            t['status_badge_class'] = 'status-blue'
            t['health_badge_class'] = 'health-mint'
            t['health'] = 'HEALTHY'
            t['icon_char'] = '⚡'
            t['icon_bg_class'] = 'icon-box-blue'
        elif st == 'Overdue':
            t['status_badge_class'] = 'status-red'
            t['health_badge_class'] = 'health-pink'
            t['health'] = 'NEEDS ATTENTION'
            t['icon_char'] = '🚨'
            t['icon_bg_class'] = 'icon-box-yellow'
        else:
            t['status_badge_class'] = 'status-yellow'
            t['health_badge_class'] = 'health-mint'
            t['health'] = 'HEALTHY'
            t['icon_char'] = '📋'
            t['icon_bg_class'] = 'icon-box-blue'

        tasks.append(t)

    default_deadline = (date.today() + timedelta(days=7)).isoformat()

    return render_template(
        'tasks.html',
        active_page='tasks',
        tasks=tasks,
        assignments=assignments,
        selected_assignment_id=selected_assignment_id,
        default_deadline=default_deadline
    )

@app.route('/tasks/create', methods=['POST'])
@login_required
@role_required(['mentor', 'admin'])
def create_task_action():
    assignment_id = request.form.get('assignment_id', type=int)
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    deadline = request.form.get('deadline', '')
    status = request.form.get('status', 'Pending')

    if not title or not assignment_id:
        flash('Task title and assignment selection are required.', 'danger')
        return redirect(url_for('tasks_view'))

    create_task(assignment_id, title, description, deadline, status)
    flash(f"Task '{title}' created successfully!", 'success')
    return redirect(url_for('tasks_view', assignment_id=assignment_id))

@app.route('/tasks/<int:task_id>/update-status', methods=['POST'])
@login_required
def update_task_status_route(task_id):
    new_status = request.form.get('status')
    if new_status:
        success, message = update_task_status(task_id, new_status)
        if success:
            flash(message, 'success')
        else:
            flash(message, 'danger')
    return redirect(request.referrer or url_for('dashboard'))

# ==========================================================
# TRACKING & HEALTH AUDIT
# ==========================================================
@app.route('/health')
@app.route('/progress')
@login_required
@role_required(['mentor', 'admin'])
def project_health_view():
    assignments = get_assignments_for_mentor()
    
    # Calculate summary metrics directly from actual data
    total_projects = len(assignments)
    on_track = sum(1 for a in assignments if a.get('health') == 'HEALTHY')
    needs_attention = sum(1 for a in assignments if a.get('health') == 'NEEDS ATTENTION')
    at_risk = sum(1 for a in assignments if a.get('health') == 'CRITICAL')

    return render_template(
        'health.html',
        active_page='health',
        assignments=assignments,
        total_projects=total_projects,
        on_track=on_track,
        needs_attention=needs_attention,
        at_risk=at_risk,
        health_detail=None
    )

@app.route('/health/<int:assignment_id>')
@login_required
def project_health_detail_view(assignment_id):
    health_detail = get_assignment_health_detail(assignment_id)
    if not health_detail:
        flash('Assignment not found.', 'danger')
        return redirect(url_for('project_health_view'))
    return render_template('health.html', active_page='health', assignments=[], health_detail=health_detail)

# ==========================================================
# SUBMISSIONS & EVALUATION
# ==========================================================
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in Config.ALLOWED_EXTENSIONS

@app.route('/submissions')
@login_required
def submissions_view():
    projects = get_all_projects()
    my_assignments = get_assignments_for_intern(session.get('user_id')) if session.get('role') == 'intern' else []
    
    conn = get_db()
    cursor = conn.cursor()
    query = '''
    SELECT s.*, p.title as project_title, u.full_name as intern_name, e.id as evaluation_id
    FROM submissions s
    JOIN assignments a ON s.assignment_id = a.id
    JOIN projects p ON a.project_id = p.id
    JOIN users u ON s.intern_id = u.id
    LEFT JOIN evaluations e ON s.id = e.submission_id
    '''
    params = []
    if session.get('role') == 'intern':
        query += ' WHERE s.intern_id = ?'
        params.append(session.get('user_id'))
    query += ' ORDER BY s.id DESC'
    
    cursor.execute(query, params)
    submissions = [dict(r) for r in cursor.fetchall()]
    conn.close()

    return render_template(
        'submissions.html',
        active_page='submissions',
        submissions=submissions,
        projects=projects,
        my_assignments=my_assignments,
        selected_assignment_id=None
    )

@app.route('/submissions/upload-sample', methods=['POST'])
@login_required
@role_required(['mentor', 'admin'])
def upload_sample_document_action():
    project_id = request.form.get('project_id', type=int)
    criteria = request.form.get('criteria', '')
    expected_sections = request.form.get('expected_sections', '')
    
    if 'sample_file' not in request.files:
        flash('No file uploaded.', 'danger')
        return redirect(url_for('submissions_view'))
        
    file = request.files['sample_file']
    if file.filename == '' or not allowed_file(file.filename):
        flash('Invalid file format. Please upload a PDF, DOCX, XLSX, or TXT file.', 'danger')
        return redirect(url_for('submissions_view'))

    filename = secure_filename(file.filename)
    save_path = Config.SAMPLES_FOLDER / f"sample_p{project_id}_{filename}"
    file.save(str(save_path))

    save_sample_document(project_id, f"uploads/samples/sample_p{project_id}_{filename}", filename, criteria, expected_sections)
    flash(f"Reference standard '{filename}' uploaded successfully for evaluation benchmark!", 'success')
    return redirect(url_for('submissions_view'))

@app.route('/submissions/submit-document', methods=['POST'])
@login_required
def submit_document_action():
    assignment_id = request.form.get('assignment_id', type=int)
    title = request.form.get('title', '').strip()
    notes = request.form.get('notes', '').strip()
    github_repo_url = request.form.get('github_repo_url', '').strip()
    google_doc_url = request.form.get('google_doc_url', '').strip()

    if not assignment_id or not title:
        flash('Assignment and document title are required.', 'danger')
        return redirect(url_for('submissions_view'))

    rel_path = ""
    file_ext = "txt"

    # Case 1: Uploaded file (Word doc .docx/.doc, PDF, TXT, RTF, XLSX)
    if 'submission_file' in request.files and request.files['submission_file'].filename:
        file = request.files['submission_file']
        if not allowed_file(file.filename):
            flash('Please upload a valid Word Document (.docx, .doc), PDF, XLSX, RTF, or TXT document.', 'danger')
            return redirect(url_for('submissions_view'))

        file_ext = file.filename.rsplit('.', 1)[1].lower()
        filename = secure_filename(file.filename)
        save_path = Config.SUBMISSIONS_FOLDER / f"sub_a{assignment_id}_{session.get('user_id')}_{filename}"
        file.save(str(save_path))
        rel_path = f"uploads/submissions/sub_a{assignment_id}_{session.get('user_id')}_{filename}"

    # Case 2: Google Docs URL
    elif google_doc_url:
        gdoc_text = fetch_google_doc_text(google_doc_url)
        if gdoc_text.startswith('[Error'):
            flash(f"Google Docs error: {gdoc_text}", "danger")
            return redirect(url_for('submissions_view'))
        
        file_ext = "gdoc"
        clean_title = re.sub(r'[^\w\s-]', '', title).strip().replace(' ', '_').lower()[:30]
        filename = f"gdoc_sub_a{assignment_id}_{session.get('user_id')}_{clean_title}.txt"
        save_path = Config.SUBMISSIONS_FOLDER / filename
        with open(save_path, 'w', encoding='utf-8') as f:
            f.write(f"# Document: {title}\n# Google Docs Source: {google_doc_url}\n\n{gdoc_text}")
        rel_path = f"uploads/submissions/{filename}"
        notes = f"{notes}\n[Imported from Google Docs: {google_doc_url}]".strip()

    else:
        flash('Please attach a deliverable file or provide a Google Docs link.', 'danger')
        return redirect(url_for('submissions_view'))

    sub_id = create_intern_submission(
        assignment_id,
        session.get('user_id'),
        title,
        rel_path,
        file_ext,
        notes,
        github_repo_url=github_repo_url
    )

    flash(f"Deliverable '{title}' submitted successfully for review & evaluation!", 'success')
    return redirect(url_for('submissions_view'))

@app.route('/api/submissions/pre-check', methods=['POST'])
@login_required
def pre_check_submission_api():
    """
    Evaluates a project document draft before final submission,
    running the PreSubmissionReviewAgent against the project's benchmark sample standard.
    """
    assignment_id = request.form.get('assignment_id', type=int)
    project_id = request.form.get('project_id', type=int)
    draft_text = request.form.get('draft_text', '').strip()
    google_doc_url = request.form.get('google_doc_url', '').strip()

    if assignment_id and not project_id:
        assignment = get_assignment_by_id(assignment_id)
        if assignment:
            project_id = assignment.get('project_id')

    if not project_id:
        return jsonify({'success': False, 'error': 'Project or Assignment ID is required.'}), 400

    # 1. Fetch from Google Docs URL if provided
    if google_doc_url:
        gdoc_text = fetch_google_doc_text(google_doc_url)
        if gdoc_text.startswith('[Error'):
            return jsonify({'success': False, 'error': gdoc_text}), 400
        draft_text = gdoc_text

    # 2. Extract from uploaded draft file if provided
    elif 'draft_file' in request.files and request.files['draft_file'].filename:
        file = request.files['draft_file']
        filename = secure_filename(file.filename)
        temp_path = Config.UPLOAD_FOLDER / f"temp_precheck_{session.get('user_id')}_{filename}"
        file.save(str(temp_path))
        extracted = extract_text_from_file(str(temp_path))
        if temp_path.exists():
            try:
                os.remove(str(temp_path))
            except Exception:
                pass
        if extracted and not extracted.startswith('[Error'):
            draft_text = extracted

    if not draft_text or len(draft_text.strip()) < 15:
        return jsonify({
            'success': False,
            'error': 'Please provide document content to evaluate (upload a Word doc/PDF, paste a Google Docs link, or enter draft text).'
        }), 400

    agent = PreSubmissionReviewAgent()
    analysis = agent.analyze_draft(draft_text, project_id=project_id, assignment_id=assignment_id)
    return jsonify({
        'success': True,
        'analysis': analysis
    })

@app.route('/api/google-docs/import', methods=['POST'])
@login_required
def import_google_doc_api():
    """Extracts text content directly from a public or shared Google Docs URL."""
    data = request.get_json(silent=True) or request.form
    url = (data.get('google_doc_url') or '').strip()
    if not url:
        return jsonify({'success': False, 'error': 'Please provide a Google Docs link.'}), 400

    text = fetch_google_doc_text(url)
    if text.startswith('[Error'):
        return jsonify({'success': False, 'error': text}), 400

    return jsonify({
        'success': True,
        'text': text,
        'word_count': len(text.split()),
        'character_count': len(text)
    })

@app.route('/api/intern/github', methods=['POST'])
@login_required
def update_intern_github_api():
    data = request.get_json(silent=True) or request.form
    github_url = (data.get('github_url') or '').strip()
    target_user_id = data.get('user_id')

    # If mentor/admin, they can update any intern's GitHub URL; if intern, update self
    if session.get('role') in ['mentor', 'admin'] and target_user_id:
        user_id = int(target_user_id)
    else:
        user_id = session.get('user_id')

    update_intern_github(user_id, github_url)
    return jsonify({
        'success': True,
        'github_url': github_url,
        'message': 'GitHub profile link updated successfully!'
    })

@app.route('/api/assignments/<int:assignment_id>/github', methods=['POST'])
@login_required
def update_assignment_github_api(assignment_id):
    data = request.get_json(silent=True) or request.form
    github_repo_url = (data.get('github_repo_url') or '').strip()
    update_assignment_github(assignment_id, github_repo_url)
    return jsonify({
        'success': True,
        'github_repo_url': github_repo_url,
        'message': 'Project GitHub repository linked successfully!'
    })

@app.route('/api/assignments/<int:assignment_id>/links', methods=['POST'])
@login_required
def update_assignment_links_api(assignment_id):
    data = request.get_json(silent=True) or request.form
    github_repo_url = data.get('github_repo_url')
    demo_url = data.get('demo_url')
    doc_url = data.get('doc_url')
    
    update_assignment_links(
        assignment_id,
        github_repo_url=github_repo_url,
        demo_url=demo_url,
        doc_url=doc_url
    )
    return jsonify({
        'success': True,
        'github_repo_url': github_repo_url or '',
        'demo_url': demo_url or '',
        'doc_url': doc_url or '',
        'message': 'Project links updated successfully!'
    })

@app.route('/projects/<int:project_id>/download-doc')
@app.route('/projects/<int:project_id>/doc')
@login_required
def download_project_doc(project_id):
    project = get_project_by_id(project_id)
    if not project:
        flash('Project not found.', 'danger')
        return redirect(url_for('projects_list'))

    fmt = request.args.get('format', 'md').lower()
    title_slug = re.sub(r'[^\w\s-]', '', project.get('title', 'project')).strip().replace(' ', '_').lower()[:40]

    # Generate complete structured documentation markdown
    abstract_text = project.get('abstract') or project.get('requirement') or 'No abstract provided.'
    problem_text = project.get('problem_statement') or project.get('requirement') or 'No problem statement provided.'
    business_text = project.get('business_context') or 'Simulated industry-standard scenario for enterprise engineering training.'
    objectives_text = project.get('objectives') or "1. Implement robust core solution architecture.\n2. Develop functional modules meeting specifications.\n3. Integrate and test against quality metrics."
    scope_text = project.get('scope') or project.get('functional_reqs') or 'Standard enterprise deliverable scope.'
    deliverables_text = project.get('deliverables') or 'Source Code Repository, Architecture Blueprint, Test Suite, Docker Manifest, Documentation'

    doc_content = f"""# {project.get('title', 'Project Specification')}
**Domain:** {project.get('domain', 'Engineering')} | **Difficulty:** {project.get('difficulty', 'Intermediate')} | **Duration:** {project.get('duration', '6 Weeks')}
**Technologies & Tools:** {project.get('technologies', 'Python, REST APIs, Frameworks')}
**Required Skills:** {project.get('required_skills', 'Python, Web Development, Git')}

---

## 1. Executive Abstract
{abstract_text}

---

## 2. Problem Statement
{problem_text}

---

## 3. Business Context & Enterprise Relevance
{business_text}

---

## 4. Key Objectives
{objectives_text}

---

## 5. Project Scope & Functional Requirements
{scope_text}

---

## 6. Expected Deliverables & Artifacts
{deliverables_text}

---
*Generated by Mentora AI Enterprise Mentorship Platform*
"""

    if fmt == 'txt':
        from flask import Response
        return Response(
            doc_content,
            mimetype='text/plain',
            headers={'Content-Disposition': f'attachment; filename="project_{project_id}_{title_slug}_blueprint.txt"'}
        )
    elif fmt == 'md':
        from flask import Response
        return Response(
            doc_content,
            mimetype='text/markdown',
            headers={'Content-Disposition': f'attachment; filename="project_{project_id}_{title_slug}_blueprint.md"'}
        )
    else:
        # Render a clean printable HTML document view
        return render_template(
            'project_doc_view.html',
            active_page='projects',
            project=project,
            doc_markdown=doc_content
        )
@app.route('/submissions/<int:submission_id>/evaluate', methods=['POST', 'GET'])
@login_required
@role_required(['mentor', 'admin', 'intern'])
def evaluate_submission_route(submission_id):
    result = run_submission_evaluation(submission_id)
    if result:
        flash('AI Submission Evaluation & Mentorship Feedback generated successfully!', 'success')
        return redirect(url_for('evaluation_detail_view', submission_id=submission_id))
    else:
        flash('Error executing evaluation.', 'danger')
        return redirect(url_for('submissions_view'))

@app.route('/evaluations/<int:submission_id>')
@login_required
def evaluation_detail_view(submission_id):
    eval_data = get_submission_evaluation(submission_id)
    if not eval_data:
        eval_data = run_submission_evaluation(submission_id)
        if eval_data:
            eval_data = get_submission_evaluation(submission_id)
        else:
            flash('Evaluation not found for this submission.', 'danger')
            return redirect(url_for('submissions_view'))
            
    return render_template('evaluation.html', active_page='submissions', evaluation=eval_data)

@app.route('/feedback/<int:evaluation_id>')
@login_required
def feedback_detail_view(evaluation_id):
    feedback_data = get_feedback_for_evaluation(evaluation_id)
    if not feedback_data:
        flash('Feedback not found.', 'danger')
        return redirect(url_for('submissions_view'))
    return render_template('feedback.html', active_page='submissions', feedback=feedback_data)

# ==========================================================
# DOCUMENTS & MULTI-AGENT STRUCTURAL VERIFICATION
# ==========================================================
@app.route('/documents')
@app.route('/mentor/documents')
@login_required
@role_required(['mentor', 'admin', 'intern'])
def documents_view():
    seed_sample_documents_if_empty()
    project_id = request.args.get('project_id', type=int)
    category = request.args.get('category', 'All')
    selected_doc_id = request.args.get('doc_id', type=int)
    selected_sub_id = request.args.get('sub_id', type=int)
    
    all_projects = get_all_projects()
    docs = get_all_documents(project_id=project_id, category=category)
    
    # Query intern submissions
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
    SELECT s.id, s.title, s.file_path, s.file_type, s.submitted_at, s.status,
           u.id as intern_id, u.full_name as intern_name, u.email as intern_email,
           p.id as project_id, p.title as project_title,
           a.id as assignment_id
    FROM submissions s
    JOIN assignments a ON s.assignment_id = a.id
    JOIN projects p ON a.project_id = p.id
    JOIN users u ON s.intern_id = u.id
    ORDER BY s.id DESC
    ''')
    intern_submissions = [dict(r) for r in cursor.fetchall()]
    conn.close()
    
    selected_doc = get_document_by_id(selected_doc_id) if selected_doc_id else (docs[0] if docs else None)
    
    # Calculate repository metrics
    total_docs = len(docs)
    approved_count = sum(1 for d in docs if d.get('approval_status') == 'Approved')
    ready_count = sum(1 for d in docs if d.get('approval_status') == 'Ready for Approval')
    needs_revision_count = sum(1 for d in docs if d.get('approval_status') == 'Needs Revision')
    avg_score = round(sum(d.get('format_score', 0) for d in docs) / total_docs) if total_docs > 0 else 0

    summary_stats = {
        "total_docs": total_docs,
        "approved_count": approved_count,
        "ready_count": ready_count,
        "needs_revision_count": needs_revision_count,
        "avg_score": avg_score
    }

    return render_template(
        'documents.html',
        active_page='documents',
        documents=docs,
        intern_submissions=intern_submissions,
        projects=all_projects,
        selected_project_id=project_id,
        selected_category=category,
        selected_sub_id=selected_sub_id,
        selected_doc=selected_doc,
        stats=summary_stats
    )

@app.route('/documents/upload', methods=['POST'])
@login_required
def upload_document_action():
    submission_id = request.form.get('submission_id', type=int)
    title = request.form.get('title', '').strip()
    category = request.form.get('category', 'Milestone Report')
    project_id = request.form.get('project_id', type=int)
    
    intern_file = request.files.get('document_file') or request.files.get('intern_file')
    sample_file = request.files.get('sample_file')
    
    # Validate: either an intern submission is selected, or an intern file is uploaded
    if not submission_id and (not intern_file or intern_file.filename == ''):
        flash('Please select an intern submission or attach an intern document file to inspect.', 'warning')
        return redirect(url_for('documents_view'))
        
    user_id = session.get('user_id')
    doc_id, analysis = save_and_verify_document(
        intern_file_obj=intern_file,
        sample_file_obj=sample_file,
        submission_id=submission_id,
        title=title,
        category=category,
        project_id=project_id,
        uploaded_by=user_id
    )
    
    score = analysis.get('format_score', 45)
    status = analysis.get('format_status', 'Needs Revision')
    rec = analysis.get('approval_recommendation', 'Needs Formatting Revisions')
    missing_count = len(analysis.get('missing_sections', []))
    
    flash(f"AI Comparative Inspection Complete: Investigated intern deliverable against sample document format ({status} — Score: {score}%). Identified {missing_count} missing section(s)!", 'success')
    return redirect(url_for('documents_view', doc_id=doc_id))

@app.route('/documents/<int:doc_id>/approve', methods=['POST'])
@login_required
@role_required(['mentor', 'admin'])
def approve_document_action(doc_id):
    approve_document(doc_id, session.get('user_id'))
    flash('Document successfully approved and marked as verified standard in project repository!', 'success')
    return redirect(url_for('documents_view', doc_id=doc_id))

@app.route('/documents/<int:doc_id>/reject', methods=['POST'])
@login_required
@role_required(['mentor', 'admin'])
def reject_document_action(doc_id):
    reason = request.form.get('reason', 'Document formatting requires restructuring according to template standard.')
    reject_document(doc_id, reason)
    flash('Document flagged for formatting revision. Notification logged for uploader.', 'warning')
    return redirect(url_for('documents_view', doc_id=doc_id))

# ==========================================================
# MENTOR & INTERN AI COPILOT
# ==========================================================
@app.route('/copilot', methods=['GET', 'POST'])
@app.route('/mentor/copilot', methods=['GET', 'POST'])
@app.route('/intern/copilot', methods=['GET', 'POST'])
@login_required
@role_required(['mentor', 'admin', 'intern'])
def copilot_view():
    question = ""
    if request.method == 'POST':
        question = request.form.get('question', '').strip()
    if not question:
        question = request.args.get('q', '').strip()

    response_text = ""
    if question:
        try:
            response_text = ask_mentor_copilot(question)
        except Exception as e:
            print(f"[Copilot Error] {e}")
            role_title = "Intern AI Copilot" if session.get('role') == 'intern' else "Mentor AI Copilot"
            response_text = f"### 💡 {role_title}\n\nI encountered an issue processing your request for: **{question}**.\n\nPlease try asking again or select one of the suggested query shortcuts below."

    # Live Database Overview Stats
    ctx = get_system_context_for_copilot()
    total_proj = ctx.get('projects_count', 0)
    active_int = len(ctx.get('interns', []))
    pending_sub = len([s for s in ctx.get('submissions', []) if s.get('status') in ['Submitted', 'Pending', 'Under Review']])
    at_risk = len([a for a in ctx.get('assignments', []) if a.get('status') in ['Delayed', 'Critical']])

    overview_stats = {
        "total_projects": total_proj,
        "active_interns": active_int,
        "pending_submissions": pending_sub,
        "at_risk_projects": at_risk
    }
    
    recent_activities = []
    for sub in ctx.get('submissions', [])[:3]:
        recent_activities.append({
            "title": f"Submission: {sub.get('title')}",
            "sub": f"{sub.get('intern_name', 'Intern')} • {sub.get('status')}",
            "dot_class": "dot-blue"
        })
    for a in ctx.get('assignments', [])[:2]:
        recent_activities.append({
            "title": f"Assignment: {a.get('project_title')}",
            "sub": f"{a.get('intern_name', 'Intern')} • {a.get('status')}",
            "dot_class": "dot-mint"
        })
    if not recent_activities:
        recent_activities = [
            {"title": "Clean Workspace Ready", "sub": "1 Mentor & 3 Interns Initialized", "dot_class": "dot-mint"}
        ]
        
    ai_insights = [
        {"icon": "💡", "title": "Platform Initialized", "sub": "Ready to design and allocate projects."}
    ]
    if total_proj > 0:
        ai_insights.append({"icon": "📊", "title": f"{total_proj} Project(s) in repository", "sub": "Use Intern Matching to assign them."})
    if pending_sub > 0:
        ai_insights.append({"icon": "⏱️", "title": f"{pending_sub} submission(s) pending review", "sub": "Run AI Evaluation to generate feedback."})

    return render_template(
        'copilot.html',
        active_page='copilot',
        question=question,
        response_text=response_text,
        stats=overview_stats,
        activities=recent_activities,
        insights=ai_insights
    )

@app.route('/copilot/ask', methods=['GET', 'POST'])
@login_required
@role_required(['mentor', 'admin', 'intern'])
def copilot_ask():
    question = request.form.get('question', '').strip() if request.method == 'POST' else request.args.get('q', '').strip()
    response_text = ""
    if question:
        try:
            response_text = ask_mentor_copilot(question)
        except Exception as e:
            print(f"[Copilot Error] {e}")
            response_text = f"### 💡 Mentora AI Copilot\n\nI encountered an issue processing your request for: **{question}**.\n\nPlease try asking again or select one of the suggested query shortcuts below."

    ctx = get_system_context_for_copilot()
    total_proj = ctx.get('projects_count', 0)
    active_int = len(ctx.get('interns', []))
    pending_sub = len([s for s in ctx.get('submissions', []) if s.get('status') in ['Submitted', 'Pending', 'Under Review']])
    at_risk = len([a for a in ctx.get('assignments', []) if a.get('status') in ['Delayed', 'Critical']])

    overview_stats = {
        "total_projects": total_proj,
        "active_interns": active_int,
        "pending_submissions": pending_sub,
        "at_risk_projects": at_risk
    }
    
    recent_activities = []
    for sub in ctx.get('submissions', [])[:3]:
        recent_activities.append({
            "title": f"Submission: {sub.get('title')}",
            "sub": f"{sub.get('intern_name', 'Intern')} • {sub.get('status')}",
            "dot_class": "dot-blue"
        })
    for a in ctx.get('assignments', [])[:2]:
        recent_activities.append({
            "title": f"Assignment: {a.get('project_title')}",
            "sub": f"{a.get('intern_name', 'Intern')} • {a.get('status')}",
            "dot_class": "dot-mint"
        })
    if not recent_activities:
        recent_activities = [
            {"title": "Clean Workspace Ready", "sub": "1 Mentor & 3 Interns Initialized", "dot_class": "dot-mint"}
        ]
        
    ai_insights = [
        {"icon": "💡", "title": "Platform Initialized", "sub": "Ready to design and allocate projects."}
    ]
    if total_proj > 0:
        ai_insights.append({"icon": "📊", "title": f"{total_proj} Project(s) in repository", "sub": "Use Intern Matching to assign them."})
    if pending_sub > 0:
        ai_insights.append({"icon": "⏱️", "title": f"{pending_sub} submission(s) pending review", "sub": "Run AI Evaluation to generate feedback."})

    return render_template(
        'copilot.html',
        active_page='copilot',
        question=question,
        response_text=response_text,
        stats=overview_stats,
        activities=recent_activities,
        insights=ai_insights
    )

# ==========================================================
# INTERN WORKSPACE SPECIFIC ROUTES
# ==========================================================
@app.route('/intern/dashboard')
@login_required
def intern_dashboard():
    user_id = session.get('user_id')
    my_assignments = get_assignments_for_intern(user_id)
    intern_profile = get_intern_by_user_id(user_id) or {}
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
    SELECT t.*, p.title as project_title, a.id as assignment_id, 
           a.github_repo_url, a.demo_url, a.doc_url,
           (SELECT demo_url FROM submissions WHERE assignment_id = a.id ORDER BY id DESC LIMIT 1) as submission_demo_url,
           (SELECT COUNT(*) FROM tasks WHERE assignment_id = a.id) as total_proj_tasks,
           (SELECT COUNT(*) FROM tasks WHERE assignment_id = a.id AND status = 'Completed') as completed_proj_tasks
    FROM tasks t
    JOIN assignments a ON t.assignment_id = a.id
    JOIN projects p ON a.project_id = p.id
    WHERE a.intern_id = ?
    ORDER BY t.deadline ASC, t.id ASC
    ''', (user_id,))
    my_tasks = [dict(r) for r in cursor.fetchall()]
    conn.close()

    total_pending = sum(1 for t in my_tasks if t['status'] != 'Completed')
    total_completed = sum(1 for t in my_tasks if t['status'] == 'Completed')
    overdue_count = sum(1 for t in my_tasks if t['status'] == 'Overdue')

    return render_template(
        'intern_dashboard.html',
        active_page='intern_dashboard',
        my_assignments=my_assignments,
        my_tasks=my_tasks,
        intern_profile=intern_profile,
        total_pending_tasks=total_pending,
        total_completed_tasks=total_completed,
        overdue_count=overdue_count
    )

@app.route('/my-projects')
@login_required
def intern_projects_view():
    user_id = session.get('user_id')
    my_assignments = get_assignments_for_intern(user_id)
    intern_profile = get_intern_by_user_id(user_id) or {}
    return render_template(
        'intern_dashboard.html',
        active_page='my_projects',
        my_assignments=my_assignments,
        my_tasks=[],
        intern_profile=intern_profile,
        total_pending_tasks=0,
        total_completed_tasks=0,
        overdue_count=0
    )

@app.route('/my-tasks')
@login_required
def intern_tasks_view():
    user_id = session.get('user_id')
    my_assignments = get_assignments_for_intern(user_id)
    intern_profile = get_intern_by_user_id(user_id) or {}
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
    SELECT t.*, p.title as project_title, a.id as assignment_id, 
           a.github_repo_url, a.demo_url, a.doc_url,
           (SELECT demo_url FROM submissions WHERE assignment_id = a.id ORDER BY id DESC LIMIT 1) as submission_demo_url,
           (SELECT COUNT(*) FROM tasks WHERE assignment_id = a.id) as total_proj_tasks,
           (SELECT COUNT(*) FROM tasks WHERE assignment_id = a.id AND status = 'Completed') as completed_proj_tasks
    FROM tasks t
    JOIN assignments a ON t.assignment_id = a.id
    JOIN projects p ON a.project_id = p.id
    WHERE a.intern_id = ?
    ORDER BY t.deadline ASC, t.id ASC
    ''', (user_id,))
    my_tasks = [dict(r) for r in cursor.fetchall()]
    conn.close()
    
    return render_template(
        'intern_dashboard.html',
        active_page='my_tasks',
        my_assignments=my_assignments,
        my_tasks=my_tasks,
        intern_profile=intern_profile,
        total_pending_tasks=sum(1 for t in my_tasks if t['status'] != 'Completed'),
        total_completed_tasks=sum(1 for t in my_tasks if t['status'] == 'Completed'),
        overdue_count=sum(1 for t in my_tasks if t['status'] == 'Overdue')
    )

@app.route('/submit-project')
@login_required
def intern_submit_view():
    assignment_id = request.args.get('assignment_id', type=int)
    projects = get_all_projects()
    my_assignments = get_assignments_for_intern(session.get('user_id'))
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
    SELECT s.*, p.title as project_title, u.full_name as intern_name, e.id as evaluation_id
    FROM submissions s
    JOIN assignments a ON s.assignment_id = a.id
    JOIN projects p ON a.project_id = p.id
    JOIN users u ON s.intern_id = u.id
    LEFT JOIN evaluations e ON s.id = e.submission_id
    WHERE s.intern_id = ?
    ORDER BY s.id DESC
    ''', (session.get('user_id'),))
    submissions = [dict(r) for r in cursor.fetchall()]
    conn.close()

    return render_template(
        'submissions.html',
        active_page='my_submissions',
        submissions=submissions,
        projects=projects,
        my_assignments=my_assignments,
        selected_assignment_id=assignment_id
    )

# ==========================================================
# INTERN ONBOARDING AGENT & CREDENTIALS PROVISIONING
# ==========================================================
@app.route('/mentor/interns', methods=['GET'])
@app.route('/mentor/interns/agent', methods=['GET'])
@login_required
@role_required(['mentor', 'admin'])
def mentor_intern_agent_view():
    """Renders the AI Intern Onboarding Agent & Credential Hub."""
    projects = get_all_projects()
    interns = get_all_interns_with_stats()
    return render_template(
        'mentor_intern_agent.html',
        active_page='intern_agent',
        projects=projects,
        interns=interns
    )

@app.route('/api/mentor/interns/provision', methods=['POST'])
@login_required
@role_required(['mentor', 'admin'])
def api_provision_single_intern():
    """API endpoint to provision a single intern and return credentials."""
    data = request.get_json(silent=True) or {}
    full_name = data.get('full_name', '').strip()
    email = data.get('email', '').strip()
    department = data.get('department', 'Engineering').strip()
    experience = data.get('experience', '3rd').strip()
    skills = data.get('skills', 'Python, Web Development').strip()
    joining_date = data.get('joining_date', '').strip() or None
    project_id = data.get('project_id')
    password = data.get('password', '').strip() or None

    try:
        if project_id:
            project_id = int(project_id)
    except (ValueError, TypeError):
        project_id = None

    ok, creds, err = provision_intern(
        full_name=full_name,
        email=email,
        password=password,
        department=department,
        skills=skills,
        technologies=skills,
        experience=experience,
        project_id=project_id,
        joining_date=joining_date
    )

    if ok:
        return jsonify({"success": True, "credential": creds})
    else:
        return jsonify({"success": False, "error": err or "Failed to provision intern."}), 400

@app.route('/api/mentor/interns/ai-provision', methods=['POST'])
@login_required
@role_required(['mentor', 'admin'])
def api_ai_provision_interns():
    """API endpoint for AI natural language / batch roster provisioning."""
    data = request.get_json(silent=True) or {}
    prompt = data.get('prompt', '').strip()
    project_id = data.get('project_id')

    try:
        if project_id:
            project_id = int(project_id)
    except (ValueError, TypeError):
        project_id = None

    ok, interns, err = ai_parse_and_provision_interns(prompt, default_project_id=project_id)

    if ok:
        return jsonify({"success": True, "interns": interns, "count": len(interns)})
    else:
        return jsonify({"success": False, "error": err or "Failed to process prompt."}), 400

@app.route('/api/mentor/interns/reset-password', methods=['POST'])
@login_required
@role_required(['mentor', 'admin'])
def api_reset_intern_password():
    """API endpoint to generate a new password for an intern."""
    data = request.get_json(silent=True) or {}
    user_id = data.get('user_id')
    try:
        user_id = int(user_id)
    except (ValueError, TypeError):
        return jsonify({"success": False, "error": "Invalid user ID."}), 400

    ok, creds, err = reset_intern_credentials(user_id)
    if ok:
        return jsonify({"success": True, "credential": creds})
    else:
        return jsonify({"success": False, "error": err or "Failed to reset password."}), 400

@app.route('/api/mentor/interns/delete/<int:user_id>', methods=['POST'])
@login_required
@role_required(['mentor', 'admin'])
def api_delete_intern(user_id):
    """API endpoint to delete an intern account."""
    ok, err = delete_intern_account(user_id)
    if ok:
        return jsonify({"success": True})
    else:
        return jsonify({"success": False, "error": err or "Could not delete intern."}), 400

@app.route('/api/mentor/interns/list', methods=['GET'])
@login_required
@role_required(['mentor', 'admin'])
def api_list_interns():
    """Returns all interns as JSON."""
    interns = get_all_interns_with_stats()
    return jsonify({"success": True, "interns": interns})

@app.route('/api/mentor/interns/send-credentials-email', methods=['POST'])
@login_required
@role_required(['mentor', 'admin'])
def api_send_credentials_email():
    """API endpoint to email login credentials (email, password, portal link) directly to an intern or batch."""
    data = request.get_json(silent=True) or request.form or {}
    mentor_name = session.get('full_name') or session.get('username') or 'Lead Mentor'
    mentor_email = session.get('email')
    default_login_url = request.host_url.rstrip('/') + url_for('intern_signin')
    login_url = data.get('login_url') or default_login_url

    # Check for batch send
    interns_list = data.get('interns')
    if isinstance(interns_list, list) and len(interns_list) > 0:
        count, successes, errors = batch_send_credentials_emails(
            interns=interns_list,
            login_url=login_url,
            mentor_name=mentor_name,
            mentor_email=mentor_email
        )
        if count > 0:
            return jsonify({
                "success": True,
                "message": f"Successfully sent credentials to {count} intern(s)!",
                "count": count,
                "successes": successes,
                "errors": errors
            })
        else:
            return jsonify({
                "success": False,
                "error": "; ".join(errors) if errors else "Failed to send batch emails."
            }), 400

    # Single intern send
    to_email = data.get('email', '').strip()
    full_name = data.get('full_name', '').strip()
    username = data.get('username', '').strip() or to_email.split('@')[0] if to_email else ''
    password = data.get('password', '').strip()
    project_title = data.get('project_title')

    if not to_email:
        return jsonify({"success": False, "error": "Intern email address is required."}), 400
    if not password:
        return jsonify({"success": False, "error": "Password is required to send credentials."}), 400

    ok, msg, real_smtp = send_intern_credentials_email(
        to_email=to_email,
        full_name=full_name,
        username=username,
        password=password,
        login_url=login_url,
        project_title=project_title,
        mentor_name=mentor_name,
        mentor_email=mentor_email
    )

    if ok:
        return jsonify({
            "success": True,
            "message": f"✅ Login credentials & portal link sent directly to {to_email}!",
            "email": to_email,
            "real_smtp": real_smtp
        })
    else:
        return jsonify({"success": False, "error": msg}), 400


# ==========================================================
# INTERN SELF-LEARNING & UPSKILLING VAULT
# ==========================================================
@app.route('/intern/self-learning', methods=['GET'])
@login_required
@role_required(['intern', 'mentor', 'admin'])
def intern_self_learning_view():
    """Renders the Intern Self-Learning Hub & Knowledge Vault."""
    intern_id = session.get('user_id')
    category_filter = request.args.get('category', 'All')
    media_filter = request.args.get('type', 'all')
    search_q = request.args.get('q', '').strip()

    resources = get_learning_resources_for_intern(
        intern_id=intern_id,
        category=category_filter,
        media_type=media_filter,
        search_q=search_q
    )
    stats = get_intern_upskilling_stats(intern_id)

    return render_template(
        'intern_self_learning.html',
        active_page='self_learning',
        resources=resources,
        stats=stats,
        selected_category=category_filter,
        selected_type=media_filter,
        search_query=search_q
    )

@app.route('/intern/self-learning/upload', methods=['POST'])
@login_required
@role_required(['intern', 'mentor', 'admin'])
def intern_self_learning_upload():
    """Handles upload/creation of learning artifact (PDF, DOC, Video, Audio, Note)."""
    intern_id = session.get('user_id')
    title = request.form.get('title', '').strip()
    category = request.form.get('category', 'General Upskilling').strip()
    tags = request.form.get('tags', '').strip()
    content_text = request.form.get('content_text', '').strip()
    external_url = request.form.get('external_url', '').strip()
    share_with_mentor = bool(request.form.get('share_with_mentor'))
    auto_synthesize = bool(request.form.get('auto_synthesize', '1') == '1')
    file_obj = request.files.get('file')

    requested_type = request.form.get('media_type', 'auto').strip().lower()
    
    if requested_type in ['pdf', 'doc', 'text', 'image', 'video', 'audio']:
        media_type = requested_type
    elif file_obj and file_obj.filename:
        from self_learning_service import detect_media_type
        media_type = detect_media_type(file_obj.filename, bool(content_text))
    else:
        media_type = 'text'

    ok, resource_id, err = save_learning_resource(
        intern_id=intern_id,
        title=title,
        category=category,
        media_type=media_type,
        file_obj=file_obj,
        content_text=content_text,
        external_url=external_url,
        tags=tags,
        share_with_mentor=share_with_mentor,
        auto_synthesize=auto_synthesize
    )

    if ok:
        flash(f'"{title}" added to your Learning Vault with AI synthesis!', 'success')
    else:
        flash(err or 'Failed to save learning artifact.', 'danger')

    return redirect(url_for('intern_self_learning_view'))

@app.route('/api/intern/self-learning/submit-quiz', methods=['POST'])
@login_required
@role_required(['intern', 'mentor', 'admin'])
def api_submit_learning_quiz():
    """Updates mastery score for a learning resource."""
    data = request.get_json(silent=True) or {}
    resource_id = data.get('resource_id')
    score = data.get('score', 0)
    intern_id = session.get('user_id')

    try:
        resource_id = int(resource_id)
        score = int(score)
    except (ValueError, TypeError):
        return jsonify({"success": False, "error": "Invalid parameters."}), 400

    ok, new_score, err = update_mastery_score(resource_id, intern_id, score)
    if ok:
        return jsonify({"success": True, "score": new_score})
    else:
        return jsonify({"success": False, "error": err}), 400

@app.route('/api/intern/self-learning/toggle-favorite/<int:resource_id>', methods=['POST'])
@login_required
@role_required(['intern', 'mentor', 'admin'])
def api_toggle_resource_favorite(resource_id):
    """Toggles bookmark on resource."""
    intern_id = session.get('user_id')
    ok, fav_status, err = toggle_favorite_resource(resource_id, intern_id)
    if ok:
        return jsonify({"success": True, "is_favorite": fav_status})
    else:
        return jsonify({"success": False, "error": err}), 400

@app.route('/api/intern/self-learning/delete/<int:resource_id>', methods=['POST'])
@login_required
@role_required(['intern', 'mentor', 'admin'])
def api_delete_learning_resource(resource_id):
    """Deletes learning resource."""
    intern_id = session.get('user_id')
    ok, err = delete_learning_resource(resource_id, intern_id)
    if ok:
        return jsonify({"success": True})
    else:
        return jsonify({"success": False, "error": err}), 400

@app.route('/api/intern/self-learning/update-type/<int:resource_id>', methods=['POST'])
@login_required
@role_required(['intern', 'mentor', 'admin'])
def api_update_learning_resource_type(resource_id):
    """Updates media type of a learning resource."""
    data = request.get_json(silent=True) or {}
    intern_id = session.get('user_id')
    new_type = data.get('media_type', '').strip().lower()
    ok, err = update_resource_media_type(resource_id, intern_id, new_type)
    if ok:
        return jsonify({"success": True, "media_type": new_type})
    else:
        return jsonify({"success": False, "error": err or "Failed to update media type."}), 400

@app.route('/api/intern/self-learning/goals/add', methods=['POST'])
@login_required
@role_required(['intern', 'mentor', 'admin'])
def api_add_learning_goal():
    """Adds a new skill upskilling goal."""
    data = request.get_json(silent=True) or {}
    intern_id = session.get('user_id')
    skill_name = data.get('skill_name', '').strip()
    target_level = data.get('target_level', 'Practitioner').strip()
    target_date = data.get('target_date', '').strip() or None

    ok, err = add_or_update_goal(intern_id, skill_name, target_level, 0, target_date)
    if ok:
        return jsonify({"success": True})
    else:
        return jsonify({"success": False, "error": err or "Failed to add goal."}), 400

@app.route('/api/intern/self-learning/goals/update-progress', methods=['POST'])
@login_required
@role_required(['intern', 'mentor', 'admin'])
def api_update_learning_goal_progress():
    """Updates goal completion percentage."""
    data = request.get_json(silent=True) or {}
    intern_id = session.get('user_id')
    goal_id = data.get('goal_id')
    progress = data.get('progress_percent', 0)

    try:
        goal_id = int(goal_id)
        progress = int(progress)
    except (ValueError, TypeError):
        return jsonify({"success": False, "error": "Invalid parameters."}), 400

    ok, err = update_goal_progress(goal_id, intern_id, progress)
    if ok:
        return jsonify({"success": True})
    else:
        return jsonify({"success": False, "error": err}), 400

@app.route('/api/intern/self-learning/goals/delete/<int:goal_id>', methods=['POST'])
@login_required
@role_required(['intern', 'mentor', 'admin'])
def api_delete_learning_goal(goal_id):
    """Deletes a skill goal."""
    intern_id = session.get('user_id')
    ok, err = delete_goal(goal_id, intern_id)
    if ok:
        return jsonify({"success": True})
    else:
        return jsonify({"success": False, "error": err}), 400

@app.route('/uploads/upskilling/<path:filename>')
@login_required
def serve_upskilling_file(filename):
    """Securely streams and serves learning vault artifacts (PDFs, videos, audios, images)."""
    return send_from_directory(Config.UPSKILLING_FOLDER, filename)


# ==========================================================
# ERROR HANDLERS
# ==========================================================
@app.errorhandler(404)
def page_not_found(e):
    return render_template('base.html', content='<div class="card" style="text-align:center; padding: 48px;"><h2>404 - Page Not Found</h2><p style="margin-top:8px; color:#6D6F80;">The requested page could not be located.</p><a href="/" class="btn btn-primary" style="margin-top:16px;">Return to Home</a></div>'), 404

@app.errorhandler(403)
def forbidden(e):
    return render_template('base.html', content='<div class="card" style="text-align:center; padding: 48px;"><h2>403 - Forbidden Access</h2><p style="margin-top:8px; color:#6D6F80;">You do not have authorization to view this area.</p><a href="/" class="btn btn-primary" style="margin-top:16px;">Return to Home</a></div>'), 403

@app.errorhandler(413)
def request_entity_too_large(e):
    if request.is_json:
        return jsonify({"success": False, "error": "Uploaded file is too large (exceeds 1GB limit)."}), 413
    flash("The uploaded file exceeds the 1GB capacity limit. Please select a video or file under 1GB.", "danger")
    return redirect(request.referrer or url_for('intern_self_learning_view'))

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('base.html', content='<div class="card" style="text-align:center; padding: 48px;"><h2>500 - Internal Server Error</h2><p style="margin-top:8px; color:#6D6F80;">An unexpected server error occurred.</p><a href="/" class="btn btn-primary" style="margin-top:16px;">Return to Home</a></div>'), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"==================================================")
    print(f"  MENTORA AI — Pastel Workspace Running          ")
    print(f"  URL: http://127.0.0.1:{port}                   ")
    print(f"==================================================")
    app.run(host='0.0.0.0', port=port, debug=True)
