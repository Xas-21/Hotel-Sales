from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType


class Command(BaseCommand):
    help = 'Populate user groups with predefined roles and permissions'

    def handle(self, *args, **options):
        # Define user groups/roles
        groups_data = [
            {
                'name': 'Director',
                'description': 'Full system access and management capabilities'
            },
            {
                'name': 'Sales Manager',
                'description': 'Manage sales team and approve requests'
            },
            {
                'name': 'Sales Executive',
                'description': 'Create and manage client requests'
            },
            {
                'name': 'Sales Coordinator',
                'description': 'Coordinate sales activities and support'
            },
            {
                'name': 'Admin',
                'description': 'System administration and configuration'
            },
            {
                'name': 'Viewer',
                'description': 'Read-only access to system data'
            }
        ]

        self.stdout.write(self.style.MIGRATE_HEADING('Creating User Groups...'))
        
        for group_data in groups_data:
            group, created = Group.objects.get_or_create(
                name=group_data['name']
            )
            
            if created:
                self.stdout.write(
                    self.style.SUCCESS(f'✓ Created group: {group.name}')
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f'• Group already exists: {group.name}')
                )

        self.stdout.write(
            self.style.SUCCESS('\n✅ Successfully populated user groups!')
        )
        self.stdout.write(
            self.style.MIGRATE_LABEL(f'\nTotal groups created: {Group.objects.count()}')
        )
        
        # List all groups
        self.stdout.write(self.style.MIGRATE_HEADING('\nAvailable Groups:'))
        for group in Group.objects.all().order_by('name'):
            self.stdout.write(f'  • {group.name}')


