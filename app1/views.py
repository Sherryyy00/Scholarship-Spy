import logging
from datetime import date
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.core.validators import validate_email
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.dateparse import parse_date
from django.utils.http import url_has_allowed_host_and_scheme

from . import recommender
from .models import (
    Country, Feedback, FieldOfInterest, History, Program, Recommendation,
    Scholarship, TypeOfDegree,
)
from .utils import send_email_token

logger = logging.getLogger(__name__)

PAGE_SIZE = 10
MIN_STATEMENT_LENGTH = 250

# Search form field -> Scholarship lookup
SEARCH_FILTERS = {
    "scholarship_title": "title__icontains",
    "country": "country__icontains",
    "field_of_interest": "subject__icontains",
    "degree": "degree__icontains",
}


# ---------- helpers ----------

def clean_param(value):
    """Treat empty strings, whitespace and the literal 'None' (from old pagination links) as missing."""
    if value is None:
        return None
    value = value.strip()
    return None if value in {"", "None"} else value


def paginate(request, queryset, per_page=PAGE_SIZE):
    """get_page() already falls back to page 1 / last page for bad input."""
    return Paginator(queryset, per_page).get_page(request.GET.get("page"))


def site_subjects():
    """Distinct site-wide subjects (not the ones users added to their own profiles)."""
    return FieldOfInterest.objects.filter(profile__isnull=True).values("name").distinct().order_by("name")


def site_degree_types():
    return TypeOfDegree.objects.filter(profile__isnull=True).values("name").distinct().order_by("name")


def search_dropdowns():
    return {
        "all_field_of_interests": site_subjects(),
        "all_degree_types": site_degree_types(),
        "all_countries": Country.objects.all(),
    }


# ---------- public pages ----------

# Destinations shown on the home page: (display name, search term, photo)
HOME_DESTINATIONS = [
    ("United Kingdom", "United Kingdom", "assets/img/countries/london.jpeg"),
    ("Germany", "Germany", "assets/img/countries/germanyy.jpeg"),
    ("Canada", "Canada", "assets/img/countries/canada.jpeg"),
    ("United States", "United States", "assets/img/countries/usa.jpeg"),
    ("Australia", "Australia", "assets/img/countries/australia.jpeg"),
    ("Japan", "Japan", "assets/img/countries/japan.jpeg"),
]


def site_stats():
    live = Scholarship.objects.all()
    return {
        "scholarships": live.count(),
        "countries": live.exclude(country="").values("country").distinct().count(),
        "subjects": site_subjects().count(),
        "sources": live.values("source").distinct().count(),
    }


def index(request):
    live = Scholarship.objects.all()
    context = search_dropdowns()
    context["all_feedbacks"] = Feedback.objects.select_related("profile__user")[:3]
    context["stats"] = site_stats()
    context["destinations"] = [
        {"name": name, "query": query, "image": image, "count": live.filter(country__icontains=query).count()}
        for name, query, image in HOME_DESTINATIONS
    ]
    return render(request, "app1/index.html", context)


def search_results(request):
    params = {name: clean_param(request.GET.get(name)) for name in SEARCH_FILTERS}
    filters = {SEARCH_FILTERS[name]: value for name, value in params.items() if value}
    if not filters:
        return redirect("home")

    results = Scholarship.objects.filter(**filters)
    context = {
        **params,
        **search_dropdowns(),
        "scholarships": paginate(request, results),
        "number_of_scholarships": results.count(),
    }
    return render(request, "app1/scholarship_results.html", context)


def search(request):
    """Legacy search form (degree + country). Hands off to the main search."""
    query = {
        "degree": clean_param(request.GET.get("degree")) or "",
        "country": clean_param(request.GET.get("query")) or "",
    }
    return redirect(f"{reverse('search_results')}?{urlencode(query)}")


def subjects(request):
    all_subjects = list(site_subjects())
    chunks = [all_subjects[i:i + 15] for i in range(0, len(all_subjects), 15)]
    return render(request, "app1/subjects.html", {"all_subjects": chunks})


def _category(request, template, **lookup):
    results = Scholarship.objects.filter(**lookup)
    return render(request, template, {
        "scholarships": paginate(request, results),
        "number_of_scholarships": results.count(),
    })


def category_subjects(request, subject):
    return _category(request, "app1/category_subjects.html", subject__icontains=subject)


def category_degree(request, degree):
    return _category(request, "app1/category_degree.html", degree__icontains=degree)


def _degree_list(request, template, context_name, degree):
    scholarships = Scholarship.objects.filter(degree__icontains=degree)
    return render(request, template, {context_name: scholarships})


def scholarshipdegree1(request):
    return _degree_list(request, "app1/phd-list.html", "scholarshipone", "phd")


def scholarshipdegree2(request):
    return _degree_list(request, "app1/bachelors-list.html", "scholarshiptwo", "bachelor")


def scholarshipdegree3(request):
    return _degree_list(request, "app1/masters-list.html", "scholarshipthree", "master")


def scholarshipdata(request):
    return render(request, "app1/events.html", {"scholarships": paginate(request, Scholarship.objects.all())})


def scholarship_detail(request, pk):
    return render(request, "app1/scholarship_detail.html", {"scholarship": get_object_or_404(Scholarship.objects, pk=pk)})


def scholarshipdatadetial(request, id):
    # Old URL; the events_detail template never existed. Send people to the real detail page.
    return redirect("scholarship_detail", pk=id)


def base(request):
    return render(request, "app1/base.html")


def trainers(request):
    return render(request, "app1/trainers.html")


def pricing(request):
    return render(request, "app1/pricing.html")


def events(request):
    return render(request, "app1/events.html")


def scholarship1(request):
    return render(request, "app1/berlin-scholarship.html")


def scholarship2(request):
    return render(request, "app1/canada-scholarship.html")


def about(request):
    return render(request, "app1/about.html", {"stats": site_stats()})


def services(request):
    return redirect("about")


def contact(request):
    return redirect("about")


# ---------- accounts ----------

def registration(request):
    if request.method != "POST":
        return render(request, "app1/registration.html")

    username = (request.POST.get("username") or "").strip()
    first_name = (request.POST.get("first_name") or "").strip()
    last_name = (request.POST.get("last_name") or "").strip()
    email = (request.POST.get("email") or "").strip().lower()
    password = request.POST.get("password1") or ""
    confirm_password = request.POST.get("password2") or ""

    errors = []
    if not username:
        errors.append("Please choose a username.")
    elif User.objects.filter(username__iexact=username).exists():
        errors.append("That username is already taken.")
    try:
        validate_email(email)
    except ValidationError:
        errors.append("Please enter a valid email address.")
    else:
        if User.objects.filter(email__iexact=email).exists():
            errors.append("The email you entered already exists.")
    if password != confirm_password:
        errors.append("Passwords do not match.")
    else:
        try:
            validate_password(password, User(username=username, email=email, first_name=first_name))
        except ValidationError as exc:
            errors.extend(exc.messages)

    if errors:
        for error in errors:
            messages.error(request, error)
        return render(request, "app1/registration.html", status=400)

    with transaction.atomic():
        user = User.objects.create_user(
            username=username, email=email, password=password,
            first_name=first_name, last_name=last_name,
        )
    sent = send_email_token(email, user.profile.email_token)
    if sent:
        messages.success(request, "Account created. Check your email for a verification link, then log in.")
    else:
        messages.warning(request, "Account created, but we couldn't send the verification email.")
    return redirect("login")


def verify(request, token):
    from .models import Profile

    profile = Profile.objects.filter(email_token=token).first()
    if profile is None:
        messages.error(request, "That verification link is invalid or has already been used.")
        return redirect("login")
    profile.is_verified = True
    profile.save(update_fields=["is_verified"])
    messages.success(request, "Account verified. You can now log in.")
    return redirect("login")


def user_login(request):
    if request.method == "POST":
        user = authenticate(
            request,
            username=(request.POST.get("username") or "").strip(),
            password=request.POST.get("password") or "",
        )
        if user is not None:
            login(request, user)
            next_url = request.GET.get("next") or request.POST.get("next")
            if next_url and url_has_allowed_host_and_scheme(next_url, {request.get_host()}, request.is_secure()):
                return redirect(next_url)
            return redirect("home")
        messages.error(request, "Invalid username or password.")
    return render(request, "app1/userlogin.html")


def user_logout(request):
    logout(request)
    return redirect("login")


@login_required
def password_reset_settings(request):
    if request.method == "POST":
        user = request.user
        old_password = request.POST.get("old_password") or ""
        new_password = request.POST.get("new_password") or ""
        retype = request.POST.get("retype_new_password") or ""

        if not user.check_password(old_password):
            messages.error(request, "Your current password is incorrect.")
            return redirect("password_reset_settings")
        if new_password != retype:
            messages.error(request, "The new passwords do not match.")
            return redirect("password_reset_settings")
        try:
            validate_password(new_password, user)
        except ValidationError as exc:
            for msg in exc.messages:
                messages.error(request, msg)
            return redirect("password_reset_settings")

        user.set_password(new_password)
        user.save()
        update_session_auth_hash(request, user)  # stay logged in
        messages.success(request, "Password updated.")
        return redirect("userprofile")

    return render(request, "app1/reset_password.html")


# ---------- profile ----------

@login_required
def showprofile(request):
    profile = request.user.profile
    return render(request, "app1/profile.html", {
        "field_of_interest_list": profile.fieldofinterest_set.all(),
        "current_program_list": profile.program_set.order_by("-timestamp"),
    })


def _parse_profile_form(post, user):
    """Validate the edit-profile form. Returns (cleaned_data, errors)."""
    data, errors = {}, []

    for field in ("first_name", "last_name", "highest_qualification", "nationality"):
        value = (post.get(field) or "").strip()
        if value:
            data[field] = value

    email = (post.get("email") or "").strip().lower()
    if email:
        try:
            validate_email(email)
        except ValidationError:
            errors.append("Please enter a valid email address.")
        else:
            if User.objects.filter(email__iexact=email).exclude(pk=user.pk).exists():
                errors.append("That email is already used by another account.")
            else:
                data["email"] = email

    cgpa = (post.get("cgpa") or "").strip()
    if cgpa:
        try:
            value = Decimal(cgpa)
        except InvalidOperation:
            errors.append("CGPA must be a number.")
        else:
            if not Decimal("0") <= value <= Decimal("4"):
                errors.append("CGPA must be between 0 and 4.0.")
            elif value.as_tuple().exponent < -2:
                errors.append("CGPA can have at most 2 digits after the decimal point.")
            else:
                data["cgpa"] = value

    age = (post.get("age") or "").strip()
    if age:
        if age.isdigit() and 10 <= int(age) <= 120:
            data["age"] = int(age)
        else:
            errors.append("Please enter a valid age.")

    dob = (post.get("dob") or "").strip()
    if dob:
        parsed = parse_date(dob)
        if parsed is None or parsed >= date.today():
            errors.append("Please enter a valid date of birth.")
        else:
            data["dob"] = parsed

    return data, errors


@login_required
def showformdata(request):
    """Edit profile. Always edits the logged-in user (the old version trusted a hidden email field)."""
    if request.method != "POST":
        return render(request, "app1/profile_edit.html")

    user, profile = request.user, request.user.profile
    data, errors = _parse_profile_form(request.POST, user)
    if errors:
        for error in errors:
            messages.error(request, error)
        return redirect("userprofileedit")

    with transaction.atomic():
        for field in ("first_name", "last_name", "email"):
            if field in data:
                setattr(user, field, data[field])
        user.save()
        for field in ("highest_qualification", "nationality", "cgpa", "age", "dob"):
            if field in data:
                setattr(profile, field, data[field])
        if request.FILES.get("photo"):
            profile.photo = request.FILES["photo"]
        profile.save()

    messages.success(request, "Profile updated.")
    return redirect("userprofile")


def _add_named_item(request, model, field, template):
    if request.method == "POST":
        name = (request.POST.get(field) or "").strip()
        if not name:
            messages.error(request, "Please enter a value.")
            return redirect(request.path)
        model.objects.get_or_create(name=name[:300], profile=request.user.profile)
        return redirect("userprofile")
    return render(request, template)


@login_required
def add_field_of_interest(request):
    return _add_named_item(request, FieldOfInterest, "fieldOfInterest", "app1/field_of_interest_form.html")


@login_required
def add_current_program(request):
    return _add_named_item(request, Program, "program", "app1/current_program.html")


# ---------- recommendations ----------

def _save_recommendations(history, matches):
    with transaction.atomic():
        Recommendation.objects.filter(history=history).delete()
        Recommendation.objects.bulk_create([
            Recommendation(history=history, scholarship_id=m.scholarship_id, rank=rank, score=m.score)
            for rank, m in enumerate(matches, start=1)
        ])


@login_required
def my_recommendations(request):
    statement = (request.GET.get("statement") or "").strip()
    context = {"personal_statement": statement, "scholarships": ""}

    if not statement:
        return render(request, "app1/recommendations.html", context)

    if len(statement) < MIN_STATEMENT_LENGTH:
        messages.info(request, f"Your statement should be at least {MIN_STATEMENT_LENGTH} characters.")
        return render(request, "app1/recommendations.html", context)

    profile = request.user.profile
    history = History.objects.filter(profile=profile, personal_statement=statement).first()
    is_new = history is None
    if is_new:
        history = History.objects.create(profile=profile, personal_statement=statement)

    # Only recompute on a new statement or the first page, so paging through results is cheap.
    if is_new or not request.GET.get("page"):
        interests = list(profile.fieldofinterest_set.values_list("name", flat=True))
        _save_recommendations(history, recommender.recommend(statement, extra_terms=interests))

    ranked = history.top_scholarships
    if not ranked.exists():
        messages.info(request, "We couldn't find a good match. Try mentioning your subject, degree level and target country.")
    else:
        context["scholarships"] = paginate(request, ranked)
    return render(request, "app1/recommendations.html", context)


@login_required
def my_history(request):
    histories = request.user.profile.history_set.all()
    return render(request, "app1/my_history.html", {"user_history": histories})


# ---------- feedback ----------

@login_required
def feedback(request):
    if request.method == "POST":
        content = (request.POST.get("feedback") or "").strip()
        if not content:
            messages.error(request, "Please write a short message.")
            return redirect("feedback")
        Feedback.objects.create(
            content=content[:500],
            emoji=(request.POST.get("emoji") or "")[:100],
            profile=request.user.profile,
        )
        messages.success(request, "Thanks for your feedback!")
        return redirect("home")
    return render(request, "app1/feedback.html")
