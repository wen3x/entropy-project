"""
WSGI config for entropy project.
"""

import os

from django.core.wsgi import get_wsgi_application
from whitenoise import WhiteNoise

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'entropy.settings')

application = WhiteNoise(get_wsgi_application())
