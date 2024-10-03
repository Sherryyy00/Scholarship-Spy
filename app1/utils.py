import requests
import json
from django.conf import settings
from django.core.mail import send_mail

def get_all_countries():
    url = "https://restcountries.com/v3.1/all"

    response = requests.get(url)

    countries_response_json = json.loads(response.text)

    countries_list = []

    for country in countries_response_json:
        countries_list.append(country['name']['common'])


    return sorted(countries_list)

def send_email_token(email,token):
    try:
        subject = 'Account Verification'
        message = f'Click on the link to verify http://127.0.0.1:8000/verify/{token}/'
        email_from = settings.EMAIL_HOST_USER
        recipient_list = [email, ]
        send_mail( subject, message, email_from, recipient_list )
                
        
    except Exception as e:
        return False
    
    return True