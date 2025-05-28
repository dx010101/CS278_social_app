from django.core.management.base import BaseCommand
from django.contrib.auth.models import User

class Command(BaseCommand):
    help = 'Create fake users: amy, bob, tom with password 123456'

    def handle(self, *args, **kwargs):
        users = ['amy', 'bob', 'tom']
        for username in users:
            if not User.objects.filter(username=username).exists():
                User.objects.create_user(username=username, password='123456')
                self.stdout.write(self.style.SUCCESS(f'Created user: {username}'))
            else:
                self.stdout.write(self.style.WARNING(f'User already exists: {username}')) 