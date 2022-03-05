from flask import render_template
from amaldiapp import app


@app.route('/')
@app.route('/index')
def index():
	dati = {'user': 'Studente', 'titolo': 'sito web'}
	return render_template('index.html', dati=dati)