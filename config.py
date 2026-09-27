import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / '.env')

class Config:
    BASE_DIR = BASE_DIR
    SECRET_KEY = os.getenv('SECRET_KEY', 'mentora-ai-master-secret-key-2025')
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'mentora-ai-jwt-secret-key-2025')
    
    # Database: Supports PostgreSQL (via DATABASE_URL) or local SQLite fallback
    DATABASE_PATH = str(BASE_DIR / os.getenv('DATABASE_PATH', 'database.db'))
    DATABASE_URL = os.getenv('DATABASE_URL', '')
    if DATABASE_URL and DATABASE_URL.startswith('postgres://'):
        DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
    
    SQLALCHEMY_DATABASE_URI = DATABASE_URL if DATABASE_URL else f"sqlite:///{DATABASE_PATH}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Gemini API Key
    GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')
    
    # Upload directories
    UPLOAD_FOLDER = BASE_DIR / 'uploads'
    SAMPLES_FOLDER = UPLOAD_FOLDER / 'samples'
    SUBMISSIONS_FOLDER = UPLOAD_FOLDER / 'submissions'
    TEMPLATES_FOLDER = UPLOAD_FOLDER / 'templates'
    UPSKILLING_FOLDER = UPLOAD_FOLDER / 'upskilling'
    
    ALLOWED_EXTENSIONS = {
        'pdf', 'docx', 'doc', 'txt', 'md', 'rtf', 'xlsx', 'csv', 'pptx', 'ppt',
        'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg',
        'mp4', 'webm', 'mov', 'mkv', 'avi',
        'mp3', 'wav', 'm4a', 'ogg', 'aac'
    }
    MAX_CONTENT_LENGTH = 1024 * 1024 * 1024  # 1GB upload limit for HD video tutorials, screen recordings, audios, and documents

# Create upload directories
Config.UPLOAD_FOLDER.mkdir(exist_ok=True)
Config.SAMPLES_FOLDER.mkdir(exist_ok=True)
Config.SUBMISSIONS_FOLDER.mkdir(exist_ok=True)
Config.TEMPLATES_FOLDER.mkdir(exist_ok=True)
Config.UPSKILLING_FOLDER.mkdir(exist_ok=True)
