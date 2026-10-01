"""Print a fresh deployment .env template. Never use example secrets."""
import secrets
print('APP_ENV=production')
print('COOKIE_SECURE=1')
print('SECRET_KEY='+secrets.token_hex(32))
print('SETUP_TOKEN='+secrets.token_urlsafe(32))
print('DOMAIN=finance.example.com')
