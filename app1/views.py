from multiprocessing.connection import Client
from django.shortcuts import render, HttpResponse, HttpResponseRedirect,redirect
from django.http import Http404
# from waitress import profile
from .forms import RegistrationForm
from .forms import ProfileUpdateForm
from .models import Profile,Scholarship,History,FieldOfInterest,TypeOfDegree,Country,Feedback,Program,FieldOfInterest,Feedback
from django.contrib import messages
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.utils.dateparse import parse_date
from django.db.models import Q
from .utils import *
import uuid

import warnings
warnings.filterwarnings('ignore')

import re
import numpy as np
import pandas as pd
from heapq import nsmallest
from nltk.corpus import stopwords
from sklearn.cluster import KMeans
from nltk.tokenize import word_tokenize
#from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
import pickle


# Create your views here.
def index(request):
    context = {}
    all_field_of_interests = FieldOfInterest.objects.all()
    all_degree_types = TypeOfDegree.objects.all()
    all_countries = Country.objects.all()
    feedbacks = Feedback.objects.all()[0:3]
    print(Feedback.objects.all())
    context['all_field_of_interests'] = all_field_of_interests
    context['all_degree_types'] = all_degree_types
    context['all_countries'] = all_countries
    context['all_feedbacks'] = feedbacks
    return render(request,"app1/index.html",context)


def search_results(request):
    all_field_of_interests = FieldOfInterest.objects.all() 
    all_degree_types = TypeOfDegree.objects.all() 
    all_countries = Country.objects.all() 
    scholarship_title = request.GET.get("scholarship_title") or None
    if scholarship_title == 'None':
        scholarship_title = None
    country = request.GET.get("country") or None
    if country == 'None':
        country = None
    field_of_interest = request.GET.get("field_of_interest") or None
    if field_of_interest == 'None':
        field_of_interest = None
    degree = request.GET.get("degree") or None
    if degree == 'None':
        degree = None
    print({'scholarship_title':scholarship_title,'country':country,'field_of_interest':field_of_interest,'degree':degree})
    page = request.GET.get('page', 1)
    if scholarship_title!=None and country==None and field_of_interest==None and degree==None:
        print("scholarship_title this is runninng")
        all_scholarships = Scholarship.objects.filter(
            title__icontains=scholarship_title
        )
    elif scholarship_title==None and country!=None and field_of_interest==None and degree==None:
        print("country this is runninng")
        all_scholarships = Scholarship.objects.filter(country__icontains=country)

    elif scholarship_title==None and country==None and field_of_interest!=None and degree==None:
        print("field_of_interest this is runninng")
        all_scholarships = Scholarship.objects.filter(subject__icontains=field_of_interest)

    elif scholarship_title==None and country==None and field_of_interest==None and degree!=None:
        print("degree this is runninng")
        all_scholarships = Scholarship.objects.filter(degree__icontains=degree)

    elif scholarship_title!=None and country!=None and field_of_interest==None and degree==None:
        print("scholarship_title country this is runninng")
        all_scholarships = Scholarship.objects.filter(title__icontains=scholarship_title,country__icontains=country)
    
    elif scholarship_title!=None and country==None and field_of_interest!=None and degree==None:
        print("scholarship_title field_of_interest this is runninng")

        all_scholarships = Scholarship.objects.filter(title__icontains=scholarship_title,subject__icontains=field_of_interest)
    
    elif scholarship_title!=None and country==None and field_of_interest==None and degree!=None:
        print("scholarship_title degree this is runninng")

        all_scholarships = Scholarship.objects.filter(title__icontains=scholarship_title,degree__icontains=degree)
    
    elif scholarship_title==None and country!=None and field_of_interest!=None and degree==None:
        print("country field_of_interest this is runninng")
        all_scholarships = Scholarship.objects.filter(country__icontains=country,subject__icontains=field_of_interest)
    
    elif scholarship_title==None and country!=None and field_of_interest==None and degree!=None:
        print("country degree this is runninng")

        all_scholarships = Scholarship.objects.filter(country__icontains=country,degree__icontains=degree)

    elif scholarship_title==None and country==None and field_of_interest!=None and degree!=None:
        print("field_of_interest degree this is runninng")
        all_scholarships = Scholarship.objects.filter(subject__icontains=field_of_interest,degree__icontains=degree)
        
    
    elif scholarship_title!=None and country!=None and field_of_interest!=None and degree==None:
        print("scholarship_title country field_of_interest this is runninng")
        all_scholarships = Scholarship.objects.filter(title__icontains=scholarship_title,country__icontains=country,subject__icontains=field_of_interest)
    
    elif scholarship_title!=None and country!=None and field_of_interest==None and degree!=None:
        print("scholarship_title country degree this is runninng")
        all_scholarships = Scholarship.objects.filter(title__icontains=scholarship_title,country__icontains=country,degree__icontains=degree)
  
    
    elif scholarship_title!=None and country==None and field_of_interest!=None and degree!=None:
        print("scholarship_title field_of_interest degree this is runninng")
        all_scholarships = Scholarship.objects.filter(title__icontains=scholarship_title,subject__icontains=field_of_interest,degree__icontains=degree)

    elif scholarship_title==None and country!=None and field_of_interest!=None and degree!=None:
        print("field_of_interest country degree this is runninng")
        all_scholarships = Scholarship.objects.filter(country__icontains=country,degree__icontains=degree,subject__icontains=field_of_interest)

    elif scholarship_title!=None and country!=None and field_of_interest!=None and degree!=None:
        print("scholarship_title country field_of_interest degree this is runninng")
        all_scholarships = Scholarship.objects.filter(title__icontains=scholarship_title,country__icontains=country,subject__icontains=field_of_interest,degree__icontains=degree)
    else:
        return redirect("home")

    paginator = Paginator(all_scholarships, 10)
    try:
        scholarships = paginator.page(page)
    except not isinstance(page,int):
        scholarships = paginator.page(1)
    except:
        scholarships = paginator.page(paginator.num_pages)
    print(scholarships)
    context = {
        'scholarships':scholarships,
        'scholarship_title':scholarship_title,
        'country':country,
        'field_of_interest':field_of_interest,
        'degree':degree,
        'number_of_scholarships':len(all_scholarships),
    }
    context['all_field_of_interests'] = all_field_of_interests
    context['all_degree_types'] = all_degree_types
    context['all_countries'] = all_countries
    return render(request,"app1/scholarship_results.html",context)



def base(request):
    return render(request,"app1/base.html")

def subjects(request):
    context = {}
    all_subjects = FieldOfInterest.objects.all()
    mydata = [all_subjects[i:i + 15] for i in range(0, len(all_subjects), 15)]
    context['all_subjects'] = mydata
    return render(request,"app1/subjects.html",context)

def category_subjects(request,subject):
    context = {}
    all_scholarships = Scholarship.objects.filter(subject__icontains=subject)
    page = request.GET.get('page', 1)
    paginator = Paginator(all_scholarships, 10)
    try:
        scholarships = paginator.page(page)
    except not isinstance(page,int):
        scholarships = paginator.page(1)
    except:
        scholarships = paginator.page(paginator.num_pages)
    context['scholarships']= scholarships
    context['number_of_scholarships']=len(all_scholarships)
    return render(request,'app1/category_subjects.html',context)

def trainers(request):
    return render(request,"app1/trainers.html")


def category_degree(request,degree):
    context = {}
    all_scholarships = Scholarship.objects.filter(degree__icontains=degree)
    page = request.GET.get('page', 1)
    paginator = Paginator(all_scholarships, 10)
    try:
        scholarships = paginator.page(page)
    except not isinstance(page,int):
        scholarships = paginator.page(1)
    except:
        scholarships = paginator.page(paginator.num_pages)
    context['scholarships']= scholarships
    context['number_of_scholarships']=len(all_scholarships)
    return render(request,'app1/category_degree.html',context)

def pricing(request):
    return render(request,"app1/pricing.html")

def events(request):
    return render(request,"app1/events.html")

def scholarship1(request):
    return render(request, "app1/berlin-scholarship.html")
    
def scholarship2(request):
    return render(request, "app1/canada-scholarship.html")

def about(request):
    return render(request,"app1/about.html")
    #return HttpResponse("this is about page")

def services(request):
    return HttpResponse("this is services page")

def contact(request):
    return HttpResponse("this is contact page")

#RegistrationView Function
def registration(request):
    if request.method == 'POST':
        u_name = request.POST.get('username')
        first_name = request.POST['first_name']
        last_name = request.POST['last_name']
        email = request.POST['email']
        password = request.POST['password1']
        confirm_password = request.POST['password2']
        try:
            user = User.objects.get(email=email)
            if user:
                messages.error(request, 'The email you entered already exists.')
                return redirect("Registration")
        except:
            if password == confirm_password:
                user = User.objects.create_user(username=u_name, email=email, password=password, first_name=first_name, last_name=last_name)
                user.save()
                user.profile.email_token=str(uuid.uuid4())
                send_email_token(email,user.profile.email_token)
                return HttpResponse('check your email account')
            else:
                messages.error(request, 'Password Mismatch')
    return render(request, 'app1/registration.html')

def verify(request, token):
    try:
        obj= Profile.objects.get(email_token=token)
        obj.is_verified=True
        obj.save()
        return HttpResponse("Account Verified Successfully!")
    
    except Exception as e:
        return HttpResponse("Invalid Token.")
        

def user_login(request):
    if request.method == 'POST': 
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(username=username, password=password)
        if user is not None:
            login(request, user)
            return HttpResponseRedirect('/', {'name': user.username})
        else:
            messages.error(request, 'Invalid Credentials')
    return render(request, 'app1/userlogin.html')




#User Profile
@login_required(login_url="/login")
def user_profile(request):
    if request.user.is_authenticated:
        return render(request, 'profile.html', {'name': request.user})
    else:
        return HttpResponseRedirect('/login/')


#Logout
def user_logout(request):
    logout(request)
    return HttpResponseRedirect('/login/')


#Profile Form
@login_required(login_url="/login")
def showformdata(request):
    if request.method == 'POST':
        photo = request.FILES.get("photo") or None
        first_name = request.POST.get("first_name") or None
        last_name = request.POST.get("last_name") or None
        email = request.POST.get("email") or None
        highest_qualification = request.POST.get("highest_qualification") or None
        nationality = request.POST.get("nationality") or None
        hidden_user_email = request.POST.get("hidden_user_email") or None
        user = User.objects.get(email=hidden_user_email)
        print(user)
        if user is not None:
            if first_name is not None:
                user.first_name = first_name
            if last_name is not None:
                user.last_name = last_name
            if email is not None:
                user.email = email
            user.save()
        dob = request.POST.get("dob") or None
        age = request.POST.get("age") or None
        cgpa = request.POST.get("cgpa") or None

        if dob is not None:
            user.profile.dob = dob
        if cgpa is not None:
            if float(cgpa)>4.0:
                messages.info(request, 'CGPA must be upto 4.0 !')
                return redirect("userprofileedit")
            if str(cgpa)[::-1].find('.') > 2:
                messages.info(request, 'CGPA must have 2 digits after decimal !')
                return redirect("userprofileedit")
            user.profile.cgpa = cgpa
        if age is not None:
            user.profile.age = age
        
        if highest_qualification is not None:
            user.profile.highest_qualification = highest_qualification
        
        if nationality is not None:
            user.profile.nationality = nationality

        if photo is not None:
            user.profile.photo = photo
        user.profile.save()
        return redirect('userprofile')
    return render (request, 'app1/profile_edit.html')


@login_required(login_url="/login")
def add_field_of_interest(request):
    context = {}
    if request.method=='POST':
        fieldOfInterest = request.POST.get("fieldOfInterest")
        fieldOfInterest_obj = FieldOfInterest.objects.create(name=fieldOfInterest,profile=request.user.profile)
        fieldOfInterest_obj.save()
        return redirect("userprofile")
    return render(request,"app1/field_of_interest_form.html",context)


@login_required(login_url="/login")
def add_current_program(request):
    context = {}
    if request.method=='POST':
        program = request.POST.get("program")
        program_obj = Program.objects.create(name=program,profile=request.user.profile)
        program_obj.save()
        return redirect("userprofile")
    return render(request,"app1/current_program.html",context)



@login_required(login_url="/login")
def showprofile(request):
    context={}
    if request.user.is_authenticated:
        context['field_of_interest_list'] = request.user.profile.fieldofinterest_set.all()
        context['current_program_list'] = request.user.profile.program_set.all()
        return render (request, 'app1/profile.html',context)
    


@login_required(login_url="/login")
def my_recommendations(request):
    context = {}
    user = request.user
    my_personal_statement = request.GET.get("statement") or None

    if my_personal_statement!=None:
        if len(my_personal_statement) < 250:
            messages.info(request, 'Your Statement should be minimum of 250 characters!')
            context['personal_statement'] = my_personal_statement
            return render (request, 'app1/recommendations.html',context)
        else:
            try:
                history = History.objects.get(personal_statement = my_personal_statement,profile = user.profile)
            except History.DoesNotExist:
                history = History.objects.create(personal_statement = my_personal_statement,profile = user.profile)
                history.save()
            context['personal_statement'] = history.personal_statement
            
            #ML
            df = pd.read_csv('Dataset/scholarshipads_updated.csv')

# Drop null values
            df = df.dropna()
            df = df.reset_index(drop=True)

            def Clean(text):
                # Convert to lowercase
                text = text.lower()

                # Remove all characters which are not alphabetical or numerical
                text = re.sub(r'[\W_]', ' ', text)

                # Tokenization
                text = word_tokenize(text)

                # Filter out stop words
                text = [w for w in text if not w in set(stopwords.words('english'))]

                return text

            def word_embeddings():
                embeddings = {}
                with open("glove.6B.50d.txt", 'r', encoding="utf-8") as f:
                    for line in f:
                        values = line.split()
                        word = values[0]
                        vector = np.asarray(values[1:], "float32")
                        embeddings[word] = vector
                return embeddings

            def Vectorize(text, embeddings):
                # Generate vector representation
                vec = np.zeros(50)
                count = 0
                for i in text:
                    try:
                        vec += embeddings[i]
                        count += 1
                    except:
                        pass
                return vec/count

            centroids = np.load('cluster_centers.npy', allow_pickle=True)

            def recommend(text, embeddings, centroids,n=5):
                temp = Clean(text)
                temp = Vectorize(temp, embeddings)
                diff = centroids - temp
                dist = list(np.sum(diff**2, axis=-1) ** 0.5)
                idx = [i for i in map(dist.index, nsmallest(n, dist))]

                return idx

            embeddings = word_embeddings()
            result = recommend( my_personal_statement ,embeddings, centroids)
            idx = np.unique(result)
            
            
            scholarships_list = Scholarship.objects.all()[:20]
            for scholarship in scholarships_list:
                scholarship.history.add(history)
                scholarship.save()
            page = request.GET.get('page', 1)
            paginator = Paginator(scholarships_list, 10)
            try:
                scholarships = paginator.page(page)
            except not isinstance(page,int):
                scholarships = paginator.page(1)
            except:
                scholarships = paginator.page(paginator.num_pages)

            context["scholarships"] = scholarships
    else:
        context["scholarships"] = "" 
        messages.info(request, 'No recommendation') 
        #return redirect("my_recommendations")  
        
    return render (request, 'app1/recommendations.html',context)


def scholarship_detail(request,pk):
    context = {}
    try:
        scholarship = Scholarship.objects.get(pk=pk)
        context['scholarship'] =  scholarship
    except Scholarship.DoesNotExist:
        raise Http404("Scholarship not found")
    return render(request,"app1/scholarship_detail.html",context)


@login_required(login_url="/login")
def my_history(request):
    context={}
    user_history = request.user.profile.history_set.all()

    context['user_history'] = user_history
    return render(request,'app1/my_history.html',context)



@login_required(login_url="/login")
def password_reset_settings(request):
    context={}
    if request.method == 'POST':
        user = request.user
        old_password=request.POST.get("old_password")
        new_password=request.POST.get("new_password")
        retype_new_password=request.POST.get("retype_new_password")

        print({
            'old_password':old_password,
            'new_password':new_password,
            'retype_new_password':retype_new_password,
        })

        if new_password!=retype_new_password:
            messages.info(request, 'Both Password should same!')
            return redirect("password_reset_settings")
       

        check_pass = request.user.check_password(old_password)
        print("check_pass",check_pass)
        if check_pass:
            if (new_password==retype_new_password):
                user.set_password(new_password)
                user.save()
                return redirect("login")
        
        else:
            messages.info(request, 'Old Password is wrong! Please enter right old password :)')
            return redirect("password_reset_settings")

    return render(request,'app1/reset_password.html')


def scholarshipdata(request):
    context ={}
    scholarships_list = Scholarship.objects.all()
    print(len(scholarships_list))
    page = request.GET.get('page', 1)
    paginator = Paginator(scholarships_list, 10)
    try:
        scholarships = paginator.page(page)
    except not isinstance(page,int):
        scholarships = paginator.page(1)
    except:
        scholarships = paginator.page(paginator.num_pages)
    context["scholarships"] = scholarships
    return render (request, 'app1/events.html', context)


@login_required(login_url="/login")
def feedback(request):
    context={}
    if request.method=='POST':
        emoji = request.POST.get("emoji")
        feedback_input = request.POST.get("feedback")
        print(emoji)
        print(feedback)
        feedback_obj = Feedback.objects.create(emoji=emoji,content=feedback_input,profile=request.user.profile)
        feedback_obj.save()
        return redirect("home")
    return render(request, 'app1/feedback.html', context)

    
def scholarshipdatadetial(request,id):
    scholar_ship = Scholarship.objects.get(pk=id)
    print(scholar_ship)
    return render (request, 'app1/events_detail.html', {'scholarship': scholar_ship})
    

def scholarshipdegree1(request):
    scholarship_degree1 = Scholarship.objects.filter(Degree='PhD')
    print(scholarship_degree1)
    return render (request, 'app1/phd-list.html', {'scholarshipone': scholarship_degree1})
    

def scholarshipdegree2(request):
    scholarship_degree2 = Scholarship.objects.filter(Degree='Bachelors')
    print(scholarship_degree2)
    return render (request, 'app1/bachelors-list.html', {'scholarshiptwo': scholarship_degree2})
    

def scholarshipdegree3(request):
    scholarship_degree3 = Scholarship.objects.filter(Degree='Masters')
    print(scholarship_degree3)
    return render (request, 'app1/masters-list.html', {'scholarshipthree': scholarship_degree3})
    

def search(request):
    degree = request.GET['degree']
    country = request.GET['query']
    search_data = Scholarship.objects.filter(Degree=degree, Country=country)
    data = [item for item in search_data if degree in item.Degree and country in item.Country]
    if data == []:
        messages.error(request, 'No Data Found')
        return render(request, 'app1/search.html', {'data': data})
    else:
        messages.success(request, 'Data Found')
        return render(request, 'app1/search.html', {'data': data})
