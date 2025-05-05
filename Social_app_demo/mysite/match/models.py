from django.db import models

class UserInfo(models.Model):
    name = models.CharField(max_length=100)
    interest = models.CharField(max_length=300)
    hometown = models.CharField(max_length=100, blank=True)
    major = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return self.name
      
# Create your models here.
