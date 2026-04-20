from flask import Flask
from config import Config
from app.extensions import db, migrate, login_manager, moment, bootstrap


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Inizializza estensioni
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    moment.init_app(app)
    bootstrap.init_app(app)

    # Importa i modelli DENTRO create_app, dopo db.init_app
    # Necessario per Flask-Login user_loader e per Alembic
    with app.app_context():
        from app import models  # noqa: F401

    # Registra blueprints
    from app.main import bp as main_bp
    app.register_blueprint(main_bp)

    from app.auth import bp as auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')

    # Configura Flask-Admin
    from app.admin_views import configure_admin
    configure_admin(app, db)

    # Debug toolbar (solo in sviluppo)
    if app.config.get('DEBUG'):
        from flask_debugtoolbar import DebugToolbarExtension
        DebugToolbarExtension(app)

    return app
