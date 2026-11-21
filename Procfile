release: python manage.py migrate --noinput && python manage.py createcachetable
web: gunicorn project1.wsgi --workers 1 --threads 4 --timeout 120
