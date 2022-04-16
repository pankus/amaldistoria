import os
import sys
import logging


logging.basicConfig(stream=sys.stderr)
# server produzione
activate_this = '/root/www/amaldistoria/venv/bin/activate_this.py'

# for Python3
with open(activate_this) as file_:
    exec(file_.read(), dict(__file__=activate_this))

sys.stdout = sys.stderr
sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), '../..'))

# server produzione
sys.path.append('/root/www/amaldistoria/')

from amaldiapp import app as application