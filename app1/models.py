from django.db import models
from django.contrib.auth.models import User
from PIL import Image

# history,program,typeofdegree

class Profile(models.Model):
    age=models.IntegerField(null=True,blank=True)
    dob=models.DateField(null=True,blank=True)
    highest_qualification=models.CharField(max_length=75,null=True,blank=True) #1
    cgpa=models.FloatField(null=True,blank=True,default=0.1)
    nationality = models.CharField(max_length=100,null=True,blank=True)
    photo = models.ImageField(default="default.jpg",upload_to="profile_pics")
    user = models.OneToOneField(User,on_delete=models.CASCADE,null=True,blank=True)
    email_token=models.CharField(max_length=200, null= True)
    is_verified=models.BooleanField(default=False)


    def __str__(self):
        return f"{self.user.username}'s profile"
    
    def save(self,*args,**kwargs):
        super().save(*args,**kwargs)

        img=Image.open(self.photo.path)

        if img.height > 300 or img.width > 300:
            remain_size=(300,300)
            img.thumbnail(remain_size)
            img.save(self.photo.path)
    


class History(models.Model):
    personal_statement = models.TextField(null=True,blank=True)
    profile=models.ForeignKey(Profile, on_delete=models.CASCADE,null=True,blank=True)

    def __str__(self):
        return self.personal_statement[0:50]

    
class Country(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self) -> str:
        return self.name

class Scholarship(models.Model):
    link=models.CharField(max_length=225, null = True,blank=True)
    title=models.CharField(max_length=200, null = True,blank=True)  
    image_link=models.CharField( max_length=200, null = True,blank=True)
    tution_structure=models.CharField(max_length=30, null=True,blank=True)
    university_name=models.CharField(max_length=200, null = True,blank=True)
    degree=models.CharField(max_length=30, null = True,blank=True)
    subject=models.CharField(max_length=30, null = True,blank=True)
    eligibility=models.CharField(max_length=30, null = True,blank=True)
    country=models.CharField(max_length=30, null = True,blank=True)
    apply_date=models.CharField(max_length=200,null = True,blank=True)
    scholarship_details= models.TextField(null = True,blank=True)
    history = models.ManyToManyField(History,blank=True)

    def __str__(self) -> str:
        return self.title

    

class Program(models.Model):
    name=models.CharField(max_length=300,null=True,blank=True)
    profile=models.ForeignKey(Profile, on_delete=models.CASCADE,null=True,blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name
    

class TypeOfDegree(models.Model):
    name=models.CharField(max_length=300,null=True,blank=True)
    profile=models.ForeignKey(Profile, on_delete=models.CASCADE,null=True,blank=True)

    def __str__(self):
        return self.name



class FieldOfInterest(models.Model):
    name=models.CharField(max_length=300)
    profile=models.ForeignKey(Profile, on_delete=models.CASCADE,null=True,blank=True)

    def __str__(self):
        return self.name


class Feedback(models.Model):
    content=models.CharField(max_length=500,null=True,blank=True)
    emoji = models.CharField(max_length=100,null=True,blank=True)
    profile=models.ForeignKey(Profile, on_delete=models.CASCADE,null=True,blank=True)
    created = models.DateTimeField(null=True,blank=True,auto_now_add=True)

    def __str__(self):
        return self.content

    class Meta:
        ordering = ("-created",)


class Institute(models.Model):
    name=models.CharField(max_length=300,null=True,blank=True)
    city=models.CharField(max_length=30,null=True,blank=True)
    state=models.CharField(max_length=30,null=True,blank=True)
    profile=models.ForeignKey(Profile, on_delete=models.CASCADE,null=True,blank=True)

    def __str__(self):
        return self.name











