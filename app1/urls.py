from django.contrib.auth import views as auth_views
from django.urls import path

from app1 import views

urlpatterns = [
    # Forgotten password
    path("password/forgot/", views.PasswordResetView.as_view(), name="password_reset"),
    path("password/forgot/sent/", auth_views.PasswordResetDoneView.as_view(
        template_name="app1/password_reset_done.html"), name="password_reset_done"),
    path("password/reset/<uidb64>/<token>/", auth_views.PasswordResetConfirmView.as_view(
        template_name="app1/password_reset_confirm.html"), name="password_reset_confirm"),
    path("password/reset/done/", auth_views.PasswordResetCompleteView.as_view(
        template_name="app1/password_reset_complete.html"), name="password_reset_complete"),

    path("", views.index, name="home"),

    # Search & browse
    path("search_results/", views.search_results, name="search_results"),
    path("search", views.search, name="search"),
    path("subjects", views.subjects, name="subjects"),
    path("category/subject/<str:subject>/", views.category_subjects, name="category_subjects"),
    path("category/degree/<str:degree>/", views.category_degree, name="category_degree"),
    path("scholarships.html", views.scholarshipdata, name="scholarships"),
    path("scholarship/detail/<int:pk>/", views.scholarship_detail, name="scholarship_detail"),
    path("events/<int:id>", views.scholarshipdatadetial, name="scholarshipsdetail"),
    path("phd-list.html", views.scholarshipdegree1, name="scholarshipone"),
    path("bachelors-list.html", views.scholarshipdegree2, name="scholarshiptwo"),
    path("masters-list.html", views.scholarshipdegree3, name="scholarshipthree"),

    # Static-ish pages
    path("about.html", views.about, name="about"),
    path("services", views.services, name="services"),
    path("contact", views.contact, name="contact"),
    path("trainers.html", views.trainers, name="trainers"),
    path("pricing.html", views.pricing, name="pricing"),
    path("base", views.base, name="base"),
    path("berlin-scholarship.html", views.scholarship1),
    path("canada-scholarship.html", views.scholarship2),

    # Accounts
    path("registration/", views.registration, name="Registration"),
    path("verify/<str:token>/", views.verify, name="verify"),
    path("login/", views.user_login, name="login"),
    path("logout/", views.user_logout, name="logout"),
    path("setting/password/edit/", views.password_reset_settings, name="password_reset_settings"),

    # Profile
    path("profile/", views.showprofile, name="userprofile"),
    path("profile/edit/", views.showformdata, name="userprofileedit"),
    path("program/add/", views.add_current_program, name="current_program"),
    path("program/<int:pk>/remove/", views.remove_current_program, name="remove_current_program"),
    path("field_of_interest/add/", views.add_field_of_interest, name="add_field_of_interest"),
    path("field_of_interest/<int:pk>/remove/", views.remove_field_of_interest, name="remove_field_of_interest"),
    path("account/delete/", views.delete_account, name="delete_account"),

    # Recommendations & feedback
    path("recommendations/", views.my_recommendations, name="my_recommendations"),
    path("recommendations/<int:pk>/", views.recommendation_results, name="recommendation_results"),
    path("recommendations/<int:pk>/refresh/", views.rerun_recommendations, name="rerun_recommendations"),
    path("history/", views.my_history, name="my_history"),
    path("history/<int:pk>/delete/", views.delete_history, name="delete_history"),
    path("history/clear/", views.clear_history, name="clear_history"),
    path("feedback/", views.feedback, name="feedback"),

    # Saved scholarships & application tracker
    path("saved/<int:pk>/toggle/", views.toggle_saved, name="toggle_saved"),
    path("applications/", views.my_applications, name="my_applications"),
    path("applications/<int:pk>/update/", views.update_application, name="update_application"),
    path("applications/<int:pk>/remove/", views.remove_application, name="remove_application"),
    path("reminders/unsubscribe/<str:token>/", views.unsubscribe_reminders, name="unsubscribe_reminders"),
]
