from flask import redirect, url_for, flash
from flask_login import current_user
from flask_admin import Admin, expose, AdminIndexView
from flask_admin.menu import MenuLink
from flask_admin.contrib.sqla import ModelView
from flask_admin.form import SecureForm, rules
from markupsafe import Markup
from werkzeug.security import generate_password_hash
from wtforms import StringField, HiddenField
from sqlalchemy import and_
from geoalchemy2.shape import from_shape
from shapely.geometry import Point


class HomeView(AdminIndexView):
    @expose('/')
    def admin_index(self):
        return redirect(url_for('main.index'))

    def is_accessible(self):
        return current_user.is_authenticated and current_user.role in ['adm', 'adv']

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('auth.login'))


class CustomUser(ModelView):
    def is_accessible(self):
        return current_user.is_authenticated and current_user.role in ['adm']

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('auth.login'))

    can_view_details = True
    details_modal = True
    column_display_pk = True
    column_default_sort = ('id')
    column_list = ['id', 'username', 'name', 'role', 'email',
                   'last_login_at', 'current_login_at', 'last_login_ip',
                   'current_login_ip', 'login_count']
    form_columns = ['username', 'role', 'name', 'email', 'password_clear']
    form_choices = {
        'role': [('adm', 'Administrator'), ('adv', 'Advanced user'),
                 ('usr', 'User'), ('rdr', 'Reader')]
    }

    def on_model_change(self, form, model, is_created):
        if form.password_clear.data:
            model.password_hash = generate_password_hash(form.password_clear.data)


class customAlunno(ModelView):
    def is_accessible(self):
        return current_user.is_authenticated and current_user.role in ['adv', 'adm']

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('auth.login'))

    action_disallowed_list = ['delete']
    can_delete = False
    can_create = False
    can_edit = False

    column_sortable_list = ('id', 'id_alunno', 'anno_ref', 'luogo_nascita',
                            'sesso', 'anno_sigla', 'sezione',
                            'indirizzo_studi_norm', 'esito_finale_norm')
    column_list = ['id', 'id_alunno', 'anno_ref', 'luogo_nascita', 'sesso',
                   'anno_sigla', 'sezione', 'indirizzo_studi_norm', 'esito_finale_norm']
    column_default_sort = [('id', False), ('start_year', False), ('anno_sigla', False)]
    column_searchable_list = ['anno_ref', 'luogo_nascita']
    column_filters = ['id_alunno', 'anno_ref', 'luogo_nascita', 'sesso',
                      'anno_sigla', 'sezione', 'indirizzo_studi_norm', 'esito_finale_norm']


class AlunnoMedia(ModelView):
    def is_accessible(self):
        return current_user.is_authenticated and current_user.role in ['adv', 'adm']

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('auth.login'))

    can_delete = False
    can_create = False
    can_edit = False

    column_list = ['id_alunno', 'anno_ref', 'sesso', 'anno_sigla', 'sezione',
                   'indirizzo_studi_norm', 'esito_finale_norm']
    column_default_sort = [('id_alunno', False), ('start_year', False), ('anno_sigla', False)]


class AlunnoResidenza(ModelView):
    def is_accessible(self):
        return current_user.is_authenticated and current_user.role in ['adv', 'adm']

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('auth.login'))

    can_delete = False
    can_create = False
    column_display_pk = True
    column_default_sort = [('anno_ref', False), ('id', False)]

    column_list = ['id', 'anno_ref', 'id_alunno', 'anno_corso',
                   'comune_residenza', 'provincia_residenza', 'indirizzo_residenza',
                   'via', 'cap_residenza', 'strade']
    column_searchable_list = ['id_alunno', 'indirizzo_residenza', 'comune_residenza',
                              'strade.osm_road', 'strade.osm_postcode']
    form_columns = ['id_alunno', 'strade']

    def _get_strada_model(self):
        from app.models import Strada
        return Strada

    def _get_alunno_model(self):
        from app.models import Alunno
        return Alunno

    @property
    def column_filters(self):
        from app.models import Alunno
        return [c.name for c in Alunno.__table__.columns]

    @property
    def form_ajax_refs(self):
        Strada = self._get_strada_model()
        return {
            'strade': {
                'fields': ['osm_road', 'osm_postcode', 'osm_suburb'],
                'page_size': 10,
                'order_by': Strada.osm_road
            },
        }


class ResidenzaAlunno(ModelView):
    def is_accessible(self):
        return current_user.is_authenticated and current_user.role in ['adv', 'adm']

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('auth.login'))

    can_delete = False
    can_create = False

    column_list = ['osm_road', 'osm_house_number', 'osm_postcode',
                   'osm_suburb', 'osm_city', 'alunni_nr', 'alunni']
    column_searchable_list = ['osm_road', 'alunni.indirizzo_residenza']
    form_columns = ['osm_road', 'osm_house_number', 'osm_postcode',
                    'osm_suburb', 'osm_city', 'alunni']
    form_widget_args = {
        'osm_road': {'readonly': True},
        'osm_house_number': {'readonly': True},
        'osm_postcode': {'readonly': True},
        'osm_suburb': {'readonly': True},
        'osm_city': {'readonly': True},
    }
    form_edit_rules = [
        rules.HTML('<h3>Utility</h3><p>Collega più studenti ad un unico indirizzo.</p>'),
        rules.FieldSet(
            ['osm_road', 'osm_house_number', 'osm_postcode', 'osm_suburb', 'osm_city', 'alunni'],
            'Sezione principale'
        )
    ]

    @property
    def form_ajax_refs(self):
        from app.models import Alunno
        return {
            'alunni': {
                'fields': ['id_alunno', 'indirizzo_residenza'],
                'page_size': 10,
                'order_by': Alunno.id
            },
        }


class StradaAdmin(ModelView):
    def is_accessible(self):
        return current_user.is_authenticated and current_user.role in ['adv', 'adm']

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('auth.login'))

    form_base_class = SecureForm
    create_template = 'admin/strada_create.html'
    edit_template = 'admin/strada_create.html'

    column_list = ['alunni_nr', 'osm_road', 'osm_house_number', 'osm_postcode',
                   'osm_city', 'osm_suburb', 'osm_type', 'osm_lat', 'osm_lon']
    column_searchable_list = ['osm_road', 'osm_city', 'osm_postcode']
    column_filters = ['alunni_nr', 'osm_city', 'osm_postcode', 'osm_type']

    form_columns = ['osm_road', 'osm_house_number', 'osm_house_number_dev',
                    'osm_postcode', 'osm_suburb', 'osm_city', 'osm_type',
                    'osm_lat', 'osm_lon']

    form_create_rules = [
        rules.FieldSet(('address_search', 'selected_address'), 'Cerca indirizzo'),
        rules.FieldSet((
            'osm_road', 'osm_house_number', 'osm_house_number_dev',
            'osm_postcode', 'osm_suburb', 'osm_city', 'osm_type',
            'osm_lat', 'osm_lon'
        ), 'Dettagli indirizzo')
    ]

    column_labels = {
        'osm_road': 'Via',
        'osm_house_number': 'Numero civico',
        'osm_house_number_dev': 'Interno/Scala',
        'osm_postcode': 'CAP',
        'osm_suburb': 'Quartiere',
        'osm_city': 'Città',
        'osm_type': 'Tipo',
        'osm_lat': 'Latitudine',
        'osm_lon': 'Longitudine',
    }

    def scaffold_form(self):
        form_class = super().scaffold_form()
        form_class.address_search = StringField('Indirizzo da cercare')
        form_class.selected_address = HiddenField()
        return form_class

    def check_duplicate(self, form):
        return self.session.query(self.model).filter(
            and_(
                self.model.osm_road == form.osm_road.data,
                self.model.osm_house_number == form.osm_house_number.data,
                self.model.osm_postcode == form.osm_postcode.data,
            )
        ).first()

    def create_model(self, form):
        try:
            if form.selected_address and form.selected_address.data:
                duplicate = self.check_duplicate(form)
                if duplicate:
                    warning_msg = Markup(
                        f'<strong>Attenzione!</strong> Un indirizzo con questi dettagli esiste già:<br>'
                        f'Via: {duplicate.osm_road}<br>'
                        f'Numero: {duplicate.osm_house_number}<br>'
                        f'CAP: {duplicate.osm_postcode}<br>'
                        f'Quartiere: {duplicate.osm_suburb}<br><br>'
                        f'Modifica i dati o seleziona un altro indirizzo.'
                    )
                    flash(warning_msg, 'warning')
                    return False

                model = self.model()
                form_fields = [
                    'osm_road', 'osm_house_number', 'osm_house_number_dev',
                    'osm_postcode', 'osm_suburb', 'osm_city', 'osm_type',
                    'osm_lat', 'osm_lon'
                ]
                for field in form_fields:
                    setattr(model, field, getattr(form, field).data)

                if model.osm_lat and model.osm_lon:
                    point = Point(float(model.osm_lon), float(model.osm_lat))
                    model.geom = from_shape(point, srid=4326)

                self.session.add(model)
                self.session.commit()
                flash('Indirizzo salvato con successo.', 'success')
                return model
            else:
                flash('Seleziona un indirizzo dai risultati della ricerca.', 'warning')
                return False

        except Exception as e:
            flash(f'Errore durante il salvataggio: {str(e)}', 'error')
            self.session.rollback()
            return False


def configure_admin(app, db):
    """Registra Flask-Admin sull'app."""
    from app.models import User, Alunno, Strada

    admin = Admin(
        app,
        name='AmaldiStoria — Admin',
        index_view=HomeView(name='Home', url='/admin'),
        template_mode='bootstrap4',
        base_template='admin/base.html',
    )

    admin.add_view(CustomUser(User, db.session, name='Utenti', category='Gestione'))
    admin.add_view(customAlunno(Alunno, db.session, name='Alunni', category='Dati'))
    admin.add_view(AlunnoResidenza(Alunno, db.session,
                                   name='Alunni (residenza)', category='Dati',
                                   endpoint='alunno_residenza'))
    admin.add_view(ResidenzaAlunno(Strada, db.session,
                                   name='Strade', category='Dati',
                                   endpoint='residenza_alunno'))
    admin.add_view(StradaAdmin(Strada, db.session,
                               name='Strade (admin)', category='Dati',
                               endpoint='strada_admin'))
    admin.add_link(MenuLink(name='Torna al sito', url='/'))
