"""Normalizzazione dei toponimi e risoluzione delle vie contro lo stradario.

Logica pura: nessuna dipendenza da Flask, dal DB o dalla rete, così è
verificabile da sola (vedi test_toponimi.py nella radice del progetto).

Il problema che questo modulo risolve: gli indirizzi arrivano dalla segreteria
scritti a mano ("VIA G. LONGHI", "VIA  G.B.BASTIANELLI, 24", "VIA MATTE TRUCCO
N.71") e vanno ricondotti al nome reale della via. Il confronto per similarità
di stringa NON funziona, perché classifica la coppia sbagliata sopra quella
giusta:

    0.750  'VIA G. LONGHI'  vs 'VIA GIUSEPPE LONGHI'   <- giusto
    0.889  'VIA LONGI'      vs 'VIA LONGO'             <- sbagliato

Si confronta quindi per token, espandendo le iniziali contro un elenco di vie
reali (lo stradario OSM).
"""

import re
import unicodedata
from collections import namedtuple

# Tipi di toponimo riconosciuti come prefisso ("VIA", "LARGO", ...).
TIPI = {
    'VIA', 'VIALE', 'PIAZZA', 'PIAZZALE', 'LARGO', 'LARGHETTO', 'VICOLO',
    'CORSO', 'LUNGOTEVERE', 'CIRCONVALLAZIONE', 'BORGO', 'STRADA', 'PARCO',
    'CONTRADA', 'LOCALITA', 'SALITA', 'DISCESA', 'GALLERIA', 'CLIVO', 'PONTE',
    'PASSEGGIATA', 'PIAZZETTA', 'TRAVERSA', 'VILLAGGIO', 'BANCHINA', 'LUNGOMARE',
}

# Sigle da espandere prima di spezzare i punti, altrimenti "L.GO" diventa "L GO".
SIGLE = {
    'V': 'VIA', 'V.': 'VIA',
    'V.LE': 'VIALE', 'VLE': 'VIALE', 'VL': 'VIALE',
    'L.GO': 'LARGO', 'LGO': 'LARGO', 'LG': 'LARGO',
    'P.ZZA': 'PIAZZA', 'P.ZA': 'PIAZZA', 'PZZA': 'PIAZZA', 'PZA': 'PIAZZA',
    'P.LE': 'PIAZZALE', 'PLE': 'PIAZZALE', 'P.LLE': 'PIAZZALE',
    'C.SO': 'CORSO', 'CSO': 'CORSO',
    'V.LO': 'VICOLO', 'VLO': 'VICOLO',
    'LUNGOT': 'LUNGOTEVERE', 'LUNGOT.': 'LUNGOTEVERE',
    'CIRC.NE': 'CIRCONVALLAZIONE', 'CIRC': 'CIRCONVALLAZIONE',
    'LOC': 'LOCALITA', 'LOC.': 'LOCALITA',
    'F.LLI': 'FRATELLI', 'FLLI': 'FRATELLI', 'F.LL': 'FRATELLI',
    # Prefisso agiografico: 'S.', 'San', "Sant'", 'Santo', 'Santa' e 'Santi'
    # sono la stessa cosa per il confronto, e OSM li alterna sulla stessa via.
    # La 'S' isolata resta fuori: puo' essere l'iniziale di un nome proprio
    # (Via S. Quasimodo), e come iniziale la tratta gia' la regola di abbreviazione.
    'S.': 'SAN', 'SS.': 'SAN', 'SS': 'SAN', 'SANT': 'SAN', 'SANT.': 'SAN',
    'SANTO': 'SAN', 'SANTA': 'SAN', 'SANTI': 'SAN', 'SANTE': 'SAN',
}

# Marcatori del numero civico: terminano il nome della via, ma solo se seguiti
# da una cifra. Senza questo vincolo "VIA DEL PIANO" perderebbe il suo nome.
RUMORE = {
    'N', 'NR', 'NUM', 'NUMERO', 'CIV', 'CIVICO', 'INT', 'INTERNO', 'SC',
    'SCALA', 'PIANO', 'PAL', 'PALAZZINA', 'PALAZZO', 'EDIFICIO', 'EDIF',
    'LOTTO', 'SNC', 'ISOLATO', 'COMPRENSORIO', 'KM',
}

# Lunghezza minima di un token perché sia lecito correggerne un refuso.
# Sotto questa soglia una singola lettera diversa cambia quasi sempre parola
# ("OPI" / "API"), quindi il caso va in revisione umana.
MIN_TOKEN_REFUSO = 5

# Preposizioni ignorate nel confronto: la segreteria scrive 'VIA DEI
# GIARDINETTI' dove OSM ha 'Via di Giardinetti'. Sono l'unica classe di parole
# che si puo' togliere senza cambiare di quale via si parla.
PREPOSIZIONI = {
    'DI', 'DEL', 'DELLO', 'DELLA', 'DEI', 'DEGLI', 'DELLE', 'DELL',
    'DA', 'DAL', 'DALLO', 'DALLA', 'DAI', 'DAGLI', 'DALLE',
    'AL', 'ALLO', 'ALLA', 'AI', 'AGLI', 'ALLE',
}

# Lunghezza minima della parte scritta di un troncamento ('ARCH.' -> 4).
# Sotto, il prefisso non discrimina: 'ARC.' sta a ARCO, ARCHETTI e ARCIPRETE.
MIN_TRONCAMENTO = 4

Esito = namedtuple('Esito', 'nome regola ambigui')


# ---------------------------------------------------------------------------
# Normalizzazione
# ---------------------------------------------------------------------------

def _senza_accenti(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s)
                   if unicodedata.category(c) != 'Mn')


def _token_grezzi(indirizzo):
    s = _senza_accenti(str(indirizzo)).upper()
    # Apostrofi dritti e tipografici trattati allo stesso modo, su entrambi i
    # lati del confronto: DELL'EDERA e Via dell'Edera devono coincidere.
    s = re.sub(r"[‘’ʼ`´']", ' ', s)
    s = s.replace('N°', ' N ').replace('Nº', ' N ')
    # Tutto ciò che segue una virgola o un punto e virgola è civico o dettaglio
    # di accesso ("Via di Vermicino, 4, scala A, int. 10").
    s = re.split(r'[,;]', s)[0]

    fuori = []
    for grezzo in s.split():
        chiave = grezzo.strip('-')
        if chiave in SIGLE:
            fuori.append(SIGLE[chiave])
            continue
        if re.fullmatch(r'[A-Z]{%d,}\.' % MIN_TRONCAMENTO, chiave):
            # 'ARCH.', 'TIRR.': il punto e' l'unico segnale che la parola e'
            # tagliata, e va conservato. Le iniziali puntate ('G.B.') restano
            # invece spezzate qui sotto: una lettera sola non e' un troncamento.
            fuori.append(chiave)
            continue
        pezzo = grezzo.replace('.', ' ')
        pezzo = re.sub(r'(?<=[A-Z])(?=\d)', ' ', pezzo)   # CAPPA48 -> CAPPA 48
        pezzo = re.sub(r'(?<=\d)(?=[A-Z])', ' ', pezzo)   # 35A     -> 35 A
        for t in pezzo.split():
            t = t.strip('-/')
            if t:
                fuori.append(SIGLE.get(t, t))
    return fuori


def normalizza(indirizzo):
    """'VIA  G.B.BASTIANELLI, 24' -> ('VIA', ('G', 'B', 'BASTIANELLI'))

    Il tipo è None quando l'indirizzo non lo dichiara ('CASTELVETRANO 72 B',
    che nei file della segreteria capita spesso).
    """
    if not indirizzo:
        return None, ()
    grezzi = _token_grezzi(indirizzo)
    tipo = None
    if grezzi and grezzi[0] in TIPI:
        tipo, grezzi = grezzi[0], grezzi[1:]

    nome = []
    for i, t in enumerate(grezzi):
        if t[0].isdigit():
            break
        seguito_da_cifra = i + 1 < len(grezzi) and grezzi[i + 1][0].isdigit()
        if t in RUMORE and seguito_da_cifra:
            break
        nome.append(t)
    return tipo, tuple(nome)


def chiave(indirizzo):
    """Chiave di confronto: i soli token del nome, senza il tipo.

    Il tipo resta fuori perche' la segreteria lo omette spesso
    ('CASTELVETRANO 72 B') e a volte lo sbaglia: non puo' far fallire un
    confronto altrimenti corretto.
    """
    return ' '.join(normalizza(indirizzo)[1])


def via_pulita(indirizzo):
    """La via ripulita da salvare in `alunni.via`, tipo compreso quando c'e'.

    'VIA FONTANA CANDIDA, 98' -> 'VIA FONTANA CANDIDA'
    'CASTELVETRANO 72 B'      -> 'CASTELVETRANO'
    """
    tipo, nome = normalizza(indirizzo)
    if not nome:
        return None
    return ' '.join(([tipo] if tipo else []) + list(nome))


def chiave_comune(nome):
    """Confronto fra comuni insensibile a spazi, accenti e punteggiatura.

    Lo stesso comune e' scritto 'MONTECOMPATRI' in `alunni`, 'MONTE COMPATRI'
    nei file della segreteria e 'Monte Compatri' in OpenStreetMap.
    """
    if not nome:
        return ''
    return re.sub(r'[^A-Z]', '', _senza_accenti(str(nome)).upper())


def normalizza_cap(cap):
    """CAP a 5 cifre, oppure None se il dato è inutilizzabile.

    Nei file arrivano '000133' (6 cifre) e '0018' (4): non si indovina quale
    cifra sia di troppo o quale manchi, quindi si rinuncia al CAP e si segnala.
    """
    if cap is None:
        return None
    cifre = re.sub(r'\D', '', str(cap))
    return cifre if len(cifre) == 5 else None


# ---------------------------------------------------------------------------
# Regole di risoluzione, dalla più sicura alla più rischiosa
# ---------------------------------------------------------------------------

def abbreviazione_compatibile(query, candidato):
    """('G', 'LONGHI') contro ('GIUSEPPE', 'LONGHI') -> True.

    Stessa lunghezza; ogni token o è identico, o è una singola lettera che è
    l'iniziale del token corrispondente. ('LONGI',) contro ('LONGO',) è False:
    nessuna abbreviazione, cognomi diversi.
    """
    if len(query) != len(candidato):
        return False
    almeno_una = False
    for a, b in zip(query, candidato):
        if a == b:
            continue
        if len(a) == 1 and b.startswith(a):
            almeno_una = True
            continue
        return False
    return almeno_una


def correzione_uno(a, b):
    """Che tipo di correzione singola porta da `a` a `b`, se ne basta una.

    Distingue l'inserimento e la sostituzione interna (refusi di battitura)
    dalla sostituzione dell'ultimo carattere, che in italiano non è un refuso
    ma un cognome diverso: Longi/Longo, Rossi/Rosso, Bianchi/Bianco.
    """
    if a == b:
        return None
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return None
    if la == lb:
        diversi = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
        if len(diversi) != 1:
            return None
        return 'sostituzione-finale' if diversi[0] == la - 1 else 'sostituzione-interna'
    if la > lb:
        a, b, la = b, a, lb
    i = 0
    while i < la and a[i] == b[i]:
        i += 1
    return 'inserimento' if a[i:] == b[i + 1:] else None


def refuso_compatibile(query, candidato):
    """Un solo token diverso, per un solo carattere, e non l'ultimo.

    'RAUL' -> 'RAOUL' (inserimento) e 'MONTEMILITTO' -> 'MONTEMILETTO'
    (sostituzione interna) passano. 'LONGI' -> 'LONGO' no: cambia la vocale
    finale, che è ciò che distingue due cognomi italiani invece di storpiarne
    uno. I token corti restano esclusi perché lì una lettera cambia parola.
    """
    if len(query) != len(candidato):
        return False
    diversi = [(a, b) for a, b in zip(query, candidato) if a != b]
    if len(diversi) != 1:
        return False
    a, b = diversi[0]
    if max(len(a), len(b)) < MIN_TOKEN_REFUSO:
        return False
    return correzione_uno(a, b) in ('inserimento', 'sostituzione-interna')


def _senza_preposizioni(token):
    return tuple(t for t in token if t not in PREPOSIZIONI)


def preposizione_compatibile(query, candidato):
    """('DEI', 'GIARDINETTI') contro ('DI', 'GIARDINETTI') -> True.

    Uguali una volta tolte le preposizioni. Non tocca le altre parole: se
    quello che resta non coincide token per token, non e' la stessa via.
    """
    q = _senza_preposizioni(query)
    return bool(q) and q == _senza_preposizioni(candidato)


def spaziatura_compatibile(query, candidato):
    """('ROCCA', 'MORICE') contro ('ROCCAMORICE',) -> True.

    Nessuna lettera cambia: cambia solo dove cade lo spazio. Le vie di
    Torrenova portano nomi di comuni ('Roccamorice', 'Poggioreale',
    'Nardodipace') e la segreteria li scrive staccati. Vale nei due sensi,
    perche' OSM a volte stacca dove la segreteria attacca.
    """
    if query == candidato:
        return False                      # identici: se ne occupa 'esatta'
    return ''.join(query) == ''.join(candidato)


def _troncato(a, b):
    """'ARCH.' contro 'ARCHETTI' -> True; 'ARCH' contro 'ARCHETTI' -> False.

    Il punto e' il permesso a confrontare per prefisso, e senza permesso non
    si confronta: 'LONGI' non deve agganciare 'LONGIANO'.
    """
    return (a.endswith('.') and len(a) - 1 >= MIN_TRONCAMENTO
            and len(b) > len(a) - 1 and b.startswith(a[:-1]))


def troncamento_compatibile(query, candidato):
    """'ARCH. DI TORRENOVA' contro 'degli Archetti di Torrenova' -> True.

    Ogni token o e' identico, o e' la sua abbreviazione col punto. Le
    preposizioni restano fuori dal conto da entrambe le parti, perche' e'
    proprio dove le due scritture divergono ('ARCH. DI' / 'degli ARCHETTI di').
    """
    q, c = _senza_preposizioni(query), _senza_preposizioni(candidato)
    if not q or len(q) != len(c):
        return False
    almeno_uno = False
    for a, b in zip(q, c):
        if a == b:
            continue
        if _troncato(a, b):
            almeno_uno = True
            continue
        return False
    return almeno_uno


def carattere_perduto(query, candidato):
    """'MATT?' contro 'MATTE' -> True: il '?' e' una lettera accentata persa.

    Vale come jolly per un carattere solo, mai per una lettera in piu' o in
    meno: la lunghezza deve coincidere.
    """
    if len(query) != len(candidato):
        return False
    almeno_uno = False
    for a, b in zip(query, candidato):
        if a == b:
            continue
        if ('?' in a and len(a) == len(b)
                and all(x == y or x == '?' for x, y in zip(a, b))):
            almeno_uno = True
            continue
        return False
    return almeno_uno


# Dalla piu' sicura alla piu' rischiosa: si ferma alla prima che aggancia.
REGOLE = (
    ('esatta', lambda q, c: q == c),
    ('spaziatura', spaziatura_compatibile),
    ('preposizione', preposizione_compatibile),
    ('abbreviazione', abbreviazione_compatibile),
    ('sottoinsieme', lambda q, c: set(q) < set(c)),
    ('refuso', refuso_compatibile),
    ('carattere perduto', carattere_perduto),
    ('troncamento', troncamento_compatibile),
)


def risolvi(nome, candidati, comune=None):
    """Risolve i token di una via contro un elenco di candidati.

    `candidati` è una sequenza di oggetti con almeno gli attributi `nome`
    (denominazione ufficiale) e `nome_norm` (token uniti da spazio); chi chiama
    ha già ristretto l'elenco, tipicamente indicizzando per ultimo token.
    `comune`, se passato, scarta i candidati di altri comuni.

    Ritorna un Esito, oppure None se nessuna regola aggancia. Quando restano
    più candidati l'Esito ha `nome` a None e `regola` 'ambigua': la scelta non
    si inventa, il caso va in coda di revisione.
    """
    if not nome or not candidati:
        return None

    if comune:
        c = chiave_comune(comune)
        filtrati = [x for x in candidati
                    if not getattr(x, 'comune', None)
                    or chiave_comune(x.comune) == c]
        if filtrati:
            candidati = filtrati

    tok = {x: tuple(x.nome_norm.split()) for x in candidati}
    tipi = {x: normalizza(x.nome)[0] for x in candidati}

    esito = _applica(nome, candidati, tok, tipi)
    if esito is None and len(nome) > 1 and nome[0] in TIPI:
        # 'VIA LARGO FERRUCCIO MENGARONI': la segreteria antepone 'VIA' a un
        # toponimo che il suo tipo ce l'ha gia'. Si riprova senza quel primo
        # token, ma solo contro i candidati proprio di quel tipo: 61 vie vere
        # dello stradario cominciano con due tipi ('Via Ponte Lucano', 'Via
        # Piazza Armerina') e togliere il secondo le storpierebbe.
        stessi = [x for x in candidati if tipi[x] == nome[0]]
        if stessi:
            esito = _applica(nome[1:], stessi, tok, tipi)
    return esito


def _applica(nome, candidati, tok, tipi):
    """Le regole in ordine, sul primo insieme di vincitori che si forma."""
    if not nome:
        return None
    for regola, test in REGOLE:
        vinti = [x for x in candidati if test(nome, tok[x])]
        if not vinti:
            continue
        scelto = _unico(vinti, tok, tipi)
        if scelto is not None:
            return Esito(scelto.nome, regola, ())
        return Esito(None, 'ambigua', tuple(sorted({x.nome for x in vinti})))
    return None


def _unico(vinti, tok, tipi):
    """Il candidato vincente, se i vincitori sono tutti la stessa via.

    Assorbe due false ambiguita' frequenti in OSM: la stessa via con maiuscole
    diverse ('Via Fontana Delle Cannetacce' / 'Via Fontana delle Cannetacce') e
    la stessa via una volta abbreviata e una estesa (tenendo la forma estesa).

    Il tipo pero' conta: 'Via delle Cisternole' e 'Vicolo delle Cisternole'
    hanno gli stessi token e sono due strade diverse, quindi restano ambigue.
    """
    if len({tipi[x] for x in vinti}) > 1:
        return None
    forme = {tok[x] for x in vinti}
    if len(forme) == 1:
        return vinti[0]
    for a in forme:
        for b in forme:
            if a != b and not (abbreviazione_compatibile(a, b)
                               or abbreviazione_compatibile(b, a)):
                return None
    return max(vinti, key=lambda x: sum(len(t) for t in tok[x]))


# ---------------------------------------------------------------------------
# Colonne "_norm" di alunni
# ---------------------------------------------------------------------------

def norm_esito(valore):
    """Coerente con le 43.705 righe già presenti in DB.

    SOSPENSIONE DEL GIUDIZIO, SOSPESO, NON IDONEO e il vuoto restano non
    mappati, com'è oggi: non sono esiti finali.
    """
    if not valore:
        return None
    v = _senza_accenti(str(valore)).upper().strip()
    if v.startswith('NON AMMESS'):
        return 'NON AMMESSO'
    if v.startswith('AMMESS') or v.startswith('DIPLOMAT') or v.startswith('LICENZIAT'):
        return 'AMMESSO'
    if v == 'NON NOTO':
        return 'NON NOTO'
    return None


def norm_sede(valore):
    if not valore:
        return None
    return 'SUCCURSALE' if 'SUCC' in str(valore).upper() else 'CENTRALE'


def norm_indirizzo_studi(valore):
    if not valore:
        return None
    v = _senza_accenti(str(valore)).upper()
    for chiave_, esito in (('LINGUIS', 'LINGUISTICO'), ('CLASSIC', 'CLASSICO'),
                           ('SCIENTIF', 'SCIENTIFICO'), ('PRIVATI', 'PRIVATISTI')):
        if chiave_ in v:
            return esito
    return None
