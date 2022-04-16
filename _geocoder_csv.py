from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
import re
import csv

"""
Script per il geocoding della tablelle amaldi:
 
"""

""" esempio testo per nominatim """
"52, Via dell'Archeologia, Tor Bella Monaca, Municipio Roma VI, Roma, Roma Capitale, Lazio, 00133, Italia" 

dati = [{"indirizzo": "DELL'ARCHEOLOGIA, 52", "cap": "00133", "localita": "Roma, Lazio"},
        {"indirizzo": "VIA A. BARBETTI, 67", "cap": "00133", "localita": "Roma, Lazio"},
        {"indirizzo": "VIA CIRO FERRI, 27", "cap": "00133", "localita": "Roma, Lazio"},
        {"indirizzo": "VIA POSEIDONE, 55", "cap": "00133", "localita": "Roma, Lazio"},
        {"indirizzo": "VIA ANTEO, 34", "cap": "00133", "localita": "Roma, Lazio"},
        {"indirizzo": "VIA GIUSEPPE MARIA BONZANIGO 10", "cap": "00133", "localita": "Roma, Lazio"},
        {"indirizzo": "VIA A. ASPERTINI, 343/A", "cap": "00133", "localita": "Roma, Lazio"},
        {"indirizzo": "VIA RUDERI DI TORRENOVA, 45", "cap": "00133", "localita": "Roma, Lazio"},
        {"indirizzo": "VIA CASILINA 1324", "cap": "00133", "localita": "Roma, Lazio"}]


def clean_address(text):
    
    text = text.replace('L.GO', 'LARGO')
    text = text.replace('LGO', 'LARGO')
    text = text.replace('LOC.', "LOCALITA'")
    text = text.replace('P.ZZA', 'PIAZZA')
    tesxt = text.replace('V.LE', 'VIALE')
    tesxt = text.replace('"', '')
    tesxt = text.replace(',', ' ')
    text = re.sub(r'^S\.', 'SANTA ', text)
    text = re.sub(r'^V\.', 'VIA ', text)
    """ i nomi delle vie con abbreviazioni vanno eliminati """
    text = re.sub(r'(?<=\s)[A-Z]\.\s?', r'', text)
    """ inserisco uno spazio tra nome via e civico """
    text = re.sub(r'(?<=[A-Z])(\d)', r' \1', text)
    """ elimino la grafia N. prima del civico """
    # text = re.sub(r'N\.\s?(\d)', r' \1', text)
    """ separo indirizzo da civico """
    text = re.sub(r'([A-Za-z])(\d)', r'\1 \2', text)
    
    return text

# creiamo un oggeto Nominatim
geolocator = Nominatim(user_agent="amaldistoria_devel2")

geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1)


data, fails = [], []

with open('geodata/dati_2block.csv') as csv_file:

    csv_reader = csv.reader(csv_file, delimiter=',')
    
    for i in csv_reader:
        
        pnt = {}

        dati_indirizzo = clean_address(i[1])
        # dati_indirizzo = i[1]
        dati_cap = i[4]
        dati_localita = "{} {}".format(i[2], i[3])
        indirizzo = "{}, {}, {}".format(dati_indirizzo, dati_cap, dati_localita)

        """ se exactly_one=False ricevo sempre una lista """
        # location = geocode(indirizzo, addressdetails=True, exactly_one=True)
        site = {'postalcode': dati_cap,
                'country': 'Italia',
                'city': dati_localita,
                'street': dati_indirizzo}
        # print(site)
        location = geocode(query=site, addressdetails=True, exactly_one=True)
        
        try:

            # 'address': {'house_number': '52', 'road': "Via dell'Archeologia", 'suburb': 'Tor Bella Monaca', 'city': 'Roma', 'county': 'Roma Capitale', 'state': 'Lazio', 'postcode': '00133', 'country': 'Italia', 'country_code': 'it'}}
            # if dati_cap == location.raw['address']['postcode']:

            # se esiste il civico (raro!)
            
            # pnt['id_alunno'] = i[0]
            pnt['lat'] = location.raw['lat']
            pnt['lon'] = location.raw['lon']
            pnt['house_number'] = location.raw['address']['house_number'] if 'house_number' in location.raw['address'] else 'empty'
            pnt['road'] = location.raw['address']['road'] if 'road' in location.raw['address'] else 'empty'
            pnt['suburb'] = location.raw['address']['suburb'] if 'suburb' in location.raw['address'] else 'empty'
            pnt['city'] = location.raw['address']['city'] if 'city' in location.raw['address'] else 'empty'
            pnt['county'] = location.raw['address']['county'] if 'county' in location.raw['address'] else 'empty'
            pnt['state'] = location.raw['address']['state'] if 'state' in location.raw['address'] else 'empty'
            pnt['postcode'] = location.raw['address']['postcode'] if 'postcode' in location.raw['address'] else 'empty'
            pnt['indirizzo'] = i[0]

            data.append(pnt)
        
        except:
            
            pnt['indirizzo'] = i[0]
            pnt['postalcode'] = dati_cap
            pnt['city'] = dati_localita
            pnt['street'] = dati_indirizzo

            fails.append(pnt)


# print(data)

""" meglio passare meno di 5000 indirizzi alla volta """
with open('geodata/_results_2block.csv', mode='w') as results:
  wrt = csv.writer(results, delimiter=',',
                   quotechar='"', quoting=csv.QUOTE_MINIMAL)
  for row in data:
    wrt.writerow([row['indirizzo'],
                  # row['id_alunno'],
                  row['road'],
                  row['house_number'],
                  row['suburb'],
                  row['city'],
                  row['county'],
                  row['state'],
                  row['postcode'],
                  row['lat'],
                  row['lon']
                  ])

with open('geodata/_errors_2block.csv', mode='w') as errors:
  wrt = csv.writer(errors, delimiter=',',
                   quotechar='"', quoting=csv.QUOTE_MINIMAL)
  for row in fails:
    wrt.writerow( [ row['indirizzo'],
                    row['street'],
                    row['city'],
                    row['postalcode'] ])
