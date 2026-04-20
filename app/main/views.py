from flask import render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from sqlalchemy.sql import text
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy import exists
from collections import OrderedDict, Counter

from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut
from app.main import bp
from app.extensions import db
from app.models import User, Indirizzo, Alunno, Strada, rel_alunno_strada


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def obj2sql(v):
    """Debug: stampa la query SQL con i valori literali."""
    from sqlalchemy.dialects import postgresql
    return str(v.statement.compile(
        dialect=postgresql.dialect(),
        compile_kwargs={"literal_binds": True}
    ))


# ---------------------------------------------------------------------------
# Geo-search API (usata dal pannello admin)
# ---------------------------------------------------------------------------

@bp.route('/search/address', methods=['GET'])
def search_address():
    query = request.args.get('q', '')
    if not query:
        return jsonify([])
    try:
        geolocator = Nominatim(user_agent="amaldiapp")
        locations = geolocator.geocode(query, exactly_one=False,
                                       addressdetails=True, limit=7)
        if locations:
            results = []
            for loc in locations:
                addr = loc.raw.get('address', {})
                results.append({
                    'display_name': loc.address,
                    'road': addr.get('road', ''),
                    'house_number': addr.get('house_number', ''),
                    'postcode': addr.get('postcode', ''),
                    'city': addr.get('city', addr.get('town', '')),
                    'suburb': addr.get('suburb', ''),
                    'type': addr.get('type', ''),
                    'lat': loc.latitude,
                    'lon': loc.longitude,
                })
            return jsonify(results)
    except GeocoderTimedOut:
        return jsonify({'error': 'Timeout durante la ricerca'}), 408
    return jsonify([])


# ---------------------------------------------------------------------------
# Pagine principali
# ---------------------------------------------------------------------------

@bp.route('/')
@bp.route('/index')
def index():
    return render_template('index.html')


@bp.route('/presentazione')
def presentazione():
    return render_template('presentazione.html')


@bp.route('/immagini')
def immagini():
    return render_template('immagini.html')


@bp.route('/voci')
def voci():
    return render_template('voci.html')


@bp.route('/test')
def test():
    return render_template('test.html')


@bp.route('/territorio')
def map_gloglo():
    return render_template('map_territorio.html')


# ---------------------------------------------------------------------------
# Mappe
# ---------------------------------------------------------------------------

@bp.route('/map', methods=['GET', 'POST'])
@bp.route('/mapdata', methods=['GET', 'POST'])
def mapdata():
    conn = db.engine.connect()

    params = [year[0] for year in
              db.session.query(Alunno.anno_ref)
              .distinct()
              .order_by(Alunno.anno_ref.desc())
              .all()]
    param = '1992-1993'
    if request.form and request.form.get('anno') in params:
        param = request.form.get('anno')

    # Punti per heatmap e cluster — query SQL diretta, più affidabile dei GeoAlchemy objects
    geo_rows = conn.execute(text("""
        SELECT s.osm_lat, s.osm_lon, s.osm_road
        FROM strada s
        JOIN rel_alunno_strada ras ON ras.strada_id = s.id
        JOIN alunni a ON a.id = ras.alunno_id
        WHERE s.geom IS NOT NULL
          AND s.osm_lat IS NOT NULL
          AND s.osm_lon IS NOT NULL
          AND a.anno_ref = :p
    """), {"p": param}).fetchall()

    heat_data  = [[r[0], r[1]] for r in geo_rows]
    cluster_data = [{'lat': r[0], 'lon': r[1], 'road': r[2] or ''} for r in geo_rows]

    studenti_nr = Alunno.query.filter(Alunno.anno_ref == param).count()
    address_nr  = len(geo_rows)

    dist_rows = conn.execute(text("""
        WITH distance AS (
            SELECT ST_Distance(
                ST_Transform(s.geom, 3857),
                ST_Transform(ST_SetSRID(ST_Point(12.634917, 41.867626), 4326), 3857)
            ) AS distances
            FROM strada s
            JOIN rel_alunno_strada ras ON ras.strada_id = s.id
            JOIN alunni a ON a.id = ras.alunno_id
            WHERE s.geom IS NOT NULL
              AND s.osm_city = 'Roma'
              AND a.anno_ref = :p
        )
        SELECT PERCENTILE_CONT(0.5) WITHIN GROUP(ORDER BY distances) FROM distance
    """), {"p": param}).fetchall()
    dist_media = dist_rows

    school_markers = _get_school_markers(param)

    # print(f"[mapdata] anno={param} punti={len(geo_rows)} studenti={studenti_nr}")

    return render_template('map_studenti.html',
                           params=params, param=param,
                           request=request.form,
                           studenti_nr=studenti_nr,
                           address_nr=address_nr,
                           dist_media=dist_media,
                           heat_data=heat_data,
                           cluster_data=cluster_data,
                           school_markers=school_markers)


@bp.route('/timemap')
def mapdata_time():
    q = text("""
        SELECT
            a.anno_ref,
            array_agg(array[s.osm_lat, s.osm_lon]),
            array_length(array_agg((s.osm_lat, s.osm_lon)), 1)
        FROM alunni a
        JOIN rel_alunno_strada ras ON ras.alunno_id = a.id
        JOIN strada s ON s.id = ras.strada_id
        WHERE s.geom is not null
        GROUP BY a.anno_ref
        ORDER BY 1
    """)
    conn = db.engine.connect()
    history_data = conn.execute(q).fetchall()

    # Struttura: {anno: [[lat,lon], ...]}
    # r[1] è un array PostgreSQL — convertilo in lista Python
    time_data = {}
    for r in history_data:
        anno = r[0]
        coords = r[1]  # array di array [[lat,lon],...]
        if coords:
            time_data[anno] = [[c[0], c[1]] for c in coords if c[0] and c[1]]
    school_markers = _get_all_school_markers()
    # print(f"[mapdata_time] anni={len(time_data)} primo={list(time_data.keys())[:1]}")

    return render_template('map_studenti_time.html',
                           time_data=time_data,
                           years=sorted(time_data.keys()),
                           school_markers=school_markers)


@bp.route('/map-graph', methods=['GET', 'POST'])
def map_graph():
    params = [year[0] for year in
              db.session.query(Alunno.anno_ref)
              .distinct()
              .order_by(Alunno.anno_ref.desc())
              .all()]
    param = request.form.get('anno') or '1992-1993'

    filters = _build_filters(request.form)
    students_query = (Alunno.query
                      .filter(*([Alunno.anno_ref == param] + filters))
                      .filter(Alunno.strade.any(Strada.geom.isnot(None)))
                      .options(selectinload(Alunno.strade))
                      .all())

    iscritti = db.session.query(Alunno).filter(Alunno.anno_ref == param).count()
    alunni_filtered = len(students_query)

    nation = sorted(set(s.descr_cittadinanza for s in students_query if s.descr_cittadinanza))
    stato_alunno = sorted(set(s.stato_alunno for s in students_query if s.stato_alunno))
    esito = sorted(set(s.esito_finale_norm for s in students_query if s.esito_finale_norm))
    anno_sigla = sorted(set(str(s.anno_sigla) for s in students_query if s.anno_sigla))
    indirizzo = sorted(set(str(s.indirizzo_studi_norm) for s in students_query if s.indirizzo_studi_norm))

    data_cittadinanza = OrderedDict(sorted(
        Counter(s.descr_cittadinanza for s in students_query).items(),
        key=lambda v: v[1], reverse=True
    ))
    data_genere = OrderedDict(Counter(s.sesso for s in students_query))
    data_indirizzo = OrderedDict(Counter(s.indirizzo_studi_norm for s in students_query))
    data_cap = OrderedDict(Counter(s.cap_residenza for s in students_query))

    punti = [
        [strada.osm_lat, strada.osm_lon, strada.osm_road]
        for student in students_query
        for strada in student.strade
        if strada.geom is not None
    ]
    # Dati geo via SQL diretto
    conn = db.engine.connect()
    geo_rows = conn.execute(text("""
        SELECT s.osm_lat, s.osm_lon, s.osm_road
        FROM strada s
        JOIN rel_alunno_strada ras ON ras.strada_id = s.id
        JOIN alunni a ON a.id = ras.alunno_id
        WHERE s.geom IS NOT NULL
          AND s.osm_lat IS NOT NULL
          AND s.osm_lon IS NOT NULL
          AND a.anno_ref = :p
    """), {"p": param}).fetchall()
    heat_data    = [[r[0], r[1]] for r in geo_rows]
    cluster_data = [{'lat': r[0], 'lon': r[1], 'road': r[2] or ''} for r in geo_rows]
    school_markers = _get_school_markers(param)

    # print(f"[map_graph] anno={param} punti={len(geo_rows)} filtrati={alunni_filtered}")

    return render_template('map_graph.html',
                           params=params, param=param, request=request.form,
                           nation=nation, esito=esito, indirizzo=indirizzo,
                           anno_sigla=anno_sigla, qry=students_query,
                           stato_alunno=stato_alunno,
                           chart_cittadinanza=data_cittadinanza,
                           chart_genere=data_genere,
                           chart_indirizzo=data_indirizzo,
                           chart_cap=data_cap,
                           iscritti=iscritti,
                           alunni_filtered=alunni_filtered,
                           heat_data=heat_data,
                           cluster_data=cluster_data,
                           school_markers=school_markers)


# ---------------------------------------------------------------------------
# Serie statistiche
# ---------------------------------------------------------------------------

@bp.route('/serie-generale')
def serie_generale():
    conn = db.engine.connect()

    gender_rows = conn.execute(text(r"""
        SELECT anno_ref,
            array_length(array_agg(id_alunno), 1),
            SUM(CASE WHEN sesso = 'M' THEN 1 END) AS Male,
            SUM(CASE WHEN sesso = 'F' THEN 1 END) AS female,
            count(sesso)
        FROM alunni
        GROUP BY anno_ref ORDER BY anno_ref
    """)).fetchall()
    gender_data = {
        'anni': (x[0] for x in gender_rows),
        'maschi': (x[2] for x in gender_rows),
        'femmine': (x[3] for x in gender_rows),
        'tot': (x[4] for x in gender_rows),
    }

    nation_rows = conn.execute(text(r"""
        SELECT anno_ref,
            array_length(array_agg(id_alunno), 1) as tot,
            SUM(CASE WHEN descr_cittadinanza = 'ITALIANA' THEN 1 END) AS italiana,
            COALESCE(SUM(CASE WHEN descr_cittadinanza != 'ITALIANA' THEN 1 END), 0) AS nonitaliana,
            count(descr_cittadinanza)
        FROM alunni
        GROUP BY anno_ref ORDER BY anno_ref
    """)).fetchall()
    nation_data = {
        'anni': (x[0] for x in nation_rows),
        'iscritti': (x[1] for x in nation_rows),
        'italiani': (x[2] for x in nation_rows),
        'stranieri': (x[3] if x[3] > 0 else 'null' for x in nation_rows),
    }

    indirizzo_rows = conn.execute(text(r"""
        SELECT anno_ref,
            array_length(array_agg(id_alunno), 1) as tot,
            coalesce(SUM(CASE WHEN indirizzo_studi ILIKE '%LINGUIS%' and sesso='M' THEN 1 END),0) AS linguisticoM,
            coalesce(SUM(CASE WHEN indirizzo_studi ILIKE '%LINGUIS%' and sesso='F' THEN 1 END),0) AS linguisticoF,
            coalesce(SUM(CASE WHEN indirizzo_studi ILIKE '%CLASSIC%' and sesso='M' THEN 1 END),0) AS classicoM,
            coalesce(SUM(CASE WHEN indirizzo_studi ILIKE '%CLASSIC%' and sesso='F' THEN 1 END),0) AS classicoF,
            coalesce(SUM(CASE WHEN indirizzo_studi ILIKE '%SCIENTIF%' and sesso='M' THEN 1 END),0) AS scientificoM,
            coalesce(SUM(CASE WHEN indirizzo_studi ILIKE '%SCIENTIF%' and sesso='F' THEN 1 END),0) AS scientificoF,
            coalesce(SUM(CASE WHEN indirizzo_studi ILIKE '%PRIVATI%' and sesso='M' THEN 1 END),0) AS privatistiM,
            coalesce(SUM(CASE WHEN indirizzo_studi ILIKE '%PRIVATI%' and sesso='F' THEN 1 END),0) AS privatistiF,
            count(indirizzo_studi)
        FROM alunni GROUP BY anno_ref ORDER BY anno_ref
    """)).fetchall()
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
        'privatistif': (x[9] if x[9] > 0 else 'null' for x in indirizzo_rows),
    }

    affollamento_rows = conn.execute(text(r"""
        WITH affollamento AS (
            SELECT anno_ref, count(*) as per_classe, anno_sigla, sezione, array_agg(id_alunno)
            FROM alunni
            WHERE sezione !~ 'P'
            GROUP BY anno_ref, anno_sigla, sezione
            ORDER BY anno_ref, anno_sigla, sezione
        )
        SELECT anno_ref, min(per_classe), max(per_classe), round(avg(per_classe))
        FROM affollamento
        GROUP BY anno_ref
        HAVING min(per_classe) > 5
        ORDER BY anno_ref
    """)).fetchall()
    affollamento_data = {
        'anni': [x[0] for x in affollamento_rows],
        'ranges': [[x[0], x[1], x[2]] for x in affollamento_rows],
        'avarages': [[x[0], int(x[3])] for x in affollamento_rows],
    }

    return render_template('serie_generale.html',
                           gender_data=gender_data,
                           nation_data=nation_data,
                           indirizzo_data=indirizzo_data,
                           affollamento_data=affollamento_data)


@bp.route('/serie-indirizzo')
def serie_indirizzo():
    plotbands = r"""
        {color: 'rgba(68, 170, 213, 0.1)', from: 9, to: 14,
          label: {text: '<strong>Succursale</strong><br>Via Oscar Romero',
            style: {color: '#606060'}}},
        {color: 'rgba(68, 170, 213, 0.1)', from: 15, to: 16,
          label: {text: '<strong>Succursale</strong><br>Via Ponti',
            style: {color: '#606060'}}},
        {color: 'rgba(68, 170, 213, 0.1)', from: 21, to: 30,
          label: {text: '<strong>Succursale</strong><br>Via Pietrasecca',
            style: {color: '#606060'}}}
    """
    conn = db.engine.connect()
    indirizzo_rows = conn.execute(text(r"""
        SELECT anno_ref,
            array_length(array_agg(id_alunno), 1) as tot,
            coalesce(SUM(CASE WHEN indirizzo_studi ILIKE '%LINGUIS%' and sesso='M' THEN 1 END),0),
            coalesce(SUM(CASE WHEN indirizzo_studi ILIKE '%LINGUIS%' and sesso='F' THEN 1 END),0),
            coalesce(SUM(CASE WHEN indirizzo_studi ILIKE '%CLASSIC%' and sesso='M' THEN 1 END),0),
            coalesce(SUM(CASE WHEN indirizzo_studi ILIKE '%CLASSIC%' and sesso='F' THEN 1 END),0),
            coalesce(SUM(CASE WHEN indirizzo_studi ILIKE '%SCIENTIF%' and sesso='M' THEN 1 END),0),
            coalesce(SUM(CASE WHEN indirizzo_studi ILIKE '%SCIENTIF%' and sesso='F' THEN 1 END),0),
            coalesce(SUM(CASE WHEN indirizzo_studi ILIKE '%PRIVATI%' and sesso='M' THEN 1 END),0),
            coalesce(SUM(CASE WHEN indirizzo_studi ILIKE '%PRIVATI%' and sesso='F' THEN 1 END),0),
            count(indirizzo_studi)
        FROM alunni GROUP BY anno_ref ORDER BY anno_ref
    """)).fetchall()
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
        'privatistif': [x[9] if x[9] > 0 else 'null' for x in indirizzo_rows],
    }
    return render_template('serie_indirizzo.html',
                           plotbands=plotbands, indirizzo_data=indirizzo_data)


@bp.route('/serie-stato')
def serie_stato():
    plotbands = r"""
        {color: 'rgba(68, 170, 213, 0.1)', from: 9, to: 14,
          label: {text: '<strong>Succursale</strong><br>Via Oscar Romero',
            style: {color: '#606060'}}},
        {color: 'rgba(68, 170, 213, 0.1)', from: 15, to: 16,
          label: {text: '<strong>Succursale</strong><br>Via Ponti',
            style: {color: '#606060'}}},
        {color: 'rgba(68, 170, 213, 0.1)', from: 21, to: 30,
          label: {text: '<strong>Succursale</strong><br>Via Pietrasecca',
            style: {color: '#606060'}}}
    """
    conn = db.engine.connect()

    stato_rows = conn.execute(text(r"""
        SELECT anno_ref,
            array_length(array_agg(id_alunno), 1) as tot,
            coalesce(SUM(CASE WHEN stato_alunno = 'Frequenta' THEN 1 END),0) AS frequenta,
            coalesce(SUM(CASE WHEN stato_alunno = 'Abbandona' THEN 1 END),0) AS abbandona,
            coalesce(SUM(CASE WHEN stato_alunno = 'Trasferito' THEN 1 END),0) AS trasferito,
            count(stato_alunno),
            coalesce(SUM(CASE WHEN stato_alunno='Frequenta' and indirizzo_studi ILIKE '%LINGUIS%' THEN 1 END),0),
            coalesce(SUM(CASE WHEN stato_alunno='Frequenta' and indirizzo_studi ILIKE '%CLASSIC%' THEN 1 END),0),
            coalesce(SUM(CASE WHEN stato_alunno='Frequenta' and indirizzo_studi ILIKE '%SCIENTIF%' THEN 1 END),0),
            coalesce(SUM(CASE WHEN stato_alunno='Abbandona' and indirizzo_studi ILIKE '%LINGUIS%' THEN 1 END),0),
            coalesce(SUM(CASE WHEN stato_alunno='Abbandona' and indirizzo_studi ILIKE '%CLASSIC%' THEN 1 END),0),
            coalesce(SUM(CASE WHEN stato_alunno='Abbandona' and indirizzo_studi ILIKE '%SCIENTIF%' THEN 1 END),0),
            coalesce(SUM(CASE WHEN stato_alunno='Trasferito' and indirizzo_studi ILIKE '%LINGUIS%' THEN 1 END),0),
            coalesce(SUM(CASE WHEN stato_alunno='Trasferito' and indirizzo_studi ILIKE '%CLASSIC%' THEN 1 END),0),
            coalesce(SUM(CASE WHEN stato_alunno='Trasferito' and indirizzo_studi ILIKE '%SCIENTIF%' THEN 1 END),0)
        FROM alunni GROUP BY anno_ref ORDER BY anno_ref
    """)).fetchall()

    stato_data = {
        'anni': [x[0] for x in stato_rows],
        'iscritti': [x[1] for x in stato_rows],
        'frequenta': [x[2] if x[2] > 0 else 'null' for x in stato_rows],
        'abbandona': [x[3] if x[3] > 0 else 'null' for x in stato_rows],
        'trasferito': [x[4] if x[4] > 0 else 'null' for x in stato_rows],
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
        'trasferito_scie': [x[14] if x[14] > 0 else 'null' for x in stato_rows],
    }

    nation_rows = conn.execute(text(r"""
        SELECT anno_ref,
            array_length(array_agg(id_alunno), 1) as tot,
            coalesce(SUM(CASE WHEN descr_cittadinanza = 'ITALIANA' THEN 1 END),0) AS italiana,
            coalesce(SUM(CASE WHEN descr_cittadinanza != 'ITALIANA' THEN 1 END),0) AS nonitaliana,
            coalesce(SUM(CASE WHEN stato_alunno='Abbandona' and descr_cittadinanza='ITALIANA' THEN 1 END),0),
            coalesce(SUM(CASE WHEN stato_alunno='Abbandona' and descr_cittadinanza!='ITALIANA' THEN 1 END),0),
            coalesce(SUM(CASE WHEN stato_alunno='Trasferito' and descr_cittadinanza='ITALIANA' THEN 1 END),0),
            coalesce(SUM(CASE WHEN stato_alunno='Trasferito' and descr_cittadinanza!='ITALIANA' THEN 1 END),0),
            count(descr_cittadinanza)
        FROM alunni
        WHERE anno_ref IN (
            '2001-2002','2002-2003','2003-2004','2004-2005','2005-2006','2006-2007',
            '2007-2008','2008-2009','2009-2010','2010-2011','2011-2012','2012-2013',
            '2013-2014','2014-2015','2015-2016','2016-2017','2017-2018','2018-2019',
            '2019-2020','2020-2021','2021-2022'
        )
        GROUP BY anno_ref ORDER BY anno_ref
    """)).fetchall()
    stato_nation = {
        'anni': [x[0] for x in nation_rows],
        'tot': [x[1] if x[1] > 0 else 'null' for x in nation_rows],
        'ita': [x[2] if x[2] > 0 else 'null' for x in nation_rows],
        'noita': [x[3] if x[3] > 0 else 'null' for x in nation_rows],
        'abb_ita': [x[4] if x[4] > 0 else 'null' for x in nation_rows],
        'abb_no_ita': [x[5] if x[5] > 0 else 'null' for x in nation_rows],
        'tra_ita': [x[6] if x[6] > 0 else 'null' for x in nation_rows],
        'tra_no_ita': [x[7] if x[7] > 0 else 'null' for x in nation_rows],
    }

    return render_template('serie_stato.html',
                           plotbands=plotbands, stato_data=stato_data,
                           stato_indirizzo_data=stato_indirizzo_data,
                           stato_nation=stato_nation)


# ---------------------------------------------------------------------------
# Helpers privati
# ---------------------------------------------------------------------------

def _build_filters(form):
    filters = []
    if form.get('nationalita'):
        filters.append(Alunno.descr_cittadinanza == form.get('nationalita'))
    if form.get('stato_alunno'):
        filters.append(Alunno.stato_alunno == form.get('stato_alunno'))
    if form.get('esito_finale'):
        filters.append(Alunno.esito_finale_norm == form.get('esito_finale'))
    if form.get('anno_sigla'):
        filters.append(Alunno.anno_sigla == form.get('anno_sigla'))
    if form.get('indirizzo_studio'):
        filters.append(Alunno.indirizzo_studi_norm == form.get('indirizzo_studio'))
    return filters

def _get_all_school_markers():
    markers = [
        {
            'lat': 41.867626,
            'lon': 12.634917,
            'popup': '<strong>Liceo Amaldi</strong><br>Via Domenico Parasacchi<br><small>Sede principale</small>',
            'color': '#a61717',
            'type': 'school',
            'name': 'Liceo Amaldi'
        },
        {
            'lat': 41.898976,
            'lon': 12.670868,
            'popup': '<strong>Succursale</strong><br>Via Oscar Romero <br><small>[attiva dal 2001 al 2007]</small>',
            'color': '#5b8fa8',
            'type': 'branch',
            'name': 'Succursale Oscar Romero'
        },
        {
            'lat': 41.869120,
            'lon': 12.577950,
            'popup': '<strong>Succursale</strong><br>Via Ponti <br><small>[attiva tra il 2007 e il 2009]</small>',
            'color': '#5b8fa8',
            'type': 'branch',
            'name': 'Succursale Via Ponti'
        },
        {
            'lat': 41.912905,
            'lon': 12.692475,
            'popup': '<strong>Succursale</strong><br>Via Pietrasecca <br><small>[attiva dal 2013]</small>',
            'color': '#6f42c1',
            'type': 'branch',
            'name': 'Succursale Via Pietrasecca'
        }
    ]
    return markers


def _get_school_markers(param):
    """Restituisce i marker scuola/succursali come lista di dict per Leaflet."""
    markers = [
        {'lat': 41.867626, 'lon': 12.634917,
         'popup': '<strong>Liceo Amaldi</strong><br>Via Domenico Parasacchi',
         'color': '#a61717', 'type': 'school'}
    ]
    if param in ["2001-2002", "2002-2003", "2003-2004",
                 "2004-2005", "2005-2006", "2006-2007"]:
        markers.append({'lat': 41.898976, 'lon': 12.670868,
                        'popup': '<strong>Succursale</strong><br>Via Oscar Romero<br><small>[2001–2007]</small>',
                        'color': '#5b8fa8', 'type': 'branch'})
    if param in ["2007-2008", "2008-2009"]:
        markers.append({'lat': 41.869120, 'lon': 12.577950,
                        'popup': '<strong>Succursale</strong><br>Via Ponti<br><small>[2007–2009]</small>',
                        'color': '#5b8fa8', 'type': 'branch'})
    if param in ["2013-2014", "2014-2015", "2015-2016", "2016-2017",
                 "2017-2018", "2018-2019", "2019-2020", "2020-2021", "2021-2022"]:
        markers.append({'lat': 41.912905, 'lon': 12.692475,
                        'popup': '<strong>Succursale</strong><br>Via Pietrasecca<br><small>attiva dal 2013</small>',
                        'color': '#6f42c1', 'type': 'branch'})
    return markers
