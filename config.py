import os
from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.flaskenv'))


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'change-me-in-production'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    TEMPLATES_AUTO_RELOAD = True

    # Flask-Admin
    FLASK_ADMIN_FLUID_LAYOUT = True

    # Debug toolbar
    DEBUG_TB_INTERCEPT_REDIRECTS = False

    if not SQLALCHEMY_DATABASE_URI:
        raise ValueError(
            "DATABASE_URL non è impostato. "
            "Assicurati che sia presente nel file .flaskenv o nell'ambiente."
        )
