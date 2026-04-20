from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_moment import Moment
from flask_bootstrap import Bootstrap5

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
moment = Moment()
bootstrap = Bootstrap5()

login_manager.session_protection = 'strong'
login_manager.login_view = 'auth.login'
login_manager.login_message_category = 'info'
