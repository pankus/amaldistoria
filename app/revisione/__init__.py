from flask import Blueprint

bp = Blueprint('revisione', __name__, url_prefix='/revisione')

from app.revisione import views  # noqa: E402,F401
