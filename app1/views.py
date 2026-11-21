import logging
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core import signing
from django.conf import settings
from django.contrib.auth import views as auth_views
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import Count, F, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from . import eligibility as elig
from . import geo, recommender
from .models import (
    Country, Feedback, FieldOfInterest, History, Program, Recommendation,
    SavedScholarship, Scholarship, TypeOfDegree,
)
from .uploads import extract_cv_text, process_profile_photo, suggested_degree
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


SORT_OPTIONS = [("", "Relevance / A–Z"), ("deadline", "Closing soon"), ("newest", "Recently added")]


def apply_eligible_filter(request, queryset):
    """?eligible=1 hides scholarships the logged-in user clearly can't apply for."""
    if request.GET.get("eligible") == "1" and request.user.is_authenticated:
        return queryset.exclude(pk__in=elig.blocked_ids(queryset, request.user.profile)), True
    return queryset, False


def apply_sort(request, queryset):
    """Sort a scholarship queryset from ?sort=. 'Closing soon' puts open, dated listings first."""
    sort = request.GET.get("sort", "")
    if sort == "deadline":
        today = timezone.localdate()
        return queryset.filter(Q(deadline__gte=today) | Q(deadline__isnull=True)).order_by(
            F("deadline").asc(nulls_last=True), "title"), sort
    if sort == "newest":
        return queryset.order_by("-created_at"), sort
    return queryset, ""


def search_dropdowns():
    return {
        "all_field_of_interests": site_subjects(),
        "all_degree_types": site_degree_types(),
        "all_countries": Country.objects.all(),
    }


# ---------- public pages ----------

# Destinations the home page can show: (display name, search term, photo).
# Only those with live scholarships are shown, busiest first.
HOME_DESTINATIONS = [
    ("Europe (Erasmus Mundus)", "Europe", "assets/img/countries/switz.jpeg"),
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
    context["all_feedbacks"] = Feedback.objects.filter(is_approved=True).select_related("profile__user")[:3]
    context["stats"] = site_stats()
    destinations = [
        {"name": name, "query": query, "image": image, "count": live.filter(country__icontains=query).count()}
        for name, query, image in HOME_DESTINATIONS
    ]
    context["destinations"] = sorted((d for d in destinations if d["count"]), key=lambda d: -d["count"])[:6]
    return render(request, "app1/index.html", context)


def search_results(request):
    params = {name: clean_param(request.GET.get(name)) for name in SEARCH_FILTERS}
    filters = {SEARCH_FILTERS[name]: value for name, value in params.items() if value}
    if not filters:
        return redirect("home")

    results, eligible_only = apply_eligible_filter(request, Scholarship.objects.filter(**filters))
    results, sort = apply_sort(request, results)
    filter_qs = {k: v for k, v in params.items() if v}
    state = _list_state(sort, eligible_only, filter_qs)
    context = {
        **params,
        **search_dropdowns(),
        "scholarships": paginate(request, results),
        "number_of_scholarships": results.count(),
        "sort": sort,
        "sort_options": SORT_OPTIONS,
        "eligible_only": eligible_only,
        "filter_fields": {k: v for k, v in state.items() if k != "sort"},
        "qs": urlencode(state),
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


def _category(request, template, heading, preset, **lookup):
    results, eligible_only = apply_eligible_filter(request, Scholarship.objects.filter(**lookup))
    results, sort = apply_sort(request, results)
    state = _list_state(sort, eligible_only)
    return render(request, template, {
        **search_dropdowns(),
        **preset,
        "heading": heading,
        "scholarships": paginate(request, results),
        "number_of_scholarships": results.count(),
        "sort": sort,
        "sort_options": SORT_OPTIONS,
        "eligible_only": eligible_only,
        "filter_fields": {k: v for k, v in state.items() if k != "sort"},
        "qs": urlencode(state),
    })


def category_subjects(request, subject):
    return _category(request, "app1/category_subjects.html", subject, {"field_of_interest": subject},
                     subject__icontains=subject)


def category_degree(request, degree):
    return _category(request, "app1/category_degree.html", degree, {"degree": degree},
                     degree__icontains=degree)


# Old degree-list URLs now point at the shared category pages.
def scholarshipdegree1(request):
    return redirect("category_degree", degree="PhD")


def scholarshipdegree2(request):
    return redirect("category_degree", degree="Bachelors")


def scholarshipdegree3(request):
    return redirect("category_degree", degree="Masters")


def _list_state(sort, eligible_only, extra=None):
    """Query-string pieces that pagination and the toolbar must keep."""
    fields = dict(extra or {})
    if sort:
        fields["sort"] = sort
    if eligible_only:
        fields["eligible"] = "1"
    return fields


def scholarshipdata(request):
    results, eligible_only = apply_eligible_filter(request, Scholarship.objects.all())
    results, sort = apply_sort(request, results)
    state = _list_state(sort, eligible_only)
    return render(request, "app1/events.html", {
        **search_dropdowns(),
        "scholarships": paginate(request, results),
        "sort": sort,
        "sort_options": SORT_OPTIONS,
        "eligible_only": eligible_only,
        "filter_fields": {k: v for k, v in state.items() if k != "sort"},
        "qs": urlencode(state),
    })


def scholarship_detail(request, pk):
    scholarship = get_object_or_404(Scholarship.objects, pk=pk)
    # "Similar scholarships": rank everything else against this listing's own text.
    matches = recommender.recommend(scholarship.search_text(), top_n=5)
    ids = [m.scholarship_id for m in matches if m.scholarship_id != scholarship.pk][:4]
    by_id = Scholarship.objects.in_bulk(ids)
    similar = [by_id[i] for i in ids if i in by_id]
    eligibility_result = elig.check(scholarship, request.user.profile) if request.user.is_authenticated else None
    return render(request, "app1/scholarship_detail.html", {
        "scholarship": scholarship, "similar": similar, "eligibility": eligibility_result,
    })


def scholarshipdatadetial(request, id):
    # Old URL; the events_detail template never existed. Send people to the real detail page.
    return redirect("scholarship_detail", pk=id)


def base(request):
    return render(request, "app1/base.html")


DEGREE_CARDS = [
    ("Bachelors", "Bachelor", "bi-book", "Undergraduate study, usually three to four years. Funding often covers tuition."),
    ("Masters", "Master", "bi-mortarboard", "One to two years of postgraduate study. The largest group of fully funded awards."),
    ("PhD", "PhD", "bi-lightbulb", "Doctoral research, often with a monthly stipend as well as fees."),
]


def trainers(request):
    """The Degrees page."""
    live = Scholarship.objects.all()
    degrees = [
        {"name": name, "slug": name, "icon": icon, "blurb": blurb, "count": live.filter(degree__icontains=match).count()}
        for name, match, icon, blurb in DEGREE_CARDS
    ]
    return render(request, "app1/trainers.html", {"degrees": degrees})


def pricing(request):
    return redirect("home")


def events(request):
    return render(request, "app1/events.html")


def scholarship1(request):
    return redirect(f"{reverse('search_results')}?country=Germany")


def scholarship2(request):
    return redirect(f"{reverse('search_results')}?country=Canada")


def about(request):
    return render(request, "app1/about.html", {"stats": site_stats()})


def services(request):
    return redirect("about")


def contact(request):
    return redirect("about")


# ---------- accounts ----------

REGISTRATIONS_PER_HOUR = 5


def registration(request):
    if request.method != "POST":
        return render(request, "app1/registration.html")
    if rate_limited(request, "register", REGISTRATIONS_PER_HOUR, 60 * 60):
        messages.error(request, "Too many sign-ups from your network. Please try again in an hour.")
        return render(request, "app1/registration.html", status=429)

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
    from .models import Profile, new_token

    profile = Profile.objects.filter(email_token=token).first()
    if profile is None:
        messages.error(request, "That verification link is invalid or has already been used.")
        return redirect("login")
    profile.is_verified = True
    profile.email_token = new_token()  # each link works once
    profile.save(update_fields=["is_verified", "email_token"])
    messages.success(request, "Account verified. You can now log in.")
    return redirect("login")


# ---------- login (email or username, with brute-force protection) ----------

LOGIN_MAX_FAILURES = 5
LOGIN_LOCKOUT_SECONDS = 15 * 60


def _client_ip(request):
    """The visitor's IP. Behind a host's proxy, REMOTE_ADDR is the proxy, so read the
    entry the proxy added to X-Forwarded-For (TRUSTED_PROXY_COUNT says how many proxies).
    Entries further left are set by the client and can be faked, so they're ignored."""
    hops = settings.TRUSTED_PROXY_COUNT
    forwarded = [p.strip() for p in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",") if p.strip()]
    if hops and len(forwarded) >= hops:
        return forwarded[-hops]
    return request.META.get("REMOTE_ADDR", "")


def rate_limited(request, scope, limit, window):
    """Count one hit for this visitor; True once they exceed `limit` within `window` seconds."""
    key = f"rate:{scope}:{_client_ip(request)}"
    cache.add(key, 0, window)
    try:
        count = cache.incr(key)
    except ValueError:
        cache.set(key, 1, window)
        count = 1
    return count > limit


def _throttle_keys(request, identifier):
    ident = (identifier or "").strip().lower()[:150]
    return [f"login-fail:ip:{_client_ip(request)}", f"login-fail:id:{ident}"]


def _is_locked(request, identifier):
    return any(cache.get(k, 0) >= LOGIN_MAX_FAILURES for k in _throttle_keys(request, identifier))


def _record_failure(request, identifier):
    for key in _throttle_keys(request, identifier):
        cache.add(key, 0, LOGIN_LOCKOUT_SECONDS)
        try:
            cache.incr(key)
        except ValueError:
            cache.set(key, 1, LOGIN_LOCKOUT_SECONDS)


def _clear_failures(request, identifier):
    cache.delete_many(_throttle_keys(request, identifier))


def _authenticate_username_or_email(request, identifier, password):
    """Accept either a username or the email address on the account."""
    user = authenticate(request, username=identifier, password=password)
    if user is None and "@" in identifier:
        match = User.objects.filter(email__iexact=identifier).order_by("id").first()
        if match is not None:
            user = authenticate(request, username=match.username, password=password)
    return user


def user_login(request):
    if request.user.is_authenticated:
        return redirect("home")
    if request.method == "POST":
        identifier = (request.POST.get("username") or "").strip()
        password = request.POST.get("password") or ""
        if _is_locked(request, identifier):
            messages.error(request, "Too many failed attempts. Please wait 15 minutes and try again.")
            return render(request, "app1/userlogin.html", status=429)
        user = _authenticate_username_or_email(request, identifier, password)
        if user is not None:
            _clear_failures(request, identifier)
            login(request, user)
            next_url = request.POST.get("next") or request.GET.get("next")
            if next_url and url_has_allowed_host_and_scheme(next_url, {request.get_host()}, request.is_secure()):
                return redirect(next_url)
            return redirect("home")
        _record_failure(request, identifier)
        messages.error(request, "Invalid username/email or password.")
    return render(request, "app1/userlogin.html")


def user_logout(request):
    """Log out on POST only, so other websites can't log users out with a link."""
    if request.method == "POST":
        logout(request)
        messages.info(request, "You've been logged out.")
        return redirect("login")
    return redirect("home")


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

def _parse_profile_form(post, user):
    """Validate the edit-profile form. Returns (cleaned_data, errors)."""
    data, errors = {}, []

    for field in ("first_name", "last_name", "highest_qualification"):
        value = (post.get(field) or "").strip()
        if value:
            data[field] = value

    nationality = (post.get("nationality") or "").strip()
    if nationality:
        country = geo.normalise_country(nationality)
        if country:
            data["nationality"] = country
        else:
            errors.append("Please choose your nationality from the list.")

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
def showprofile(request):
    profile = request.user.profile
    return render(request, "app1/profile.html", {
        "field_of_interest_list": profile.fieldofinterest_set.order_by("name"),
        "current_program_list": profile.program_set.order_by("-timestamp"),
        "recent_history": profile.history_set.all()[:3],
        "history_count": profile.history_set.count(),
        "upcoming": profile.saved.select_related("scholarship").filter(
            status__in=SavedScholarship.REMIND_STATUSES,
            scholarship__deadline__gte=timezone.localdate(),
        ).order_by("scholarship__deadline")[:5],
        "saved_count": profile.saved.count(),
    })


@login_required
def showformdata(request):
    """Edit profile. Always edits the logged-in user (the old version trusted a hidden email field)."""
    if request.method != "POST":
        return render(request, "app1/profile_edit.html", {
            "country_choices": geo.all_countries(),
            "current_nationality": geo.normalise_country(request.user.profile.nationality) or request.user.profile.nationality,
        })

    user, profile = request.user, request.user.profile
    data, errors = _parse_profile_form(request.POST, user)

    photo = None
    if request.FILES.get("photo"):
        try:
            photo = process_profile_photo(request.FILES["photo"])
        except ValidationError as exc:
            errors.extend(exc.messages)

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
        profile.email_reminders = request.POST.get("email_reminders") == "on"
        if photo is not None:
            old = profile.photo.name
            profile.photo.save(photo.name, photo, save=False)
            if old and old != "default.jpg":
                profile.photo.storage.delete(old)
        profile.save()

    messages.success(request, "Profile updated.")
    return redirect("userprofile")


# ---------- interests & programmes ----------

# Starter ideas for people who aren't sure what to add yet.
STARTER_INTERESTS = [
    "Computer Science", "Data Science", "Artificial Intelligence", "Business Administration",
    "Economics", "Finance", "Public Health", "Medicine", "Nursing", "Engineering",
    "Renewable Energy", "Environmental Science", "Agriculture", "Law", "International Relations",
    "Education", "Psychology", "Arts and Design", "Architecture", "Mathematics",
]
MAX_INTERESTS = 15


@login_required
def add_field_of_interest(request):
    profile = request.user.profile
    mine = list(profile.fieldofinterest_set.order_by("name"))
    if request.method == "POST":
        name = " ".join((request.POST.get("fieldOfInterest") or "").split())[:60]
        if not name:
            messages.error(request, "Please type or pick an interest.")
        elif len(mine) >= MAX_INTERESTS:
            messages.error(request, f"You can save up to {MAX_INTERESTS} interests. Remove one to add another.")
        elif any(i.name.lower() == name.lower() for i in mine):
            messages.info(request, f"“{name}” is already in your interests.")
        else:
            FieldOfInterest.objects.create(name=name, profile=profile)
            messages.success(request, f"Added “{name}”.")
        return redirect("add_field_of_interest")

    taken = {i.name.lower() for i in mine}
    popular = [
        row["subject"] for row in
        Scholarship.objects.exclude(subject="").values("subject").annotate(n=Count("id")).order_by("-n")[:30]
    ]
    popular = list(dict.fromkeys(p.split(";")[0].strip() for p in popular))  # first subject, de-duplicated
    # Skip catch-all labels like "All subjects" or "Development-related subjects" - they aren't real interests.
    popular = [p for p in popular if p and "subject" not in p.lower() and p.lower() not in taken][:12]
    shown = {p.lower() for p in popular}
    return render(request, "app1/field_of_interest_form.html", {
        "my_interests": mine,
        "starter_interests": [s for s in STARTER_INTERESTS if s.lower() not in taken and s.lower() not in shown],
        "popular_interests": popular,
        "all_subjects": site_subjects(),
        "max_interests": MAX_INTERESTS,
    })


@login_required
@require_POST
def remove_field_of_interest(request, pk):
    get_object_or_404(FieldOfInterest, pk=pk, profile=request.user.profile).delete()
    return redirect(request.POST.get("next") if request.POST.get("next") == reverse("userprofile") else "add_field_of_interest")


@login_required
def add_current_program(request):
    if request.method == "POST":
        name = " ".join((request.POST.get("program") or "").split())[:150]
        if not name:
            messages.error(request, "Please enter the programme you're studying.")
            return redirect("current_program")
        Program.objects.get_or_create(name=name, profile=request.user.profile)
        messages.success(request, "Programme saved.")
        return redirect("userprofile")
    return render(request, "app1/current_program.html")


@login_required
@require_POST
def remove_current_program(request, pk):
    get_object_or_404(Program, pk=pk, profile=request.user.profile).delete()
    return redirect("userprofile")


# ---------- recommendations ----------

DEGREE_CHOICES = ["Bachelors", "Masters", "PhD"]


def _save_recommendations(history, matches):
    with transaction.atomic():
        Recommendation.objects.filter(history=history).delete()
        Recommendation.objects.bulk_create([
            Recommendation(
                history=history, scholarship_id=m.scholarship_id, rank=rank, score=m.score,
                matched_terms="|".join(m.terms)[:200],
            )
            for rank, m in enumerate(matches, start=1)
        ])


def run_recommendations(history):
    """Rank scholarships for a History (statement and/or CV) and store the results."""
    candidates = Scholarship.objects.all()
    if history.target_degree:
        candidates = candidates.filter(degree__icontains=history.target_degree.rstrip("s"))
    if history.target_country:
        candidates = candidates.filter(country__icontains=history.target_country)
    candidate_ids = None
    if history.target_degree or history.target_country:
        candidate_ids = set(candidates.values_list("id", flat=True))

    interests = list(history.profile.fieldofinterest_set.values_list("name", flat=True))
    boost = "" if history.target_degree else suggested_degree(history.query_text)
    matches = recommender.recommend(
        history.query_text, extra_terms=interests, candidate_ids=candidate_ids, boost_degree=boost,
    )
    _save_recommendations(history, matches)
    return matches


@login_required
def my_recommendations(request):
    """Form to get recommendations. Sent by POST so statements never appear in URLs or logs."""
    profile = request.user.profile
    context = {
        "degree_choices": DEGREE_CHOICES,
        "countries": Country.objects.all(),
        "recent_history": profile.history_set.all()[:5],
        "min_length": MIN_STATEMENT_LENGTH,
        "form": {"statement": "", "degree": "", "country": ""},
    }
    if request.method != "POST":
        return render(request, "app1/recommendations.html", context)

    statement = (request.POST.get("statement") or "").strip()[:10_000]
    degree = request.POST.get("degree") if request.POST.get("degree") in DEGREE_CHOICES else ""
    country = (request.POST.get("country") or "").strip()[:100]
    if country and not Country.objects.filter(name=country).exists():
        country = ""
    cv_file = request.FILES.get("cv")
    context["form"] = {"statement": statement, "degree": degree, "country": country, "mode": "cv" if cv_file else ""}

    errors, cv_text = [], ""
    if cv_file:
        try:
            cv_text = extract_cv_text(cv_file)
        except ValidationError as exc:
            errors.extend(exc.messages)
    if not cv_file and not statement:
        errors.append("Write a personal statement or upload your CV (or both).")
    elif statement and not cv_file and len(statement) < MIN_STATEMENT_LENGTH:
        errors.append(
            f"Your statement is {len(statement)} characters. Please write at least {MIN_STATEMENT_LENGTH}, "
            "or upload your CV instead."
        )
    if errors:
        for error in errors:
            messages.error(request, error)
        return render(request, "app1/recommendations.html", context, status=400)

    input_type = History.INPUT_BOTH if (statement and cv_text) else (History.INPUT_CV if cv_text else History.INPUT_STATEMENT)
    history = History.objects.create(
        profile=profile, personal_statement=statement, cv_text=cv_text,
        cv_filename=(cv_file.name[:255] if cv_file else ""), input_type=input_type,
        target_degree=degree, target_country=country,
    )
    run_recommendations(history)
    return redirect("recommendation_results", pk=history.pk)


@login_required
def recommendation_results(request, pk):
    history = get_object_or_404(History, pk=pk, profile=request.user.profile)
    recs = list(
        Recommendation.objects.filter(history=history, scholarship__is_active=True)
        .select_related("scholarship").order_by("rank")
    )
    show_all = request.GET.get("all") == "1"
    profile = request.user.profile
    blocked = {r.pk for r in recs if elig.check(r.scholarship, profile).is_blocked}
    hidden_count = 0 if show_all else len(blocked)
    if not show_all:
        recs = [r for r in recs if r.pk not in blocked]
    top_score = recs[0].score if recs else 0
    page = paginate(request, recs)
    for rec in page:
        # Relative match strength (best result = 100%), easier to read than raw cosine scores.
        rec.match_percent = round(100 * rec.score / top_score) if top_score else 0
    return render(request, "app1/recommendation_results.html", {
        "history": history,
        "recommendations": page,
        "total": len(recs),
        "hidden_count": hidden_count,
        "show_all": show_all,
        "has_nationality": bool(profile.nationality),
        "suggested_degree": "" if history.target_degree else suggested_degree(history.query_text),
    })


@login_required
@require_POST
def rerun_recommendations(request, pk):
    history = get_object_or_404(History, pk=pk, profile=request.user.profile)
    run_recommendations(history)
    messages.success(request, "Recommendations refreshed with the latest scholarships.")
    return redirect("recommendation_results", pk=history.pk)


@login_required
def my_history(request):
    histories = request.user.profile.history_set.annotate(n=Count("recommendation"))
    return render(request, "app1/my_history.html", {"user_history": paginate(request, histories)})


@login_required
@require_POST
def delete_history(request, pk):
    get_object_or_404(History, pk=pk, profile=request.user.profile).delete()
    messages.success(request, "Deleted from your history.")
    return redirect("my_history")


@login_required
@require_POST
def clear_history(request):
    request.user.profile.history_set.all().delete()
    messages.success(request, "Your history has been cleared.")
    return redirect("my_history")


# ---------- feedback ----------

@login_required
def feedback(request):
    if request.method == "POST":
        content = " ".join((request.POST.get("feedback") or "").split())
        emoji = request.POST.get("emoji") if request.POST.get("emoji") in {"1", "2", "3", "4"} else ""
        if len(content) < 5:
            messages.error(request, "Please write a short message (at least 5 characters).")
            return redirect("feedback")
        if Feedback.objects.filter(profile=request.user.profile, created__gte=timezone.now() - timedelta(minutes=10)).count() >= 3:
            messages.error(request, "Thanks! You've sent a few messages already. Please try again a bit later.")
            return redirect("feedback")
        Feedback.objects.create(content=content[:500], emoji=emoji, profile=request.user.profile)
        messages.success(request, "Thanks for your feedback! It will appear on the site once it's reviewed.")
        return redirect("feedback")
    return render(request, "app1/feedback.html", {
        "my_feedback": request.user.profile.feedback_set.all()[:5],
    })


# ---------- account deletion ----------

@login_required
def delete_account(request):
    if request.method == "POST":
        if not request.user.check_password(request.POST.get("password") or ""):
            messages.error(request, "That password is incorrect.")
            return redirect("delete_account")
        user = request.user
        photo = user.profile.photo
        if photo and photo.name != "default.jpg":
            photo.storage.delete(photo.name)
        logout(request)
        user.delete()  # cascades to profile, history, interests, feedback
        messages.success(request, "Your account and all your data have been deleted.")
        return redirect("home")
    return render(request, "app1/delete_account.html")


# ---------- saved scholarships & application tracker ----------

def _wants_json(request):
    return request.headers.get("x-requested-with") == "fetch" or "application/json" in request.headers.get("accept", "")


def _safe_next(request, fallback):
    nxt = request.POST.get("next") or ""
    if nxt and url_has_allowed_host_and_scheme(nxt, {request.get_host()}, request.is_secure()):
        return nxt
    return fallback


@login_required
@require_POST
def toggle_saved(request, pk):
    """Save or unsave a scholarship. Works as a normal form post or via fetch() (returns JSON)."""
    scholarship = get_object_or_404(Scholarship.objects, pk=pk)
    profile = request.user.profile
    existing = SavedScholarship.objects.filter(profile=profile, scholarship=scholarship).first()
    if existing:
        existing.delete()
        saved = False
    else:
        SavedScholarship.objects.create(profile=profile, scholarship=scholarship)
        saved = True
    if _wants_json(request):
        return JsonResponse({"saved": saved, "count": profile.saved.count()})
    messages.success(request, f"Saved “{scholarship.title}”." if saved else f"Removed “{scholarship.title}”.")
    return redirect(_safe_next(request, reverse("scholarship_detail", args=[pk])))


@login_required
def my_applications(request):
    saved = (
        request.user.profile.saved.select_related("scholarship")
        .order_by(F("scholarship__deadline").asc(nulls_last=True), "-created_at")
    )
    columns = [
        {"key": key, "label": label, "items": [s for s in saved if s.status == key]}
        for key, label in SavedScholarship.STATUS_CHOICES
    ]
    return render(request, "app1/applications.html", {
        "columns": columns,
        "total": len(saved),
        "status_choices": SavedScholarship.STATUS_CHOICES,
    })


@login_required
@require_POST
def update_application(request, pk):
    item = get_object_or_404(SavedScholarship, pk=pk, profile=request.user.profile)
    fields = []
    status = request.POST.get("status")
    if status is not None:
        if status not in dict(SavedScholarship.STATUS_CHOICES):
            return JsonResponse({"error": "Unknown status"}, status=400) if _wants_json(request) else redirect("my_applications")
        item.status = status
        fields.append("status")
    if "notes" in request.POST:
        item.notes = request.POST["notes"].strip()[:2000]
        fields.append("notes")
    if fields:
        item.save(update_fields=fields + ["updated_at"])
    if _wants_json(request):
        return JsonResponse({"ok": True, "status": item.status})
    messages.success(request, "Application updated.")
    return redirect("my_applications")


@login_required
@require_POST
def remove_application(request, pk):
    get_object_or_404(SavedScholarship, pk=pk, profile=request.user.profile).delete()
    messages.success(request, "Removed from your applications.")
    return redirect("my_applications")


# ---------- email reminders: one-click unsubscribe ----------

UNSUBSCRIBE_SALT = "reminders-unsubscribe"


def unsubscribe_token(user):
    return signing.dumps(user.pk, salt=UNSUBSCRIBE_SALT)


def unsubscribe_reminders(request, token):
    """Linked from every reminder email; works without logging in."""
    try:
        user_pk = signing.loads(token, salt=UNSUBSCRIBE_SALT, max_age=60 * 60 * 24 * 365)
    except signing.BadSignature:
        messages.error(request, "That unsubscribe link isn't valid.")
        return redirect("home")
    from .models import Profile

    Profile.objects.filter(user_id=user_pk).update(email_reminders=False)
    return render(request, "app1/unsubscribed.html")


# ---------- forgotten password ----------


PASSWORD_RESETS_PER_HOUR = 5


class PasswordResetView(auth_views.PasswordResetView):
    """Django's reset flow (one-time, 1-hour links; the page never says whether an email
    has an account) plus a per-visitor limit so it can't be used to flood an inbox."""

    template_name = "app1/password_reset_form.html"
    email_template_name = "emails/password_reset.txt"
    subject_template_name = "emails/password_reset_subject.txt"

    def post(self, request, *args, **kwargs):
        if rate_limited(request, "password-reset", PASSWORD_RESETS_PER_HOUR, 60 * 60):
            messages.error(request, "Too many reset requests. Please try again in an hour.")
            return self.render_to_response(self.get_context_data(form=self.get_form()), status=429)
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        from urllib.parse import urlsplit
        parts = urlsplit(settings.SITE_URL)
        self.extra_email_context = {"site_url": settings.SITE_URL}
        form.save(
            domain_override=parts.netloc, use_https=parts.scheme == "https",
            subject_template_name=self.subject_template_name,
            email_template_name=self.email_template_name,
            from_email=settings.DEFAULT_FROM_EMAIL, request=self.request,
            extra_email_context=self.extra_email_context,
        )
        return redirect(self.get_success_url())


def healthz(request):
    """Tiny page for uptime pings (keeps a free host awake). No database query."""
    return HttpResponse("ok", content_type="text/plain")
