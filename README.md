...
### 1) L'ambiente di sviluppo 
Per prima cosa è necessario creare un `virtualenlv`, un ambiente di sviluppo per Python che ci permetta di introdurre modifiche senza toccare il Python di sistema.
```python
python3 -m venv venv
```
o
```python
virtualenv -p python3 venv
```

Entrambe le soluzioni fanno la stessa cosa, ovvero creano una cartella `venv` in cui verrà installato una versione di Python (in questo caso diciamo esplicitamente di installare Python 3)

Per attivare questo ambiente di sviluppo sarà sufficiente ricorrere al seguente comando

```bash
source ven/bin/activate
```

### 2) Cominciamo ad installare quello che ci serve

Il modo più comodo per installare i pacchetti è `pip`. Per installare Flask useremo il comando:
```python
pip install flask
```

Per comodità ogni progetto Python dovrebbe avere un file di testo chiamato `requirements.txt` con la lista di tutte le componenti necessarie a far eseguire l'applicazione. Quindi piuttosto che installare le singole componenti individualmente sarà sufficiente digitare il seguente comando
```python
pip install -r requirements.txt
```

### 3) Operativi!
Sebbene un'applicazione Flask possa essere costituita da un unico file, il più delle volte conviene isolare le singole componenti dell'applicazione.
Per prima cosa allora creeremo una directory chiamata `amaldiapp` e in questa directory creeremo un file chiamato `__init__.py`. Python interpreterà questa directory come un "pacchetto" (*package*) e dunque si potrà interagire con le varie parti di questo pacchetto nel codice che andremo a realizzare.

```bash
mkdir amaldiapp
```

Il file __init__.py conterrà invece:

```python
from flask import Flask

app = Flask(__name__)

from amaldiapp import views
```