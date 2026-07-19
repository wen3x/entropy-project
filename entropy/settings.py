import os
import dj_database_url
from pathlib import Path
from django.urls import reverse_lazy
from dotenv import load_dotenv

# 1. Загрузка окружения
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(os.path.join(BASE_DIR, '.env'))

# 2. Основные настройки из .env
SECRET_KEY = os.getenv('SECRET_KEY')
DEBUG = os.getenv('DEBUG') == 'True'

_allowed = os.getenv('ALLOWED_HOSTS', '*')
ALLOWED_HOSTS = [h.strip() for h in _allowed.split(',') if h.strip()]

# 3. Приложения
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles', # Для работы стилей
    'cloudinary',
    'accounts',
    'forum',
]

# 4. Middleware (добавлен WhiteNoise для деплоя)
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware', # Должен быть вторым!
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'accounts.middleware.VitalityMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'accounts.middleware.DailyStreakMiddleware',
    'accounts.middleware.BanMiddleware',
    'accounts.middleware.OnlineUsersMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'entropy.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'accounts.context_processors.site_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'entropy.wsgi.application'

# 5. База данных
DATABASES = {
    'default': dj_database_url.config(
        default=os.environ.get('DATABASE_URL', 'sqlite:///' + str(BASE_DIR / 'db.sqlite3')),
        conn_max_age=600
    )
}

# 6. Валидация паролей
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# 7. Локализация
LANGUAGE_CODE = 'ru'
TIME_ZONE = 'Europe/Moscow'
USE_I18N = True
USE_TZ = True

# 8. СТАТИКА (Критично для деплоя)
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Настройка WhiteNoise для сжатия и долгого кэширования
STATICFILES_STORAGE = 'whitenoise.storage.CompressedStaticFilesStorage'

# 9. Пользователи и редиректы
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
AUTH_USER_MODEL = 'accounts.User'

LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = reverse_lazy('forum:post_list')
LOGOUT_REDIRECT_URL = reverse_lazy('forum:post_list')
# ── 10. CSRF ───────────────────────────────────────────────────────────────────
_csrf_raw = os.getenv('CSRF_TRUSTED_ORIGINS', '')
CSRF_TRUSTED_ORIGINS = [h.strip() for h in _csrf_raw.split(',') if h.strip().startswith('http')]
# Fallback для Render / Replit
_replit_domain = os.getenv('REPLIT_DEV_DOMAIN')
if _replit_domain:
    CSRF_TRUSTED_ORIGINS.append(f'https://{_replit_domain}')
_replit_domains = os.getenv('REPLIT_DOMAINS', '')
for _d in _replit_domains.split(','):
    _d = _d.strip()
    if _d:
        CSRF_TRUSTED_ORIGINS.append(f'https://{_d}')

# ── 11. Администратор ─────────────────────────────────────────────────────────
GOD_USERNAME = os.getenv('GOD_USERNAME', 'admin')

# ── 12. Donation Alerts ───────────────────────────────────────────────────────
DONATION_ALERTS_URL = os.getenv('DONATION_ALERTS_URL', '')

# ── 13. Web Push (VAPID) ───────────────────────────────────────────────────────
WEBPUSH_VAPID_PUBLIC_KEY = os.getenv('WEBPUSH_VAPID_PUBLIC_KEY', '')
WEBPUSH_VAPID_PRIVATE_KEY = os.getenv('WEBPUSH_VAPID_PRIVATE_KEY', '')
WEBPUSH_VAPID_CLAIMS = {
    'sub': 'mailto:admin@entropy.local',
}

# ── Cloudinary ───────────────────────────────────────────────────────────────
CLOUDINARY_CLOUD_NAME = os.getenv('CLOUDINARY_CLOUD_NAME', '')
CLOUDINARY_API_KEY = os.getenv('CLOUDINARY_API_KEY', '')
CLOUDINARY_API_SECRET = os.getenv('CLOUDINARY_API_SECRET', '')

if CLOUDINARY_CLOUD_NAME and CLOUDINARY_API_KEY and CLOUDINARY_API_SECRET:
    import cloudinary
    cloudinary.config(
        cloud_name=CLOUDINARY_CLOUD_NAME,
        api_key=CLOUDINARY_API_KEY,
        api_secret=CLOUDINARY_API_SECRET,
        secure=True,
    )

# ── 15. Cron ───────────────────────────────────────────────────────────────────
CRON_SECRET_TOKEN = os.getenv('CRON_SECRET_TOKEN', '')