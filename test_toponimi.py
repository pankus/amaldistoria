"""Verifica di app/toponimi.py su casi reali estratti dai file della segreteria.

Nessun framework: `python test_toponimi.py`. Fallisce con un AssertionError
che nomina il caso rotto.
"""

import sys
from collections import namedtuple

sys.path.insert(0, '.')

from app.toponimi import (normalizza, normalizza_cap, abbreviazione_compatibile,
                          refuso_compatibile, correzione_uno, risolvi, norm_esito,
                          norm_sede, norm_indirizzo_studi, chiave, via_pulita,
                          chiave_comune, preposizione_compatibile,
                          troncamento_compatibile, carattere_perduto,
                          spaziatura_compatibile)

Via = namedtuple('Via', 'nome nome_norm comune')


def via(nome, comune='Roma'):
    return Via(nome, chiave(nome), comune)


# Le sei "Bastianelli" che esistono davvero nella Città Metropolitana.
BASTIANELLI = [
    via('Via Giovanni Battista Bastianelli'),
    via('Via Giuseppe Bastianelli', 'Ardea'),
    via('Via Raffaele Bastianelli'),
    via('Via Salvatore Bastianelli', 'Civitavecchia'),
    via('Largo Ezio Bastianelli', 'Ardea'),
    via('Via Bastianelli', 'Colleferro'),
]


def test_normalizza():
    casi = {
        'VIA  G.B.BASTIANELLI, 24': ('VIA', ('G', 'B', 'BASTIANELLI')),
        'VIA G. LONGHI': ('VIA', ('G', 'LONGHI')),
        'VIA MATTE TRUCCO N.71': ('VIA', ('MATTE', 'TRUCCO')),
        'VIA CASALANGUIDA NR.22': ('VIA', ('CASALANGUIDA',)),
        'L.GO FERRUCCIO MENGARONI': ('LARGO', ('FERRUCCIO', 'MENGARONI')),
        'Via di Vermicino, 4, scala A, int. 10': ('VIA', ('DI', 'VERMICINO')),
        'VIA GUGLIELMO CAPPA48': ('VIA', ('GUGLIELMO', 'CAPPA')),
        'VIA GUARDIAGRELE N°10': ('VIA', ('GUARDIAGRELE',)),
        'CASTELVETRANO 72 B': (None, ('CASTELVETRANO',)),
        'VIA COL DI LANA N. 76': ('VIA', ('COL', 'DI', 'LANA')),
        'VIA NAIDE 116 D/2': ('VIA', ('NAIDE',)),
        'Via della Riserva Nuova': ('VIA', ('DELLA', 'RISERVA', 'NUOVA')),
        'VIA CASILINA, 17/26': ('VIA', ('CASILINA',)),
        'Via di Giardinetti 35a': ('VIA', ('DI', 'GIARDINETTI')),
    }
    # L'apostrofo tipografico e quello dritto devono dare lo stesso risultato.
    casi['VIA DELL’EDERA'] = ('VIA', ('DELL', 'EDERA'))
    casi["VIA DELL'EDERA"] = ('VIA', ('DELL', 'EDERA'))
    for grezzo, atteso in casi.items():
        assert normalizza(grezzo) == atteso, f'{grezzo!r} -> {normalizza(grezzo)}, atteso {atteso}'

    # "Via del Piano" non deve perdere il nome: PIANO è rumore solo davanti a una cifra.
    assert normalizza('VIA DEL PIANO')[1] == ('DEL', 'PIANO')

    # `via_pulita` tiene il tipo, `chiave` no: la prima si salva in alunni.via,
    # la seconda serve solo a confrontare.
    assert via_pulita('VIA FONTANA CANDIDA, 98') == 'VIA FONTANA CANDIDA'
    assert via_pulita('L.GO FERRUCCIO MENGARONI') == 'LARGO FERRUCCIO MENGARONI'
    assert via_pulita('CASTELVETRANO 72 B') == 'CASTELVETRANO'
    assert via_pulita('') is None
    assert chiave('VIA FONTANA CANDIDA, 98') == 'FONTANA CANDIDA'


def test_cap():
    assert normalizza_cap('00133') == '00133'
    assert normalizza_cap(' 00132 ') == '00132'
    assert normalizza_cap('000133') is None, 'sei cifre: non si indovina quale togliere'
    assert normalizza_cap('0018') is None, 'quattro cifre: non si indovina quale aggiungere'
    assert normalizza_cap('') is None
    assert normalizza_cap(None) is None
    assert normalizza_cap(133) is None


def test_abbreviazione():
    assert abbreviazione_compatibile(('G', 'LONGHI'), ('GIUSEPPE', 'LONGHI'))
    assert abbreviazione_compatibile(('G', 'B', 'BASTIANELLI'),
                                     ('GIOVANNI', 'BATTISTA', 'BASTIANELLI'))
    assert not abbreviazione_compatibile(('LONGI',), ('LONGO',)), 'cognomi diversi'
    assert not abbreviazione_compatibile(('G', 'LONGHI'), ('GIUSEPPE', 'LONGO'))
    assert not abbreviazione_compatibile(('LONGHI',), ('GIUSEPPE', 'LONGHI')), 'lunghezze diverse'
    assert not abbreviazione_compatibile(('LONGHI',), ('LONGHI',)), 'identici, non abbreviati'


def test_refuso():
    assert refuso_compatibile(('MONTEMILITTO',), ('MONTEMILETTO',)), 'sostituzione interna'
    assert refuso_compatibile(('RAUL', 'CHIODELLI'), ('RAOUL', 'CHIODELLI')), 'inserimento'
    assert refuso_compatibile(('PIETROABBONDANTE',), ('PIETRABBONDANTE',)), 'cancellazione'
    # La vocale finale distingue i cognomi italiani: non è un refuso da correggere.
    assert not refuso_compatibile(('LONGI',), ('LONGO',))
    assert not refuso_compatibile(('ROSSI',), ('ROSSO',))
    assert not refuso_compatibile(('OPI',), ('API',)), 'token troppo corto'
    assert not refuso_compatibile(('MATTE', 'TRUCCO'), ('MONTE', 'TRUCCA')), 'due token diversi'


def test_risolvi():
    # Il caso che motiva tutto il modulo.
    longhi = [via('Via Giuseppe Longhi'), via('Via Longo')]
    e = risolvi(('G', 'LONGHI'), longhi)
    assert e and e.nome == 'Via Giuseppe Longhi' and e.regola == 'abbreviazione', e
    assert risolvi(('LONGI',), longhi) is None, 'LONGI non deve agganciare LONGO'
    # Nemmeno quando "Via Longo" è l'unico candidato in campo.
    assert risolvi(('LONGI',), [via('Via Longo')]) is None

    # Due iniziali distinguono la Bastianelli giusta fra sei.
    e = risolvi(('G', 'B', 'BASTIANELLI'), BASTIANELLI)
    assert e and e.nome == 'Via Giovanni Battista Bastianelli', e

    # Una sola iniziale aggancia solo i candidati con lo stesso numero di token:
    # 'Via Giovanni Battista Bastianelli' ne ha tre, quindi resta fuori.
    e = risolvi(('G', 'BASTIANELLI'), BASTIANELLI)
    assert e and e.nome == 'Via Giuseppe Bastianelli' and e.regola == 'abbreviazione', e

    # Quando due candidati hanno la stessa forma, l'iniziale non basta più.
    omonime = [via('Via Giuseppe Longhi'), via('Via Giovanni Longhi', 'Tivoli')]
    e = risolvi(('G', 'LONGHI'), omonime)
    assert e and e.regola == 'ambigua' and len(e.ambigui) == 2, e

    # Il comune disambigua ciò che l'iniziale non risolve.
    e = risolvi(('G', 'LONGHI'), omonime, comune='Tivoli')
    assert e and e.nome == 'Via Giovanni Longhi', e

    # Lo stesso comune scritto in tre modi deve restare lo stesso comune.
    assert chiave_comune('MONTECOMPATRI') == chiave_comune('Monte Compatri') == \
           chiave_comune('MONTE  COMPATRI')
    sancesareo = [via('Via degli Ulivi', 'San Cesareo'), via('Via degli Ulivi', 'Milano')]
    e = risolvi(('DEGLI', 'ULIVI'), sancesareo, comune='SAN CESAREO')
    assert e and e.regola == 'esatta', e

    # Sottoinsieme: accettato solo se il candidato è unico.
    e = risolvi(('BASTIANELLI',), BASTIANELLI)
    assert e and e.regola == 'esatta' and e.nome == 'Via Bastianelli', e
    e = risolvi(('CHIODELLI',), [via('Via Raoul Chiodelli')])
    assert e and e.regola == 'sottoinsieme', e

    # Refuso corretto solo con candidato unico.
    e = risolvi(('MONTEMILITTO',), [via('Via Montemiletto')])
    assert e and e.regola == 'refuso' and e.nome == 'Via Montemiletto', e

    # Falsa ambiguita' da assorbire: stessa via, grafie diverse in OSM.
    grafie = [via('Via Fontana Delle Cannetacce'), via('Via Fontana delle Cannetacce')]
    e = risolvi(('FONTANA', 'DELLE', 'CANNETACCE'), grafie)
    assert e and e.regola == 'esatta' and e.ambigui == (), e

    # 'S.', "Sant'" e 'Santo' sono lo stesso prefisso: non devono creare ambiguita'.
    andrea = [via('Via Colle S. Andrea Di Sopra'), via("Via Colle Sant'Andrea Di Sopra")]
    e = risolvi(normalizza("VIA COLLE S'ANDREA DI SOPRA 12/L")[1], andrea)
    assert e and e.regola in ('esatta', 'abbreviazione') and e.ambigui == (), e
    assert chiave("Via Sant'Andrea") == chiave('Via S. Andrea') == chiave('Via Santo Andrea')
    # Ma la 'S' isolata resta un'iniziale, non un santo.
    assert chiave('Via S Quasimodo') == 'S QUASIMODO'

    # Vie davvero diverse restano ambigue.
    cisternole = [via('Via delle Cisternole'), via('Vicolo delle Cisternole')]
    e = risolvi(('DELLE', 'CISTERNOLE'), cisternole)
    assert e and e.regola == 'ambigua', e

    assert risolvi(('MODESTA', 'VALENTI'), BASTIANELLI) is None
    assert risolvi((), BASTIANELLI) is None


def test_preposizione():
    """'VIA DEI GIARDINETTI' e 'Via di Giardinetti' sono la stessa via."""
    assert preposizione_compatibile(('DEI', 'GIARDINETTI'), ('DI', 'GIARDINETTI'))
    assert preposizione_compatibile(('DEL', 'MARE'), ('MARE',))
    # Tolte le preposizioni deve restare identico: non e' un lasciapassare
    # per le altre parole.
    assert not preposizione_compatibile(('DEI', 'GIARDINI'), ('DI', 'GIARDINETTI'))
    assert not preposizione_compatibile(('LONGI',), ('LONGO',))
    assert not preposizione_compatibile(('DELLE',), ('DEI',)), 'solo preposizioni: niente'

    e = risolvi(('DEI', 'GIARDINETTI'), [via('Via di Giardinetti')])
    assert e and e.regola == 'preposizione' and e.nome == 'Via di Giardinetti', e
    # Due vie diverse che differiscono solo per la preposizione restano ambigue.
    monti = [via('Via di Monti'), via('Vicolo di Monti')]
    e = risolvi(('DEI', 'MONTI'), monti)
    assert e and e.regola == 'ambigua', e


def test_spaziatura():
    """Cambia solo dove cade lo spazio: nessuna lettera si tocca."""
    assert spaziatura_compatibile(('ROCCA', 'MORICE'), ('ROCCAMORICE',))
    assert spaziatura_compatibile(('ROCCAFIORITA',), ('ROCCA', 'FIORITA')), 'vale nei due sensi'
    assert not spaziatura_compatibile(('ROCCA', 'MORICE'), ('ROCCAMORICI',)), 'una lettera diversa'
    assert not spaziatura_compatibile(('LONGI',), ('LONGO',))
    assert not spaziatura_compatibile(('ROCCAMORICE',), ('ROCCAMORICE',)), 'identici: e\' esatta'

    e = risolvi(('ROCCA', 'MORICE'), [via('Via Roccamorice')])
    assert e and e.regola == 'spaziatura' and e.nome == 'Via Roccamorice', e
    # Se in comune esistono entrambe le grafie come vie diverse, non si sceglie.
    due = [via('Via Roccafiorita'), via('Vicolo Roccafiorita')]
    e = risolvi(('ROCCA', 'FIORITA'), due)
    assert e and e.regola == 'ambigua', e


def test_troncamento():
    """Il punto e' il permesso a confrontare per prefisso; senza, non si fa."""
    assert troncamento_compatibile(('ARCH.', 'DI', 'TORRENOVA'),
                                   ('DEGLI', 'ARCHETTI', 'DI', 'TORRENOVA'))
    assert troncamento_compatibile(('VILLAFRANCA', 'TIRR.'), ('VILLAFRANCA', 'TIRRENA'))
    # Senza punto sarebbe di nuovo LONGI/LONGO, con l'aggravante del prefisso.
    assert not troncamento_compatibile(('ARCH', 'DI', 'TORRENOVA'),
                                       ('DEGLI', 'ARCHETTI', 'DI', 'TORRENOVA'))
    assert not troncamento_compatibile(('LONGI',), ('LONGIANO',))
    # Prefisso troppo corto: 'ARC.' sta a ARCO, ARCHETTI, ARCIPRETE.
    assert not troncamento_compatibile(('ARC.',), ('ARCHETTI',))
    # Il troncamento deve essere un prefisso vero, non una parola diversa.
    assert not troncamento_compatibile(('ARCO.',), ('ARCHETTI',))
    # Il punto va conservato dalla normalizzazione, o il segnale si perde.
    assert normalizza('VIA ARCH. DI TORRENOVA 27') == ('VIA', ('ARCH.', 'DI', 'TORRENOVA'))
    # Ma le iniziali puntate restano iniziali: una lettera non e' un troncamento.
    assert normalizza('VIA  G.B.BASTIANELLI, 24') == ('VIA', ('G', 'B', 'BASTIANELLI'))

    e = risolvi(('ARCH.', 'DI', 'TORRENOVA'), [via('Via degli Archetti di Torrenova')])
    assert e and e.regola == 'troncamento', e


def test_carattere_perduto():
    """Il '?' del mojibake vale una lettera sola, mai una in piu' o in meno."""
    assert carattere_perduto(('MATT?', 'TRUCCO'), ('MATTE', 'TRUCCO'))
    assert not carattere_perduto(('MATT?',), ('MATTEO',)), 'lunghezze diverse'
    assert not carattere_perduto(('MATTE',), ('MATTE',)), 'niente da recuperare'
    e = risolvi(('MATT?', 'TRUCCO'), [via('Via Mattè Trucco')])
    assert e and e.regola == 'carattere perduto' and e.nome == 'Via Mattè Trucco', e


def test_fratelli():
    """'F.LLI' e' un'abbreviazione, non due token."""
    assert normalizza('VIA F.LLI MAZZOCCHI, 75') == ('VIA', ('FRATELLI', 'MAZZOCCHI'))
    assert normalizza('VIA FLLI POGGINI') == ('VIA', ('FRATELLI', 'POGGINI'))
    e = risolvi(('FRATELLI', 'MAZZOCCHI'), [via('Via Fratelli Mazzocchi')])
    assert e and e.regola == 'esatta', e


def test_doppio_tipo():
    """'VIA LARGO FERRUCCIO MENGARONI': il tipo vero e' il secondo."""
    mengaroni = [via('Largo Ferruccio Mengaroni')]
    e = risolvi(('LARGO', 'FERRUCCIO', 'MENGARONI'), mengaroni)
    assert e and e.nome == 'Largo Ferruccio Mengaroni', e
    # Il secondo passaggio compone con le altre regole: 'VIA V.F.BISLERI'.
    e = risolvi(('VIA', 'F', 'BISLERI'), [via('Via Francesco Bisleri')])
    assert e and e.nome == 'Via Francesco Bisleri', e
    # Il token va tolto solo contro i candidati di quel tipo: 61 vie vere
    # cominciano con due tipi e non vanno storpiate.
    assert risolvi(('PONTE', 'LUCANO'), [via('Via Lucano')]) is None
    e = risolvi(('PONTE', 'LUCANO'), [via('Via Ponte Lucano')])
    assert e and e.regola == 'esatta' and e.nome == 'Via Ponte Lucano', e
    # E non deve diventare una scorciatoia per agganciare vie diverse.
    assert risolvi(('LARGO', 'FRANCESCO', 'MENGARONI'), mengaroni) is None


def test_colonne_norm():
    for grezzo in ['AMMESSO/A', 'AMMESSO', "AMMESSO/A ALL'ESAME", 'DIPLOMATO/A',
                   'LICENZIATO/A', 'AMMESSO CON DEROGA ALLA FREQ',
                   "AMMESSO ALL' ESAME DI MATURITÀ"]:
        assert norm_esito(grezzo) == 'AMMESSO', grezzo
    for grezzo in ['NON AMMESSO/A', 'NON AMMESSO PER MANCATA FREQ',
                   "NON AMMESSO ALL' ESAME DI MATURITÀ",
                   'NON AMMESSO  ALLA CLASSE SUCCESSIVA - SCR. IN DEROGA']:
        assert norm_esito(grezzo) == 'NON AMMESSO', grezzo
    assert norm_esito('NON NOTO') == 'NON NOTO'
    for grezzo in ['SOSPENSIONE DEL GIUDIZIO', 'SOSPESO', 'NON IDONEO', '', None]:
        assert norm_esito(grezzo) is None, grezzo

    assert norm_sede('ISTITUTO ISTRUZIONE SUPERIORE E. AMALDI SEDE SUCC.') == 'SUCCURSALE'
    assert norm_sede('ISTITUTO ISTRUZIONE SUPERIORE E. AMALDI') == 'CENTRALE'
    assert norm_sede('LICEO CLASSICO') == 'CENTRALE'
    assert norm_sede('') is None

    assert norm_indirizzo_studi('LINGUISTICO') == 'LINGUISTICO'
    assert norm_indirizzo_studi('LICEO SCIENTIFICO SPERIMENTALE') == 'SCIENTIFICO'
    assert norm_indirizzo_studi('') is None


if __name__ == '__main__':
    fatti = 0
    for nome, fn in sorted(globals().items()):
        if nome.startswith('test_'):
            fn()
            print(f'  ok  {nome}')
            fatti += 1
    print(f'\n{fatti} verifiche passate')
