from amaldiapp import db, login_manager
from geoalchemy2 import Geometry
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy import func


class User(UserMixin, db.Model):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String, index=True)
    password_clear = db.Column(db.String(128))
    password_hash = db.Column(db.String(128))
    role = db.Column(db.String(64))
    name = db.Column(db.String)
    email = db.Column(db.String(64), unique=True, index=True)
    interest = db.Column(db.Text)
    member_since = db.Column(db.DateTime(), default=datetime.utcnow)

    # notes = db.relationship('ParolaNota', back_populates="useredit")

    @property
    def password(self):
        raise AttributeError('password is not a readable attribute')

    @password.setter
    def password(self, password):
        self.password_hash = generate_password_hash(password)

    def verify_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return '<User %r>' % self.username

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))


class Alunno(db.Model):
    __tablename__ = "alunni"
    id = db.Column(db.Integer, primary_key=True)
    anno_ref = db.Column(db.String(128))
    id_alunno = db.Column(db.Integer, db.ForeignKey('indirizzo.id_alunno'))
    sesso = db.Column(db.String(128))
    luogo_nascita = db.Column(db.String(128))
    provincia_nascita = db.Column(db.String(128))
    stato_nascita = db.Column(db.String(128))
    descr_cittadinanza = db.Column(db.String(128))
    matricola = db.Column(db.String(128))
    comune_residenza = db.Column(db.String(128))
    provincia_residenza = db.Column(db.String(128))
    indirizzo_residenza = db.Column(db.String(128))
    cap_residenza = db.Column(db.String(128))
    stato_alunno = db.Column(db.String(128))
    tipologia_stato_alunno = db.Column(db.String(128))
    data_inizio = db.Column(db.DateTime())
    data_fine = db.Column(db.DateTime())
    numero_volte_iscrizione = db.Column(db.Integer)
    fornito_di = db.Column(db.String(128))
    scuola_provenienza = db.Column(db.String(128))
    posizione = db.Column(db.String(128))
    religione_cattolica = db.Column(db.String(128))
    attivita_alternativa = db.Column(db.String(128))
    educazione_fisica = db.Column(db.String(128))
    esito_finale = db.Column(db.String(128))
    # modifica esito_finale
    esito_finale_norm = db.Column(db.String(128))
    esito_sospeso = db.Column(db.String(128))
    media_voti = db.Column(db.Float)
    scuola_trasferimento = db.Column(db.String(128))
    anno_corso = db.Column(db.Integer)
    anno_sigla = db.Column(db.Integer)
    sezione = db.Column(db.String(128))
    classe = db.Column(db.String(128))
    indirizzo_studi = db.Column(db.String(128))
    # modifica indirizzo_studi
    indirizzo_studi_norm = db.Column(db.String(128))
    classificazione_ministeriale = db.Column(db.String(128))
    indirizzo_ministeriale = db.Column(db.String(128))
    sede = db.Column(db.String(128))
    # modifica sede (CENTRALE/SUCCURSALE)
    sede_norm = db.Column(db.String(128))
    scuola = db.Column(db.String(128))
    cod_meccanografico = db.Column(db.String(128))
    piano_studio = db.Column(db.String(128))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    data_create = db.Column(db.DateTime(), default=datetime.utcnow)
    data_update = db.Column(db.DateTime(), default=datetime.utcnow,
                         onupdate=datetime.utcnow)

    user = db.relationship('User', foreign_keys=[user_id], backref='user_back')
    indirizzo = db.relationship('Indirizzo', foreign_keys=[id_alunno], backref='alunni')

    # @hybrid_property
    # def serie_hyb(self):
    #     return func.coalesce(self.s_main, '') + func.coalesce(self.s_sub, '')

    # @hybrid_property
    # def date_hyb(self):
    #     return func.coalesce(self.d_fase, '') + ' ' + \
    #         func.coalesce(self.d_period, '') + ' ' + \
    #         func.coalesce(self.d_sub, '')


class Indirizzo(db.Model):
	__tablename__ = "indirizzo"
	id_alunno = db.Column(db.Integer, primary_key=True)
	osm_indirizzo_ref = db.Column(db.String(128))
	osm_road = db.Column(db.String(128))
	osm_house_number = db.Column(db.String(128))
	osm_house_number_dev = db.Column(db.String(128))
	osm_postcode = db.Column(db.String(128))
	osm_suburb = db.Column(db.String(128))
	osm_city = db.Column(db.String(128))
	osm_lat = db.Column(db.Float)
	osm_lon = db.Column(db.Float)
	geom = db.Column(Geometry(geometry_type='POINT', srid=4326))
