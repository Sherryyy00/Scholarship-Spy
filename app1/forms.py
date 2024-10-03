from cProfile import Profile
# from curses import meta
from dataclasses import fields
from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm, UsernameField, PasswordChangeForm, PasswordResetForm, SetPasswordForm
from django.contrib.auth.models import User
from django.utils.translation import gettext, gettext_lazy as _
from django.contrib.auth import password_validation
from .models import *

class RegistrationForm(UserCreationForm):
    password2: forms.CharField(label='Confirm Password', widget=forms.PasswordInput)
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'username', 'email']
        labels ={'email':'Email'}


class UserUpdateForm(forms.ModelForm):
    email=forms.EmailField()

    class Meta:
        model=User
        fields=['username','email','password']


class ProfileUpdateForm(forms.ModelForm):
    class Meta:
        model=Profile
        fields=['age','dob', 'highest_qualification', 'cgpa']
