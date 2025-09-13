from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from accounts.models import UserProfile


class Command(BaseCommand):
    help = 'Set up user roles and permissions for the Hotel Sales Management System'

    def handle(self, *args, **options):
        self.stdout.write('Setting up user roles and permissions...')
        
        # Define roles and their permissions
        roles_permissions = {
            'Admin': {
                'description': 'Full system access',
                'permissions': [
                    # Dashboard permissions
                    ('dashboard', 'view_dashboard'),
                    ('dashboard', 'view_calendar'),
                    
                    # Accounts permissions
                    ('accounts', 'add_account'),
                    ('accounts', 'change_account'),
                    ('accounts', 'delete_account'),
                    ('accounts', 'view_account'),
                    ('accounts', 'add_userprofile'),
                    ('accounts', 'change_userprofile'),
                    ('accounts', 'delete_userprofile'),
                    ('accounts', 'view_userprofile'),
                    
                    # Requests permissions
                    ('requests', 'add_request'),
                    ('requests', 'change_request'),
                    ('requests', 'delete_request'),
                    ('requests', 'view_request'),
                    ('requests', 'add_cancelledrequest'),
                    ('requests', 'change_cancelledrequest'),
                    ('requests', 'delete_cancelledrequest'),
                    ('requests', 'view_cancelledrequest'),
                    
                    # Agreements permissions
                    ('agreements', 'add_agreement'),
                    ('agreements', 'change_agreement'),
                    ('agreements', 'delete_agreement'),
                    ('agreements', 'view_agreement'),
                    
                    # Sales calls permissions
                    ('sales_calls', 'add_salescall'),
                    ('sales_calls', 'change_salescall'),
                    ('sales_calls', 'delete_salescall'),
                    ('sales_calls', 'view_salescall'),
                    
                    # Auth permissions
                    ('auth', 'add_user'),
                    ('auth', 'change_user'),
                    ('auth', 'view_user'),
                ]
            },
            'Manager': {
                'description': 'Management access to most features',
                'permissions': [
                    ('dashboard', 'view_dashboard'),
                    ('dashboard', 'view_calendar'),
                    ('accounts', 'add_account'),
                    ('accounts', 'change_account'),
                    ('accounts', 'view_account'),
                    ('requests', 'add_request'),
                    ('requests', 'change_request'),
                    ('requests', 'view_request'),
                    ('requests', 'add_cancelledrequest'),
                    ('requests', 'change_cancelledrequest'),
                    ('requests', 'view_cancelledrequest'),
                    ('agreements', 'add_agreement'),
                    ('agreements', 'change_agreement'),
                    ('agreements', 'view_agreement'),
                    ('sales_calls', 'add_salescall'),
                    ('sales_calls', 'change_salescall'),
                    ('sales_calls', 'view_salescall'),
                ]
            },
            'Sales': {
                'description': 'Sales team access',
                'permissions': [
                    ('dashboard', 'view_dashboard'),
                    ('dashboard', 'view_calendar'),
                    ('accounts', 'add_account'),
                    ('accounts', 'change_account'),
                    ('accounts', 'view_account'),
                    ('requests', 'add_request'),
                    ('requests', 'change_request'),
                    ('requests', 'view_request'),
                    ('agreements', 'view_agreement'),
                    ('sales_calls', 'add_salescall'),
                    ('sales_calls', 'change_salescall'),
                    ('sales_calls', 'view_salescall'),
                ]
            },
            'Staff': {
                'description': 'General staff access',
                'permissions': [
                    ('dashboard', 'view_dashboard'),
                    ('dashboard', 'view_calendar'),
                    ('accounts', 'view_account'),
                    ('requests', 'view_request'),
                    ('agreements', 'view_agreement'),
                    ('sales_calls', 'view_salescall'),
                ]
            },
            'Viewer': {
                'description': 'Read-only access',
                'permissions': [
                    ('dashboard', 'view_dashboard'),
                    ('accounts', 'view_account'),
                    ('requests', 'view_request'),
                    ('agreements', 'view_agreement'),
                    ('sales_calls', 'view_salescall'),
                ]
            }
        }
        
        # Create groups and assign permissions
        for role_name, role_data in roles_permissions.items():
            group, created = Group.objects.get_or_create(name=role_name)
            
            if created:
                self.stdout.write(f'Created role: {role_name}')
            else:
                self.stdout.write(f'Updated role: {role_name}')
            
            # Clear existing permissions
            group.permissions.clear()
            
            # Add permissions to group
            for app_label, codename in role_data['permissions']:
                try:
                    permission = Permission.objects.get(
                        codename=codename,
                        content_type__app_label=app_label
                    )
                    group.permissions.add(permission)
                    
                except Permission.DoesNotExist:
                    self.stdout.write(
                        self.style.WARNING(
                            f'Permission {app_label}.{codename} not found - skipping'
                        )
                    )
                except Permission.MultipleObjectsReturned:
                    self.stdout.write(
                        self.style.WARNING(
                            f'Multiple permissions found for {app_label}.{codename} - skipping'
                        )
                    )
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'Configured {group.permissions.count()} permissions for {role_name}'
                )
            )
        
        self.stdout.write(
            self.style.SUCCESS('Successfully set up all user roles and permissions!')
        )