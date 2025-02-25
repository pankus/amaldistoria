from amaldiapp import app, db
from amaldiapp.models import User, Alunno, Indirizzo, Strada


@app.shell_context_processor
def make_shell_context():
	return {'db': db, 'User': User, 'Alunno': Alunno, 'Indirizzo': Indirizzo}