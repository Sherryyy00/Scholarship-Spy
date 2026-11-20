from django.db import migrations


def normalise(apps, schema_editor):
    """'Pakistani', 'british', 'PK' -> country names, so eligibility checks can match them."""
    from app1.geo import normalise_country

    Profile = apps.get_model("app1", "Profile")
    for p in Profile.objects.exclude(nationality="").only("id", "nationality"):
        country = normalise_country(p.nationality)
        if country and country != p.nationality:
            Profile.objects.filter(pk=p.pk).update(nationality=country)


class Migration(migrations.Migration):
    dependencies = [("app1", "0004_deadlines_saved_scholarships")]
    operations = [migrations.RunPython(normalise, migrations.RunPython.noop)]
