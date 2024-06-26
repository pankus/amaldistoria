from flask import render_template, Markup, request, jsonify, json, flash, redirect, url_for
from flask_login import login_required, login_user, logout_user, current_user
from amaldiapp import app, db
from sqlalchemy.sql import text, func, and_
from sqlalchemy.orm import joinedload
import os
import folium
from folium.plugins import MarkerCluster, HeatMap, HeatMapWithTime, Fullscreen, Geocoder
import pandas as pd
# import plotly
# import plotly.express as px
import geojson
from collections import OrderedDict, Counter

import flask_admin as admin
from flask_admin import expose, AdminIndexView
from flask_admin.menu import MenuLink
from flask_admin.contrib.sqla import ModelView

from amaldiapp.models import User, Indirizzo, Alunno
from amaldiapp.forms import LoginForm, RegistrationForm


""" UTILS """
def obj2sql(v):
    from sqlalchemy.dialects import postgresql
    sql = str(v.statement.compile(
        dialect=postgresql.dialect(),
        compile_kwargs={"literal_binds": True})
    )
    return sql

""" Admmin Panel """
class HomeView(AdminIndexView):
    @expose('/')
    def admin_index(self):
        return self.render(url_for(index))

class customAlunno(ModelView):
    """ gestion dati alunni """
    
    action_disallowed_list = ['delete', ]
    can_delete = False
    
    column_sortable_list = ('id','id_alunno', 'anno_ref', 'luogo_nascita', 'sesso', 'anno_sigla', 'sezione',
                            'indirizzo_studi_norm', 'esito_finale_norm')
    column_list = ['id', 'id_alunno', 'anno_ref', 'luogo_nascita', 'sesso', 'anno_sigla', 'sezione',
                   'indirizzo_studi_norm', 'esito_finale_norm']
    column_default_sort = 'id'
    
    column_searchable_list = ['anno_ref', 'luogo_nascita']
    column_filters = ['id_alunno', 'anno_ref', 'luogo_nascita', 'sesso', 'anno_sigla', 'sezione',
                      'indirizzo_studi_norm', 'esito_finale_norm']
    
class customIndirizzo(ModelView):
    action_disallowed_list = ['delete', ]
    can_delete = False
    
    column_sortable_list = ('osm_road', 'osm_house_number', 'osm_house_number_dev', 'osm_postcode',
                            'osm_suburb', 'osm_city', 'osm_lat', 'osm_lon')
    column_list = ['osm_road', 'osm_house_number', 'osm_house_number_dev', 'osm_postcode',
                            'osm_suburb', 'osm_city', 'osm_lat', 'osm_lon']
    # column_default_sort = 'osm_city'
    
    column_searchable_list = ['osm_road', 'osm_suburb']
    column_filters = ['osm_road', 'osm_house_number', 'osm_house_number_dev', 'osm_postcode',
                      'osm_suburb', 'osm_city', 'osm_lat', 'osm_lon']

# app.config['FLASK_ADMIN_SWATCH'] = 'spacelab'
# app.config['FLASK_ADMIN_SWATCH'] = 'united'
admin = admin.Admin(app, name='AmaldiStoria [Admin Panel]', template_mode='bootstrap3')

# se non metto la category elimino il sub-menu
admin.add_view(customAlunno(Alunno, db.session, category=''))
admin.add_view(customIndirizzo(Indirizzo, db.session, category=''))
# admin.add_view(ModelView(Indirizzo, db.session))
admin.add_link(MenuLink(name='AmaldiStoria Homepage', url='/'))


@app.route('/')
@app.route('/index')
def index():
    dati = {'user': 'Studente', 'titolo': 'sito web'}
    # print(os.environ.get('SECRET_KEY'))
    # print(os.getenv('SECRET_KEY'))
    return render_template('index.html', dati=dati)


@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()

    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user is not None and user.verify_password(form.password.data):
            login_user(user, form.remember_me.data)
            return redirect(request.args.get('next') or url_for('index'))
        flash(u'Invalid username or password.', 'danger')

    return render_template('login.html', form=form)


@app.route('/logout')
def logout():
    logout_user()
    flash(u'You have been logged out.', 'info')
    return redirect(url_for('index'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        default_role = "rdr"
        pwd_clear = form.password.data
        user = User(email=form.email.data,
                    username=form.username.data,
                    name=form.name.data,
                    password=form.password.data,
                    password_clear=pwd_clear,
                    role=default_role)
        db.session.add(user)
        db.session.commit()
        flash(u'You can now login.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html', form=form)


@app.route('/presentazione')
def presentazione():
    return  render_template('presentazione.html')


@app.route('/immagini')
def immagini():
    return  render_template('immagini.html')


@app.route('/voci')
def voci():
    return  render_template('voci.html')


@app.route('/mapdata', methods=['GET', 'POST'])
def mapjs():

    params = ["2021-2022", "2020-2021", "2019-2020", "2018-2019", "2017-2018", "2016-2017", "2015-2016",
              "2014-2015", "2013-2014", "2012-2013", "2011-2012", "2010-2011", "2009-2010", "2008-2009",
              "2007-2008", "2006-2007", "2005-2006", "2004-2005", "2003-2004", "2002-2003", "2001-2002",
              "2000-2001", "1999-2000", "1998-1999", "1997-1998", "1996-1997", "1995-1996", "1994-1995",
              "1993-1994", "1992-1993"]

    """ Parametro di ricerca iniziale """
    param = '1992-1993'

    """ se ricevo un dato dalla form allora param cambia di conseguenza """
    if request.form:
        if request.form.get('anno') in params:
            param = request.form.get('anno')

    rows = Indirizzo.query.join(Alunno).filter(Alunno.anno_ref == param).filter(Indirizzo.osm_lon.isnot(None)).all()

    features = [ geojson.Feature(
        geometry=geojson.Point((i.osm_lat, i.osm_lon)), properties={"strada": i.osm_road}
        ) for i in rows ]
    
    # geodata = geojson.FeatureCollection(features)

    geodata = geojson.dumps(features)
    # print(geodata)

    return render_template('map.html', params=params, param=param, geodata=geodata)



@app.route('/map', methods=['GET', 'POST'])
def mapdata():

    params = ["2021-2022", "2020-2021", "2019-2020", "2018-2019", "2017-2018", "2016-2017", "2015-2016",
              "2014-2015", "2013-2014", "2012-2013", "2011-2012", "2010-2011", "2009-2010", "2008-2009",
              "2007-2008", "2006-2007", "2005-2006", "2004-2005", "2003-2004", "2002-2003", "2001-2002",
              "2000-2001", "1999-2000", "1998-1999", "1997-1998", "1996-1997", "1995-1996", "1994-1995",
              "1993-1994", "1992-1993"]

    """ Parametro di ricerca iniziale """
    param = '1992-1993'

    """ se ricevo un dato dalla form allora param cambia di conseguenza """
    if request.form:
        if request.form.get('anno') in params:
            param = request.form.get('anno')

    qry = Indirizzo.query.join(Alunno).filter(Alunno.anno_ref == param).filter(Indirizzo.osm_lon.isnot(None)).all()
    punti = [[x.osm_lat, x.osm_lon, x.osm_road] for x in qry]

    """ conto quanti studenti finiranno in mappa (solo quelli che hanno un indirizzo) """
    punti_nr = len(punti)

    """ calcolo della distanza media """
    s = text(
        """ WITH distance AS (
                SELECT
                    -- i.id_alunno,
                    ST_Distance(
                        ST_Transform(i.geom, 3857),
                        ST_Transform(ST_SetSRID( ST_Point( 12.634917, 41.867626), 4326), 3857)
                    ) AS distances,
                    osm_suburb, osm_city, anno_ref
                FROM indirizzo i
                JOIN alunni a ON a.id_alunno = i.id_alunno
                WHERE geom IS NOT NULL
                AND osm_city = 'Roma'
                AND anno_ref = :p
                ORDER BY 1
        )
            SELECT PERCENTILE_CONT(0.5) WITHIN GROUP(ORDER BY distances) FROM distance; """)

    conn = db.engine.connect()
    dist_media = conn.execute(s, p=param).fetchall()


    # sezione per la stampa della mappa (devo dare un'altezza in px altrimenti non si inizializza)
    start_coords = (41.875696, 12.622261)
    start_zoom = 12
    folium_map = folium.Map(location=start_coords,
                            zoom_start=start_zoom,
                            width='100%',
                            height=500,
                            tiles=None,
                            control_scale=True)
    
    # folium.TileLayer(tiles='Stamen Toner', name='Stamen Toner', show=True).add_to(folium_map)
    # folium.TileLayer(tiles='Stamen Terrain', name='Stamen Terrain', show=True).add_to(folium_map)
    folium.TileLayer(tiles='https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',
                     attr='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> \
                           contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
                     name='CartoDB Positron', show=True).add_to(folium_map)
    folium.TileLayer(tiles='https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
                     attr='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> \
                           contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
                     name='CartoDB DarkMatter', show=True).add_to(folium_map)
    folium.TileLayer(tiles='OpenStreetMap', name='Open Street Map', show=True).add_to(folium_map)


    def add_heatmap(folium_map):

        # steps = 20
        # color_map=cm.linear.PuBu.scale(0,1).to_step(steps)

        # gradient_map=defaultdict(dict)
        # for i in range(steps):
        #     gradient_map[1/steps*i] = color_map.rgb_hex_str(1/steps*i)
        
        heat_in = [[x.osm_lat, x.osm_lon] for x in qry]

        HeatMap(data=heat_in,
                radius=15,
                name='Heat Map',
                show=True,
                control=True,
                min_opacity=0.5,
                # gradient = gradient_map
                ).add_to(folium_map)

    
    def add_markers(folium_map):

        ft_group = folium.FeatureGroup(name='Indirizzi', show=False)

        for i in punti:

            circle = folium.CircleMarker([i[0], i[1] ],
                            popup=i[2],
                            radius=5,
                            color="#3186cc",
                            fill=True,
                            fill_color="#3186cc"
                            )
            circle.add_to(ft_group)

        ft_group.add_to(folium_map)


    def add_clusters(folium_map):

        # Markers e Clusters
        clusters = MarkerCluster(name='Dati raggruppati', show=False, control=True)

        for i in punti:
            # folium.Marker( [i[0], i[1] ], popup=i[2]).add_to(marker_cluster)
            circle = folium.CircleMarker([i[0], i[1] ],
                                popup=i[2],
                                radius=5,
                                color="#3186cc",
                                fill=True,
                                fill_color="#3186cc"
                                )

            circle.add_to(clusters)

            clusters.add_to(folium_map)


    """ marker per il Liceo Amaldi e le sue succurslai """
    folium.Marker(
        [ 41.867626, 12.634917 ],
        popup='<strong>Liceo&#160;Amaldi</strong></br>Via&#160;Domenico&#160;Parasacchi',
        icon=folium.Icon(color="darkred", icon="users", prefix="fa")
        ).add_to(folium_map)

    succursali_group = folium.FeatureGroup(name='Succursali*', show=True)

    if param in ["2001-2002", "2002-2003", "2003-2004", "2004-2005", "2005-2006", "2006-2007" ]:
        folium.Marker(
            [ 41.898976, 12.670868 ],
            popup='<strong>Succursale</strong></br>Via&#160;Oscar&#160;Romero</br><small>[2001 - 2007]</small>',
            icon=folium.Icon(color="cadetblue", icon="user", prefix="fa")
            ).add_to(succursali_group)

    if param in ["2007-2008", "2008-2009"]:
        folium.Marker(
            [ 41.869120, 12.577950 ],
            popup='<strong>Succursale</strong></br>Via&#160;Ponti</br><small>[2007 - 2009]</small>',
            icon=folium.Icon(color="cadetblue", icon="user", prefix="fa")
            ).add_to(succursali_group)

    if param in ["2013-2014", "2014-2015", "2015-2016", "2016-2017", "2017-2018", "2018-2019", "2019-2020", "2020-2021", "2021-2022" ]:
        folium.Marker(
            [ 41.912905, 12.692475 ],
            popup='<strong>Succursale</strong></br>Via&#160;Pietrasecca</br><small>attiva dal 2013</small>',
            icon=folium.Icon(color="darkpurple", icon="user", prefix="fa")
            ).add_to(succursali_group)

    
    succursali_group.add_to(folium_map)


    add_heatmap(folium_map)

    # add_markers(folium_map)

    add_clusters(folium_map)

    # add control to pick basemap, layers to show
    folium.LayerControl().add_to(folium_map)



    """ esistono diverse soluzioni per stampare la mappa in un template Jinja2 """
    """ soluzione 1: a pagina intera """
    # return folium_map._repr_html_()
    
    """ soluzione 2: per div o iframes """
    # il metodo save vuole l'intero percorso!
    # # folium_map.save(outfile='/Users/pankus/gitrepo/amaldistoria/amaldiapp/templates/line_map.html')
    # basedir = os.path.abspath(os.path.dirname(__file__))
    # folium_map.save(os.path.join(basedir, 'templates', 'line_map.html'))
    # return render_template('map.html')

    """ soluzione 3: iframes """
    """ sembra essere la soluzione migliore perché non confligge con il resto della pagina (templates e javascript) """
    return render_template('map_studenti.html', folium_map=folium_map, params=params, param=param,
                           request=request.form, punti_nr=punti_nr, dist_media=dist_media)

    """ soluzione 4: scorporando le varie componenti (maggior controllo sul risultato, ma genera conflitti) """
    # _ = folium_map._repr_html_()
    # map_div = Markup(folium_map.get_root().html.render())
    # map_header = Markup(folium_map.get_root().header.render())
    # map_script = Markup(folium_map.get_root().script.render())

    # print(map_header)

    # return render_template('map_folium.html', map_div=map_div, map_header=map_header,
    #                        map_script=map_script, params=params, param=param,
    #                        request=request.form, punti_nr=punti_nr, dist_media=dist_media)


@app.route('/timemap')
def mapdata_time():
    
    q = text(
            r""" --SELECT regexp_replace(anno_ref, '-\d{4}$', ''), array_agg( array[ osm_lat, osm_lon ] ), array_length( array_agg( (osm_lat, osm_lon) ), 1 )
                 SELECT anno_ref, array_agg( array[ osm_lat, osm_lon ] ), array_length( array_agg( (osm_lat, osm_lon) ), 1 )
                 FROM indirizzo i
                 JOIN alunni a ON a.id_alunno = i.id_alunno
                 WHERE geom is not null                 
                 -- GROUP BY regexp_replace(anno_ref, '-\d{4}$', '')
                 GROUP BY anno_ref
                 ORDER BY 1
             """)
        
    conn = db.engine.connect()
    history_data = conn.execute(q).fetchall()

    
    def add_heatmap_time(folium_map):
        
        # https://stackoverflow.com/a/64392033/5541592
        data = OrderedDict()
        data = dict([ (r[0], r[1]) for r in history_data ])

        HeatMapWithTime(data=list(data.values()),
                        index=list(data.keys()),
                        radius=15,
                        name="Time HeatMap",
                        auto_play=False,
                        max_opacity=0.5
                        ).add_to(folium_map)


    start_coords = (41.875696, 12.622261)
    start_zoom = 12
    folium_map = folium.Map(location=start_coords,
                            zoom_start=start_zoom,
                            width='100%',
                            height=550,
                            # height='100%',
                            tiles=None,
                            control_scale=True)
    
    # folium.TileLayer(tiles='Stamen Toner', name='Stamen Toner', show=True).add_to(folium_map)
    # folium.TileLayer(tiles='Stamen Terrain', name='Stamen Terrain', show=True).add_to(folium_map)
    folium.TileLayer(tiles='https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',
                     attr='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> \
                           contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
                     name='CartoDB Positron', show=True).add_to(folium_map)
    folium.TileLayer(tiles='https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
                     attr='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> \
                           contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
                     name='CartoDB DarkMatter', show=True).add_to(folium_map)
    folium.TileLayer(tiles='OpenStreetMap', name='Open Street Map', show=True).add_to(folium_map)


    Fullscreen(position='topleft', # ‘topleft’, default=‘topright’, ‘bottomleft’, ‘bottomright’ 
               title='Schermo intero', 
               title_cancel='',
               force_separate_button=False
               ).add_to(folium_map)

    """ marker per il Liceo Amaldi """
    folium.Marker(
        [ 41.867626, 12.634917 ],
        popup='<strong>Liceo&#160;Amaldi</strong></br>Via&#160;Domenico&#160;Parasacchi',
        icon=folium.Icon(color="darkred", icon="users", prefix="fa")
        ).add_to(folium_map)

    succursali_group = folium.FeatureGroup(name='Succursali', show=True)

    folium.Marker(
        [ 41.898976, 12.670868 ],
        popup='<strong>Succursale</strong></br>Via&#160;Oscar&#160;Romero</br><small>[2001 - 2007]</small>',
        icon=folium.Icon(color="cadetblue", icon="user", prefix="fa")
        ).add_to(succursali_group)

    folium.Marker(
        [ 41.869120, 12.577950 ],
        popup='<strong>Succursale</strong></br>Via&#160;Ponti</br><small>[2007 - 2009]</small>',
        icon=folium.Icon(color="cadetblue", icon="user", prefix="fa")
        ).add_to(succursali_group)

    folium.Marker(
        [ 41.912905, 12.692475 ],
        popup='<strong>Succursale</strong></br>Via&#160;Pietrasecca</br><small>attiva dal 2013</small>',
        icon=folium.Icon(color="darkpurple", icon="user", prefix="fa")
        ).add_to(succursali_group)

    succursali_group.add_to(folium_map)


    add_heatmap_time(folium_map)

    folium.LayerControl().add_to(folium_map)

    return render_template('map_studenti_time.html', folium_map=folium_map)
    # return folium_map._repr_html_()


@app.route('/map-graph', methods=['GET', 'POST'])
def map_graph():

    params = ["2021-2022", "2020-2021", "2019-2020", "2018-2019", "2017-2018", "2016-2017", "2015-2016",
              "2014-2015", "2013-2014", "2012-2013", "2011-2012", "2010-2011", "2009-2010", "2008-2009",
              "2007-2008", "2006-2007", "2005-2006", "2004-2005", "2003-2004", "2002-2003", "2001-2002",
              "2000-2001", "1999-2000", "1998-1999", "1997-1998", "1996-1997", "1995-1996", "1994-1995",
              "1993-1994", "1992-1993"]

    # nation = db.session.query(Alunno.descr_cittadinanza, func.count(Alunno.descr_cittadinanza)).\
    #          group_by(Alunno.descr_cittadinanza).order_by(Alunno.descr_cittadinanza).all()


    """ Parametro di ricerca iniziale """
    param = '1992-1993'

    fil_anno, fil_nation, fil_stato, fil_esito = '', '', '', ''
    fil_anno_sigla, fil_indirizzo = '', ''

    if request.form.get('anno'):
        fil_anno = [Alunno.anno_ref == request.form.get('anno', '')]
        param = request.form.get('anno')

    if request.form.get('nationalita'):
        fil_nation = [Alunno.descr_cittadinanza == request.form.get('nationalita', '')]

    if request.form.get('stato_alunno'):
        fil_stato = [Alunno.stato_alunno == request.form.get('stato_alunno', '')]

    if request.form.get('esito_finale'):
        fil_stato = [Alunno.esito_finale_norm == request.form.get('esito_finale', '')]

    if request.form.get('anno_sigla'):
        fil_anno_sigla = [Alunno.anno_sigla == request.form.get('anno_sigla', '')]

    if request.form.get('indirizzo_studio'):
        fil_indirizzo = [Alunno.indirizzo_studi_norm == request.form.get('indirizzo_studio')]

    """ query principale (prima chiamata) """
    qry = db.session.query(Alunno).\
          options(joinedload(Alunno.indirizzo)).\
          join(Indirizzo).filter(Alunno.anno_ref == param)
          # filter(Indirizzo.osm_lon.isnot(None)).all()

    """ la query cambia ad ogni chiamata POST """
    if request.method == 'POST':
        qry = db.session.query(Alunno).\
              options(joinedload(Alunno.indirizzo)).\
              join(Indirizzo).\
              filter(*fil_anno).filter(*fil_nation).\
              filter(*fil_stato).filter(*fil_esito).\
              filter(*fil_anno_sigla).filter(*fil_indirizzo)
        # qry = Alunno.query.join(Indirizzo).\
        #       filter(*fil_anno).filter(*fil_nation).\
        #       filter(*fil_stato).filter(*fil_esito).\
        #       filter(*fil_anno_sigla).filter(*fil_indirizzo)
              # filter(Indirizzo.osm_lon.isnot(None)).all()

    # DEBUG query
    # print(obj2sql(qry))

    qry = qry.all()

    """ popolamento dei menu select """
    nation = sorted(set( [x.descr_cittadinanza for x in qry if x.descr_cittadinanza] ))
    stato_alunno = sorted(set( [x.stato_alunno for x in qry if x.stato_alunno] ))
    esito = sorted(set( [x.esito_finale_norm for x in qry if x.esito_finale_norm] ))
    anno_sigla = sorted(set( [str(x.anno_sigla) for x in qry if x.anno_sigla] ))
    indirizzo = sorted(set( [str(x.indirizzo_studi_norm) for x in qry if x.indirizzo_studi_norm] ))
    
    iscritti = db.session.query(Alunno).filter(Alunno.anno_ref == param).count()
    if request.form.get('anno'):
        iscritti = db.session.query(Alunno).filter(*fil_anno).count()
    print(iscritti)

    # nation = db.session.query(func.coalesce(Alunno.descr_cittadinanza, 'N.D.'), func.count(Alunno.descr_cittadinanza)).\
    #          filter(*filters).\
    #          group_by(Alunno.descr_cittadinanza).order_by(Alunno.descr_cittadinanza).all()
    
    # DEBUG
    # print(request.method)
    # print('PARAMETRI: ', param, request, len(qry))
    # print(fil_anno, fil_nation, fil_stato, fil_esito)

    """ GRAFICI """
    """ Highcharts > cittadinanza, genere, indirizzo > grafico a torta """
    tmp_cittadinanza = Counter( [x.descr_cittadinanza for x in qry] )
    order_cittadinanza = sorted( tmp_cittadinanza.items(), key= lambda v: v[1], reverse=True )
    data_cittadinanza = OrderedDict( order_cittadinanza )
    
    data_genere = OrderedDict( Counter( [x.sesso for x in qry] ) )
    data_indirizzo = OrderedDict( Counter( [x.indirizzo_studi_norm for x in qry] ) )
    data_cap = OrderedDict( Counter( [x.cap_residenza for x in qry] ) )

    """ mappa """
    punti = [[x.indirizzo.osm_lat, x.indirizzo.osm_lon, x.indirizzo.osm_road] for x in qry if x.indirizzo.geom]

    # sezione per la stampa della mappa (devo dare un'altezza in px altrimenti non si inizializza)
    start_coords = (41.875696, 12.622261)
    start_zoom = 12
    folium_map = folium.Map(location=start_coords,
                            zoom_start=start_zoom,
                            width='100%',
                            height=600,
                            tiles=None,
                            control_scale=True)
    
    # folium.TileLayer(tiles='Stamen Toner', name='Stamen Toner', show=True).add_to(folium_map)
    # folium.TileLayer(tiles='Stamen Terrain', name='Stamen Terrain', show=True).add_to(folium_map)
    folium.TileLayer(tiles='https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',
                     attr='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> \
                           contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
                     name='CartoDB Positron', show=True).add_to(folium_map)
    folium.TileLayer(tiles='https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
                     attr='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> \
                           contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
                     name='CartoDB DarkMatter', show=True).add_to(folium_map)
    folium.TileLayer(tiles='OpenStreetMap', name='Open Street Map', show=True).add_to(folium_map)

    Fullscreen(position='topleft', # ‘topleft’, default=‘topright’, ‘bottomleft’, ‘bottomright’ 
               title='Schermo intero', 
               title_cancel='',
               force_separate_button=False
               ).add_to(folium_map)

    def add_heatmap(folium_map):

        heat_in = [[x.indirizzo.osm_lat, x.indirizzo.osm_lon] for x in qry if x.indirizzo.geom]

        HeatMap(data=heat_in,
                radius=15,
                name='Heat Map',
                show=True,
                control=True,
                min_opacity=0.5,
                # gradient = gradient_map
                ).add_to(folium_map)

    
    def add_markers(folium_map):

        ft_group = folium.FeatureGroup(name='Indirizzi', show=False)

        for i in punti:

            circle = folium.CircleMarker([i[0], i[1] ],
                            popup=i[2],
                            radius=5,
                            color="#3186cc",
                            fill=True,
                            fill_color="#3186cc"
                            )
            circle.add_to(ft_group)

        ft_group.add_to(folium_map)


    def add_clusters(folium_map):

        # Markers e Clusters
        clusters = MarkerCluster(name='Dati raggruppati', show=False, control=True)

        for i in punti:
            # folium.Marker( [i[0], i[1] ], popup=i[2]).add_to(marker_cluster)
            circle = folium.CircleMarker([i[0], i[1] ],
                                popup=i[2],
                                radius=5,
                                color="#3186cc",
                                fill=True,
                                fill_color="#3186cc"
                                )

            circle.add_to(clusters)

            clusters.add_to(folium_map)


    """ marker per il Liceo Amaldi """
    folium.Marker(
        [ 41.867626, 12.634917 ],
        popup='<strong>Liceo&#160;Amaldi</strong></br>Via&#160;Domenico&#160;Parasacchi',
        icon=folium.Icon(color="darkred", icon="users", prefix="fa")
        ).add_to(folium_map)

    succursali_group = folium.FeatureGroup(name='Succursali*', show=True)

    if param in ["2001-2002", "2002-2003", "2003-2004", "2004-2005", "2005-2006", "2006-2007" ]:
        folium.Marker(
            [ 41.898976, 12.670868 ],
            popup='<strong>Succursale</strong></br>Via&#160;Oscar&#160;Romero</br><small>[2001 - 2007]</small>',
            icon=folium.Icon(color="cadetblue", icon="user", prefix="fa")
            ).add_to(succursali_group)

    if param in ["2007-2008", "2008-2009"]:
        folium.Marker(
            [ 41.869120, 12.577950 ],
            popup='<strong>Succursale</strong></br>Via&#160;Ponti</br><small>[2007 - 2009]</small>',
            icon=folium.Icon(color="cadetblue", icon="user", prefix="fa")
            ).add_to(succursali_group)

    if param in ["2013-2014", "2014-2015", "2015-2016", "2016-2017", "2017-2018", "2018-2019", "2019-2020", "2020-2021", "2021-2022" ]:
        folium.Marker(
            [ 41.912905, 12.692475 ],
            popup='<strong>Succursale</strong></br>Via&#160;Pietrasecca</br><small>attiva dal 2013</small>',
            icon=folium.Icon(color="darkpurple", icon="user", prefix="fa")
            ).add_to(succursali_group)

    
    succursali_group.add_to(folium_map)

    add_heatmap(folium_map)

    add_clusters(folium_map)

    # add control to pick basemap, layers to show
    folium.LayerControl().add_to(folium_map)

    return render_template('map_graph.html',
                           params=params,
                           param=param,
                           request=request.form,
                           nation=nation,
                           esito=esito,
                           indirizzo=indirizzo,
                           anno_sigla=anno_sigla,
                           qry=qry,
                           stato_alunno=stato_alunno,
                           folium_map=folium_map,
                           chart_cittadinanza=data_cittadinanza,
                           chart_genere=data_genere,
                           chart_indirizzo=data_indirizzo,
                           chart_cap=data_cap,
                           iscritti=iscritti
                           )


@app.route('/serie-generale')
def serie_generale():

    """ genere """
    g = text(
            r""" SELECT anno_ref,
                    array_length(array_agg( id_alunno), 1),
                    SUM(CASE WHEN sesso = 'M' THEN 1 END) AS Male,
                    SUM(CASE WHEN sesso = 'F' THEN 1 END) AS female,
                    count(sesso)
                FROM alunni
                GROUP BY anno_ref
                ORDER BY anno_ref
             """)
        
    conn = db.engine.connect()
    gender_rows = conn.execute(g).fetchall()
    
    gender_data = {
        'anni': (x[0] for x in gender_rows),
        'maschi': (x[2] for x in gender_rows),
        'femmine': (x[3] for x in gender_rows),
        'tot': (x[4] for x in gender_rows)
    }
    
    """ nazionalità """
    n = text(
            r""" SELECT anno_ref,
                    array_length(array_agg( id_alunno), 1) as tot,
                    SUM(CASE WHEN descr_cittadinanza = 'ITALIANA' THEN 1 END) AS italiana,
                    COALESCE( SUM(CASE WHEN descr_cittadinanza != 'ITALIANA' THEN 1 END), 0 ) AS nonitaliana,
                    count(descr_cittadinanza)
                FROM alunni
                GROUP BY anno_ref
                ORDER BY anno_ref
             """)
        
    conn = db.engine.connect()
    nation_rows = conn.execute(n).fetchall()

    nation_data = {
        'anni': (x[0] for x in nation_rows),
        'iscritti': (x[1] for x in nation_rows),
        'italiani': (x[2] for x in nation_rows),
        'stranieri': (x[3] if x[3] > 0 else 'null' for x in nation_rows)
    }

    """ sql per indirizzo studi senza distinguere il genere """
    # i = text(
    #         r""" SELECT anno_ref,
    #                 array_length(array_agg( id_alunno), 1) as tot,
    #                 coalesce ( SUM(CASE WHEN indirizzo_studi ILIKE '%LINGUIS%' THEN 1 END) , 0) AS linguistico,
    #                 coalesce ( SUM(CASE WHEN indirizzo_studi ILIKE '%CLASSIC%' THEN 1 END) , 0) AS classico,
    #                 coalesce ( SUM(CASE WHEN indirizzo_studi ILIKE '%SCIENTIF%' THEN 1 END) , 0) AS scientifico,
    #                 coalesce ( SUM(CASE WHEN indirizzo_studi ILIKE '%PRIVATI%' THEN 1 END) , 0) AS privatisti,
    #                 count(indirizzo_studi)
    #             FROM alunni
    #             GROUP BY anno_ref
    #             ORDER BY anno_ref
    #          """)
        
    # conn = db.engine.connect()
    # indirizzo_rows = conn.execute(i).fetchall()



    # indirizzo_data = {
    #     'anni': (x[0] for x in indirizzo_rows),
    #     'iscritti': (x[1] for x in indirizzo_rows),
    #     'linguistico': (x[2] if x[2] > 0 else 'null' for x in indirizzo_rows),
    #     'classico': (x[3] if x[3] > 0 else 'null' for x in indirizzo_rows),
    #     'scientifico': (x[4] if x[4] > 0 else 'null' for x in indirizzo_rows),
    #     'privatisti': (x[5] if x[5] > 0 else 'null' for x in indirizzo_rows)
    # }

    """ indirizzo studi """
    i = text(
            r""" SELECT anno_ref,
                    array_length(array_agg( id_alunno), 1) as tot,
                    coalesce ( SUM(CASE WHEN indirizzo_studi ILIKE '%LINGUIS%' and sesso = 'M' THEN 1 END) , 0) AS linguisticoM,
                    coalesce ( SUM(CASE WHEN indirizzo_studi ILIKE '%LINGUIS%' and sesso = 'F' THEN 1 END) , 0) AS linguisticoF,
                    coalesce ( SUM(CASE WHEN indirizzo_studi ILIKE '%CLASSIC%' and sesso = 'M' THEN 1 END) , 0) AS classicoM,
                    coalesce ( SUM(CASE WHEN indirizzo_studi ILIKE '%CLASSIC%' and sesso = 'F' THEN 1 END) , 0) AS classicoF,
                    coalesce ( SUM(CASE WHEN indirizzo_studi ILIKE '%SCIENTIF%' and sesso = 'M' THEN 1 END) , 0) AS scientificoM,
                    coalesce ( SUM(CASE WHEN indirizzo_studi ILIKE '%SCIENTIF%' and sesso = 'F' THEN 1 END) , 0) AS scientificoF,
                    coalesce ( SUM(CASE WHEN indirizzo_studi ILIKE '%PRIVATI%' and sesso = 'M' THEN 1 END) , 0) AS privatistiM,
                    coalesce ( SUM(CASE WHEN indirizzo_studi ILIKE '%PRIVATI%' and sesso = 'F' THEN 1 END) , 0) AS privatistiF,
                    count(indirizzo_studi)
                FROM alunni
                GROUP BY anno_ref
                ORDER BY anno_ref
             """)
        
    conn = db.engine.connect()
    indirizzo_rows = conn.execute(i).fetchall()

    indirizzo_data = {
        'anni': (x[0] for x in indirizzo_rows),
        'iscritti': (x[1] for x in indirizzo_rows),
        'linguistico': (x[2] if x[2] > 0 else 'null' for x in indirizzo_rows),
        'linguisticof': (x[3] if x[3] > 0 else 'null' for x in indirizzo_rows),
        'classico': (x[4] if x[4] > 0 else 'null' for x in indirizzo_rows),
        'classicof': (x[5] if x[5] > 0 else 'null' for x in indirizzo_rows),
        'scientifico': (x[6] if x[6] > 0 else 'null' for x in indirizzo_rows),
        'scientificof': (x[7] if x[7] > 0 else 'null' for x in indirizzo_rows),
        'privatisti': (x[8] if x[8] > 0 else 'null' for x in indirizzo_rows),
        'privatisti': (x[9] if x[9] > 0 else 'null' for x in indirizzo_rows)
    }

    """ affollamento scolastico """
    a = text(
            r""" with affollamento as (
                 SELECT
                     anno_ref, count(*) as per_classe,
                     anno_sigla,
                     sezione,
                     array_agg( id_alunno )
                 FROM alunni
                 where sezione !~ 'P'
                 GROUP BY anno_ref, anno_sigla, sezione
                 ORDER BY anno_ref, anno_sigla, sezione
                 )
                 select 
                     anno_ref, min(per_classe), max(per_classe), round(avg(per_classe))
                 from affollamento
                 group by anno_ref
                 having min(per_classe) > 5
                 order by anno_ref
             """)
        
    conn = db.engine.connect()
    affollamento_rows = conn.execute(a).fetchall()

    affollamento_data = {
        'anni': [x[0] for x in affollamento_rows],
        'ranges': [ [x[0], x[1], x[2] ] for x in affollamento_rows],
        'avarages': [ [x[0], int(x[3]) ] for x in affollamento_rows]
    }

    # print(affollamento_data)

    return render_template('serie_generale.html',
                           gender_data=gender_data,
                           nation_data=nation_data,
                           indirizzo_data=indirizzo_data,
                           affollamento_data=affollamento_data
                          )


@app.route('/serie-indirizzo')
def serie_indirizzo():

    """ indirizzo studi """

    plotbands = r"""
        {color: 'rgba(68, 170, 213, 0.1)', from: 9, to: 14,
        label: {text: '<strong>Succursale</strong></br>Via Oscar Romero',
          style: {color: '#606060'}
        }
      }, 
      {color: 'rgba(68, 170, 213, 0.1)', from: 15, to: 16,
        label: {text: '<strong>Succursale</strong></br>Via Ponti',
          style: {color: '#606060'}
        }
      },
      {color: 'rgba(68, 170, 213, 0.1)', from: 21, to: 30,
        label: {text: '<strong>Succursale</strong></br>Via Pietrasecca',
          style: {color: '#606060'}
        }
      }
    """

    i = text(
            r""" SELECT anno_ref,
                    array_length(array_agg( id_alunno), 1) as tot,
                    coalesce ( SUM(CASE WHEN indirizzo_studi ILIKE '%LINGUIS%' and sesso = 'M' THEN 1 END) , 0) AS linguisticoM,
                    coalesce ( SUM(CASE WHEN indirizzo_studi ILIKE '%LINGUIS%' and sesso = 'F' THEN 1 END) , 0) AS linguisticoF,
                    coalesce ( SUM(CASE WHEN indirizzo_studi ILIKE '%CLASSIC%' and sesso = 'M' THEN 1 END) , 0) AS classicoM,
                    coalesce ( SUM(CASE WHEN indirizzo_studi ILIKE '%CLASSIC%' and sesso = 'F' THEN 1 END) , 0) AS classicoF,
                    coalesce ( SUM(CASE WHEN indirizzo_studi ILIKE '%SCIENTIF%' and sesso = 'M' THEN 1 END) , 0) AS scientificoM,
                    coalesce ( SUM(CASE WHEN indirizzo_studi ILIKE '%SCIENTIF%' and sesso = 'F' THEN 1 END) , 0) AS scientificoF,
                    coalesce ( SUM(CASE WHEN indirizzo_studi ILIKE '%PRIVATI%' and sesso = 'M' THEN 1 END) , 0) AS privatistiM,
                    coalesce ( SUM(CASE WHEN indirizzo_studi ILIKE '%PRIVATI%' and sesso = 'F' THEN 1 END) , 0) AS privatistiF,
                    count(indirizzo_studi)
                FROM alunni
                GROUP BY anno_ref
                ORDER BY anno_ref
             """)
        
    conn = db.engine.connect()
    indirizzo_rows = conn.execute(i).fetchall()

    indirizzo_data = {
        'anni': [x[0] for x in indirizzo_rows],
        'iscritti': [x[1] for x in indirizzo_rows],
        'linguistico': [x[2] if x[2] > 0 else 'null' for x in indirizzo_rows],
        'linguisticof': [x[3] if x[3] > 0 else 'null' for x in indirizzo_rows],
        'classico': [x[4] if x[4] > 0 else 'null' for x in indirizzo_rows],
        'classicof': [x[5] if x[5] > 0 else 'null' for x in indirizzo_rows],
        'scientifico': [x[6] if x[6] > 0 else 'null' for x in indirizzo_rows],
        'scientificof': [x[7] if x[7] > 0 else 'null' for x in indirizzo_rows],
        'privatisti': [x[8] if x[8] > 0 else 'null' for x in indirizzo_rows],
        'privatistif': [x[9] if x[9] > 0 else 'null' for x in indirizzo_rows]
    }

    return render_template('serie_indirizzo.html',
                           plotbands=plotbands,
                           indirizzo_data=indirizzo_data
                          )


@app.route('/serie-stato')
def serie_stato():

    plotbands = r"""
        {color: 'rgba(68, 170, 213, 0.1)', from: 9, to: 14,
        label: {text: '<strong>Succursale</strong></br>Via Oscar Romero',
          style: {color: '#606060'}
        }
      }, 
      {color: 'rgba(68, 170, 213, 0.1)', from: 15, to: 16,
        label: {text: '<strong>Succursale</strong></br>Via Ponti',
          style: {color: '#606060'}
        }
      },
      {color: 'rgba(68, 170, 213, 0.1)', from: 21, to: 30,
        label: {text: '<strong>Succursale</strong></br>Via Pietrasecca',
          style: {color: '#606060'}
        }
      }
    """

    """ trasferimento / abbandono studenti (stato_alunno) """

    s = text(
            r"""
                SELECT anno_ref,
                    array_length(array_agg( id_alunno), 1) as tot,
                    -- devo dividere tra bocciati e promossi
                    coalesce( SUM(CASE WHEN stato_alunno = 'Frequenta' THEN 1 END) , 0 ) AS frequenta,
                    coalesce( SUM(CASE WHEN stato_alunno = 'Abbandona' THEN 1 END) , 0 ) AS abbandona,
                    coalesce( SUM(CASE WHEN stato_alunno = 'Trasferito' THEN 1 END) , 0 ) AS trasferito,
                    count(stato_alunno),
                    coalesce( SUM(CASE WHEN stato_alunno = 'Frequenta' and indirizzo_studi ILIKE '%LINGUIS%' THEN 1 END) , 0 ) AS frequenta_ling,
                    coalesce( SUM(CASE WHEN stato_alunno = 'Frequenta' and indirizzo_studi ILIKE '%CLASSIC%' THEN 1 END) , 0 ) AS frequenta_clas,
                    coalesce( SUM(CASE WHEN stato_alunno = 'Frequenta' and indirizzo_studi ILIKE '%SCIENTIF%' THEN 1 END) , 0 ) AS frequenta_scie,
                    coalesce( SUM(CASE WHEN stato_alunno = 'Abbandona' and indirizzo_studi ILIKE '%LINGUIS%' THEN 1 END) , 0 ) AS abbandona_ling,
                    coalesce( SUM(CASE WHEN stato_alunno = 'Abbandona' and indirizzo_studi ILIKE '%CLASSIC%' THEN 1 END) , 0 ) AS abbandona_clas,
                    coalesce( SUM(CASE WHEN stato_alunno = 'Abbandona' and indirizzo_studi ILIKE '%SCIENTIF%' THEN 1 END) , 0 ) AS abbandona_scie,
                    coalesce( SUM(CASE WHEN stato_alunno = 'Trasferito' and indirizzo_studi ILIKE '%LINGUIS%' THEN 1 END) , 0 ) AS trasferito_ling,
                    coalesce( SUM(CASE WHEN stato_alunno = 'Trasferito' and indirizzo_studi ILIKE '%CLASSIC%' THEN 1 END) , 0 ) AS trasferito_clas,
                    coalesce( SUM(CASE WHEN stato_alunno = 'Trasferito' and indirizzo_studi ILIKE '%SCIENTIF%' THEN 1 END) , 0 ) AS trasferito_scie
                FROM alunni
                GROUP BY anno_ref
                ORDER BY anno_ref
            """)

    conn = db.engine.connect()
    stato_rows = conn.execute(s).fetchall()

    stato_data = {
        'anni': [x[0] for x in stato_rows],
        'iscritti': [x[1] for x in stato_rows],
        'frequenta': [x[2] if x[2] > 0 else 'null' for x in stato_rows],
        'abbandona': [x[3] if x[3] > 0 else 'null' for x in stato_rows],
        'trasferito': [x[4] if x[4] > 0 else 'null' for x in stato_rows]
    }

    stato_indirizzo_data = {
        'anni': [x[0] for x in stato_rows],
        'iscritti': [x[1] for x in stato_rows],
        'frequenta_ling': [x[6] if x[6] > 0 else 'null' for x in stato_rows],
        'frequenta_clas': [x[7] if x[7] > 0 else 'null' for x in stato_rows],
        'frequenta_scie': [x[8] if x[8] > 0 else 'null' for x in stato_rows],
        'abbandona_ling': [x[9] if x[9] > 0 else 'null' for x in stato_rows],
        'abbandona_clas': [x[10] if x[10] > 0 else 'null' for x in stato_rows],
        'abbandona_scie': [x[11] if x[11] > 0 else 'null' for x in stato_rows],
        'trasferito_ling': [x[12] if x[12] > 0 else 'null' for x in stato_rows],
        'trasferito_clas': [x[13] if x[13] > 0 else 'null' for x in stato_rows],
        'trasferito_scie': [x[14] if x[14] > 0 else 'null' for x in stato_rows]
    }

    n = text(
            r"""
                SELECT anno_ref,
                    array_length(array_agg( id_alunno), 1) as tot,
                    coalesce( SUM(CASE WHEN descr_cittadinanza = 'ITALIANA' THEN 1 END) , 0 ) AS italiana,
                    coalesce( SUM(CASE WHEN descr_cittadinanza != 'ITALIANA' THEN 1 END) , 0 ) AS nonitaliana,
                    coalesce( SUM(CASE WHEN stato_alunno = 'Abbandona' and descr_cittadinanza = 'ITALIANA' THEN 1 END) , 0 ) AS abb_ita,
                    coalesce( SUM(CASE WHEN stato_alunno = 'Abbandona' and descr_cittadinanza != 'ITALIANA' THEN 1 END) , 0 ) AS abb_no_ita,
                    coalesce( SUM(CASE WHEN stato_alunno = 'Trasferito' and descr_cittadinanza = 'ITALIANA' THEN 1 END) , 0 ) AS tra_ita,
                    coalesce( SUM(CASE WHEN stato_alunno = 'Trasferito' and descr_cittadinanza != 'ITALIANA' THEN 1 END) , 0 ) AS tra_no_ita,
                    count(descr_cittadinanza)
                FROM alunni
                -- il fenomeno comincia dal 2001
                WHERE anno_ref IN ('2001-2002', '2002-2003', '2003-2004', '2004-2005', '2005-2006', '2006-2007', '2007-2008',
                                   '2008-2009', '2009-2010', '2010-2011', '2011-2012', '2012-2013', '2013-2014', '2014-2015',
                                   '2015-2016', '2016-2017', '2017-2018', '2018-2019', '2019-2020', '2020-2021', '2021-2022')
                GROUP BY anno_ref
                ORDER BY anno_ref
            """)

    conn = db.engine.connect()
    stato_rows = conn.execute(n).fetchall()

    stato_nation = {
        'anni': [x[0] for x in stato_rows],
        'tot': [x[1] if x[1] > 0 else 'null' for x in stato_rows],
        'ita': [x[2] if x[2] > 0 else 'null' for x in stato_rows],
        'noita': [x[3] if x[3] > 0 else 'null' for x in stato_rows],
        'abb_ita': [x[4] if x[4] > 0 else 'null' for x in stato_rows],
        'abb_no_ita': [x[5] if x[5] > 0 else 'null' for x in stato_rows],
        'tra_ita': [x[6] if x[6] > 0 else 'null' for x in stato_rows],
        'tra_no_ita': [x[7] if x[7] > 0 else 'null' for x in stato_rows]
    }


    return render_template('serie_stato.html', plotbands=plotbands,
                           stato_data=stato_data,
                           stato_indirizzo_data=stato_indirizzo_data,
                           stato_nation=stato_nation
                          )
    
@app.route('/test')
def test():
    return render_template('test.html')