from datetime import datetime, date
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'mentor', 'intern', 'admin'
    full_name = db.Column(db.String(150), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    mentor_profile = db.relationship('MentorProfile', backref='user', uselist=False, cascade="all, delete-orphan")
    intern_profile = db.relationship('InternProfile', backref='user', uselist=False, cascade="all, delete-orphan")

class MentorProfile(db.Model):
    __tablename__ = 'mentor_profiles'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, unique=True)
    organization = db.Column(db.String(150), default='Mentora Enterprise')
    department = db.Column(db.String(150), nullable=False)
    specialization = db.Column(db.String(255), nullable=False)
    years_of_experience = db.Column(db.String(50), default='5+ Years')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class InternProfile(db.Model):
    __tablename__ = 'intern_profiles'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, unique=True)
    college = db.Column(db.String(200), default='Institute of Technology')
    course = db.Column(db.String(150), default='Computer Science & Engineering')
    year_of_study = db.Column(db.String(50), default='Final Year')
    skills = db.Column(db.Text, nullable=False)
    technologies = db.Column(db.Text, nullable=False)
    experience = db.Column(db.Text, default='Intermediate (1.5 years academic + project research)')
    workload = db.Column(db.String(50), default='Low')  # 'Low', 'Medium', 'High'
    availability = db.Column(db.String(50), default='Available')
    joining_date = db.Column(db.Date, default=date.today)
    github_url = db.Column(db.String(255), default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Project(db.Model):
    __tablename__ = 'projects'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    requirement = db.Column(db.Text, nullable=False)
    domain = db.Column(db.String(100), nullable=False)
    difficulty = db.Column(db.String(50), nullable=False)
    duration = db.Column(db.String(50), nullable=False)
    required_skills = db.Column(db.Text, nullable=False)
    business_context = db.Column(db.Text)
    problem_statement = db.Column(db.Text)
    abstract = db.Column(db.Text)
    objectives = db.Column(db.Text)
    scope = db.Column(db.Text)
    functional_reqs = db.Column(db.Text)
    non_functional_reqs = db.Column(db.Text)
    expected_outcomes = db.Column(db.Text)
    deliverables = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    tech_recommendations = db.relationship('ProjectTechnology', backref='project', cascade="all, delete-orphan")
    scenarios = db.relationship('ProjectScenario', backref='project', cascade="all, delete-orphan")
    assignments = db.relationship('ProjectAssignment', backref='project', cascade="all, delete-orphan")
    sample_documents = db.relationship('SampleDocument', backref='project', cascade="all, delete-orphan")

class ProjectTechnology(db.Model):
    __tablename__ = 'project_technologies'
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False)
    recommendations_json = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class ProjectScenario(db.Model):
    __tablename__ = 'project_scenarios'
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False)
    scenario_json = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class ProjectAssignment(db.Model):
    __tablename__ = 'project_assignments'
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False)
    mentor_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    intern_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    assignment_date = db.Column(db.Date, default=date.today)
    start_date = db.Column(db.Date, default=date.today)
    deadline = db.Column(db.Date, nullable=False)
    deliverables = db.Column(db.Text)
    github_repo_url = db.Column(db.String(500), default='')
    demo_url = db.Column(db.String(500), default='')
    doc_url = db.Column(db.String(500), default='')
    status = db.Column(db.String(50), default='In Progress')  # 'Not Started', 'In Progress', 'On Track', 'Delayed', 'Submitted', 'Under Review', 'Completed', 'Critical'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    tasks = db.relationship('Task', backref='assignment', cascade="all, delete-orphan")
    submissions = db.relationship('Submission', backref='assignment', cascade="all, delete-orphan")

class Task(db.Model):
    __tablename__ = 'tasks'
    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey('project_assignments.id', ondelete='CASCADE'), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    deadline = db.Column(db.Date)
    status = db.Column(db.String(50), default='Pending')  # 'Pending', 'In Progress', 'Completed', 'Overdue'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class SampleDocument(db.Model):
    __tablename__ = 'sample_documents'
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    evaluation_criteria = db.Column(db.Text, nullable=False)
    expected_sections = db.Column(db.Text, nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

class Submission(db.Model):
    __tablename__ = 'submissions'
    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey('project_assignments.id', ondelete='CASCADE'), nullable=False)
    intern_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    file_type = db.Column(db.String(50), nullable=False)
    notes = db.Column(db.Text)
    github_repo_url = db.Column(db.String(500), default='')
    demo_url = db.Column(db.String(500), default='')
    doc_url = db.Column(db.String(500), default='')
    status = db.Column(db.String(50), default='Under Review')  # 'Submitted', 'Under Review', 'Evaluated', 'Needs Revision'
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    evaluation = db.relationship('EvaluationResult', backref='submission', uselist=False, cascade="all, delete-orphan")

class EvaluationResult(db.Model):
    __tablename__ = 'evaluation_results'
    id = db.Column(db.Integer, primary_key=True)
    submission_id = db.Column(db.Integer, db.ForeignKey('submissions.id', ondelete='CASCADE'), nullable=False, unique=True)
    overall_score = db.Column(db.Integer, nullable=False)
    section_scores_json = db.Column(db.Text, nullable=False)
    missing_sections_json = db.Column(db.Text, nullable=False)
    errors_json = db.Column(db.Text, nullable=False)
    strengths_json = db.Column(db.Text, nullable=False)
    weaknesses_json = db.Column(db.Text, nullable=False)
    recommendations_json = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationship
    feedback = db.relationship('Feedback', backref='evaluation', uselist=False, cascade="all, delete-orphan")

class Feedback(db.Model):
    __tablename__ = 'feedback'
    id = db.Column(db.Integer, primary_key=True)
    evaluation_id = db.Column(db.Integer, db.ForeignKey('evaluation_results.id', ondelete='CASCADE'), nullable=False, unique=True)
    summary = db.Column(db.Text, nullable=False)
    strengths_json = db.Column(db.Text, nullable=False)
    weaknesses_json = db.Column(db.Text, nullable=False)
    required_corrections_json = db.Column(db.Text, nullable=False)
    priority_corrections_json = db.Column(db.Text, nullable=False)
    final_recommendation = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Notification(db.Model):
    __tablename__ = 'notifications'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'))
    action = db.Column(db.String(100), nullable=False)
    entity_type = db.Column(db.String(50))
    entity_id = db.Column(db.Integer)
    details = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
