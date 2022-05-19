from flask import Flask
from config import Config
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_bootstrap import Bootstrap
from flask_login import LoginManager
from flask_moment import Moment
# from flask_admin import Admin
from flask_debugtoolbar import DebugToolbarExtension


login_manager = LoginManager()
login_manager.session_protection = 'strong'
login_manager.login_view = 'login'
login_manager.login_message_category = "info"


app = Flask(__name__)
app.config.from_object(Config)
db = SQLAlchemy(app)
migrate = Migrate(app, db)
bootstrap = Bootstrap(app)
login_manager.init_app(app)
moment = Moment(app)
# admin = Admin(app, name='AmaldiStoria - Admin Panel', template_mode='bootstrap3')

toolbar = DebugToolbarExtension(app)


from amaldiapp import views, models