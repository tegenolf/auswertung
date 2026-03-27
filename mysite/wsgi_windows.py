import os

import sys

import site

from django.core.wsgi import get_wsgi_application

# Add the app’s directory to the PYTHONPATH

#sys.path.append('C:/Wettkampf/auswertung/mysite')

sys.path.append('C:/Wettkampf/auswertung')

sys.path.append('C:\\Wettkampf\\auswertung')

os.environ['DJANGO_SETTINGS_MODULE'] = 'mysite.settings'

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mysite.settings')

application = get_wsgi_application()