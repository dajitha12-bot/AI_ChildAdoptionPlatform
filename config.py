import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'smart_child_adoption_secret_key_2026_dev')
    MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017/smart_adoption')
    MONGO_DB_NAME = os.getenv('MONGO_DB_NAME', 'smart_adoption')

    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')

    SMTP_HOST = os.getenv('SMTP_HOST', 'smtp.gmail.com')
    SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
    SMTP_USERNAME = os.getenv('SMTP_USERNAME', '')
    SMTP_PASSWORD = os.getenv('SMTP_PASSWORD', '')
    SMTP_FROM = os.getenv('SMTP_FROM', os.getenv('SMTP_USERNAME', ''))

    IMAP_HOST = os.getenv('IMAP_HOST', 'imap.gmail.com')
    IMAP_PORT = int(os.getenv('IMAP_PORT', '993'))
    IMAP_USERNAME = os.getenv('IMAP_USERNAME', '')
    IMAP_PASSWORD = os.getenv('IMAP_PASSWORD', '')
