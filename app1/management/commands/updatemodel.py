from django.core.management.base import BaseCommand
import pandas as pd
from app1.models import Scholarship
class Command(BaseCommand):
    help = 'import booms'

    def add_arguments(self, parser):
        pass

    def handle(self, *args, **options):
        df=pd.read_csv('studyportal1.csv')
        for TITLE,LINKS,COUNTRY,DEGREE,APPLYDATE,DESCRIPTION in zip(df.Title,df.Links,df.Country,df.degree,df.apply_date,df.scholarship_details):
            models=Scholarship(title=TITLE,link=LINKS,country=COUNTRY,degree=DEGREE,apply_date=APPLYDATE,scholarship_details=DESCRIPTION)
            models.save()