release: python manage.py migrate --noinput && python manage.py createcachetable
web: gunicorn project1.wsgi --workers 2 --timeout 60
