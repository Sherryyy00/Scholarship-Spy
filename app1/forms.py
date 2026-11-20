from django import forms

from .models import Profile


class ProfileUpdateForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ["age", "dob", "highest_qualification", "cgpa", "nationality", "photo"]
