from django.core.management.base import BaseCommand
from event_management.models import MeetingRoom


class Command(BaseCommand):
    help = 'Populate meeting rooms with predefined data'

    def handle(self, *args, **options):
        # Combined rooms (Main Halls) - Individual capacity 34, Combined capacity 150
        combined_rooms = [
            {
                'name': 'IKMA',
                'display_name': 'IKMA Hall',
                'room_type': 'combined',
                'capacity': 34,
                'is_combined': True,
                'combined_group': 'main_halls',
                'description': 'Main conference hall with modern facilities (34 individual, 150 when combined)'
            },
            {
                'name': 'HEGRA',
                'display_name': 'HEGRA Hall',
                'room_type': 'combined',
                'capacity': 34,
                'is_combined': True,
                'combined_group': 'main_halls',
                'description': 'Secondary conference hall (34 individual, 150 when combined)'
            },
            {
                'name': 'DADAN',
                'display_name': 'DADAN Hall',
                'room_type': 'combined',
                'capacity': 34,
                'is_combined': True,
                'combined_group': 'main_halls',
                'description': 'Medium-sized conference room (34 individual, 150 when combined)'
            },
            {
                'name': 'ALJADIDA',
                'display_name': 'AL JADIDA Hall',
                'room_type': 'combined',
                'capacity': 34,
                'is_combined': True,
                'combined_group': 'main_halls',
                'description': 'Versatile conference space (34 individual, 150 when combined)'
            }
        ]

        # Separate rooms
        separate_rooms = [
            {
                'name': 'Board Room',
                'display_name': 'Board Room',
                'room_type': 'separate',
                'capacity': 20,
                'is_combined': False,
                'description': 'Executive board room for small meetings'
            },
            {
                'name': 'Al Badia',
                'display_name': 'Al Badia Meeting Room',
                'room_type': 'separate',
                'capacity': 30,
                'is_combined': False,
                'description': 'Dedicated meeting room in the resort'
            },
            {
                'name': 'La Palma',
                'display_name': 'La Palma Restaurant',
                'room_type': 'separate',
                'capacity': 80,
                'is_combined': False,
                'description': 'Main restaurant space for events'
            }
        ]

        # Create combined rooms
        for room_data in combined_rooms:
            room, created = MeetingRoom.objects.get_or_create(
                name=room_data['name'],
                defaults=room_data
            )
            if created:
                self.stdout.write(
                    self.style.SUCCESS(f'Created combined room: {room.display_name}')
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f'Combined room already exists: {room.display_name}')
                )

        # Create separate rooms
        for room_data in separate_rooms:
            room, created = MeetingRoom.objects.get_or_create(
                name=room_data['name'],
                defaults=room_data
            )
            if created:
                self.stdout.write(
                    self.style.SUCCESS(f'Created separate room: {room.display_name}')
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f'Separate room already exists: {room.display_name}')
                )

        self.stdout.write(
            self.style.SUCCESS('Successfully populated meeting rooms!')
        )
