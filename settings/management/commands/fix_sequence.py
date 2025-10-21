from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = 'Fix the ID sequence for CancellationReason table'

    def handle(self, *args, **options):
        with connection.cursor() as cursor:
            # Get the maximum ID from the table
            cursor.execute("SELECT MAX(id) FROM settings_cancellationreason;")
            max_id = cursor.fetchone()[0]
            
            if max_id:
                # Set the sequence to start from max_id + 1
                cursor.execute(f"SELECT setval('settings_cancellationreason_id_seq', {max_id});")
                self.stdout.write(
                    self.style.SUCCESS(f'Successfully updated sequence to start from {max_id + 1}')
                )
            else:
                self.stdout.write(
                    self.style.WARNING('No records found in settings_cancellationreason table')
                )
