
from django.contrib import admin
from django.urls import path
from app1 import views



urlpatterns =[
    path("", views.index, name='home'),
    path("search_results/", views.search_results, name='search_results'),
    path("about.html", views.about, name='about'),
    path("search", views.search, name='search'),
    path("services", views.services, name='services'),
    path("contact", views.contact, name='contact'),
    path("subjects", views.subjects, name='subjects'),
    path("trainers.html", views.trainers, name='trainers'),
    path("pricing.html", views.pricing, name='pricing'),
    path("base", views.base, name='base'),
    path("registration/",views.registration, name="Registration"),
    path(" ",views.verify,name='verify'),
    path("login/",views.user_login, name="login"),
    path("logout/",views.user_logout, name="logout"),
    path("feedback/",views.feedback, name="feedback"),
    path("berlin-scholarship.html", views.scholarship1),
    path("canada-scholarship.html", views.scholarship2),


    path("program/add/",views.add_current_program, name="current_program"),
    path("field_of_interest/add/",views.add_field_of_interest, name="add_field_of_interest"),


    path("profile/",views.showprofile, name="userprofile"),
    path("category/subject/<str:subject>/",views.category_subjects, name="category_subjects"),
    path("category/degree/<str:degree>/",views.category_degree, name="category_degree"),

    path("profile/edit/",views.showformdata, name="userprofileedit"),
    path("setting/password/edit/",views.password_reset_settings, name="password_reset_settings"),
    path("scholarship/detail/<int:pk>/",views.scholarship_detail, name="scholarship_detail"),
    path("recommendations/",views.my_recommendations, name="my_recommendations"),
    path("history/",views.my_history, name="my_history"),
    path("scholarships.html",views.scholarshipdata, name="scholarships"),
    path("events/<id>",views.scholarshipdatadetial, name="scholarshipsdetail"),
    path("phd-list.html",views.scholarshipdegree1, name="scholarshipone"),
    path("bachelors-list.html",views.scholarshipdegree2, name="scholarshiptwo"),
    path("masters-list.html",views.scholarshipdegree3, name="scholarshipthree"),
]