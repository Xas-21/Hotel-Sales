from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from requests.models import EventAgenda, Request
from .models import EventBooking, MeetingRoom

def map_meeting_room_to_agenda_name(instance):
    """Map MeetingRoom name to EventAgenda room name"""
    if not instance.meeting_rooms.exists():
        return 'All Halls'
    
    room_name = instance.meeting_rooms.first().name
    room_name_mapping = {
        'All Halls': 'All Halls',
        'IKMA': 'IKMA',
        'HEGRA': 'HEGRA',
        'DADAN': 'DADAN', 
        'ALJADIDA': 'AL JADIDA',  # Map no space to space
        'Board Room': 'Board Room',
        'Al Badia': 'Al Badiya',  # Map different spelling
        'La Palma': 'La Palma'
    }
    return room_name_mapping.get(room_name, room_name)

def map_agenda_room_to_meeting_room_name(agenda_room_name):
    """Map EventAgenda room name to MeetingRoom name"""
    agenda_to_meeting_mapping = {
        'All Halls': 'All Halls',
        'IKMA': 'IKMA',
        'HEGRA': 'HEGRA',
        'DADAN': 'DADAN',
        'AL JADIDA': 'ALJADIDA',  # Map space to no space
        'Board Room': 'Board Room',
        'Al Badiya': 'Al Badia',  # Map different spelling
        'La Palma': 'La Palma'
    }
    return agenda_to_meeting_mapping.get(agenda_room_name, agenda_room_name)

def map_meeting_room_to_agenda_name_from_booking(booking_instance):
    """Map EventBooking meeting rooms to EventAgenda room name"""
    if not booking_instance.meeting_rooms.exists():
        return 'All Halls'
    
    room_name = booking_instance.meeting_rooms.first().name
    room_name_mapping = {
        'All Halls': 'All Halls',
        'IKMA': 'IKMA',
        'HEGRA': 'HEGRA',
        'DADAN': 'DADAN', 
        'ALJADIDA': 'AL JADIDA',  # Map no space to space
        'Board Room': 'Board Room',
        'Al Badia': 'Al Badiya',  # Map different spelling
        'La Palma': 'La Palma'
    }
    return room_name_mapping.get(room_name, room_name)

@receiver(post_save, sender=EventAgenda)
def sync_event_agenda_to_booking(sender, instance, created, **kwargs):
    """
    Automatically sync EventAgenda to EventBooking.
    Only syncs EVENT data, not accommodation data.
    """
    # Skip if this is a signal-triggered save to prevent circular updates
    if hasattr(instance, '_skip_signal'):
        return
        
    try:
        # Find existing EventBooking for this request or create new one
        event_booking = EventBooking.objects.filter(request=instance.request).first()
        if not event_booking:
            # Create new EventBooking
            event_booking = EventBooking.objects.create(
                request=instance.request,
                event_name=instance.event_name or instance.agenda_details or f"Event for {instance.request.account.name}",
                account=instance.request.account,
                event_date=instance.event_date,
                start_time=instance.start_time,
                end_time=instance.end_time,
                coffee_break_time=instance.coffee_break_time,
                lunch_time=instance.lunch_time,
                dinner_time=instance.dinner_time,
                style=instance.style,
                rental_fees_per_day=instance.rental_fees_per_day,
                rate_per_person=instance.rate_per_person,
                total_persons=instance.total_persons,
                packages=instance.packages,
                status=instance.request.status,
                notes=instance.request.notes,
                # Sync deadline fields
                request_received_date=instance.request.request_received_date,
                offer_acceptance_deadline=instance.request.offer_acceptance_deadline,
                deposit_deadline=instance.request.deposit_deadline,
                full_payment_deadline=instance.request.full_payment_deadline,
            )
        else:
            # Update existing EventBooking
            event_booking.event_name = instance.event_name or instance.agenda_details or f"Event for {instance.request.account.name}"
            event_booking.event_date = instance.event_date
            event_booking.start_time = instance.start_time
            event_booking.end_time = instance.end_time
            event_booking.coffee_break_time = instance.coffee_break_time
            event_booking.lunch_time = instance.lunch_time
            event_booking.dinner_time = instance.dinner_time
            event_booking.style = instance.style
            event_booking.rental_fees_per_day = instance.rental_fees_per_day
            event_booking.rate_per_person = instance.rate_per_person
            event_booking.total_persons = instance.total_persons
            event_booking.packages = instance.packages
            event_booking.status = instance.request.status
            event_booking.notes = instance.request.notes
            # Sync deadline fields
            event_booking.request_received_date = instance.request.request_received_date
            event_booking.offer_acceptance_deadline = instance.request.offer_acceptance_deadline
            event_booking.deposit_deadline = instance.request.deposit_deadline
            event_booking.full_payment_deadline = instance.request.full_payment_deadline
            event_booking._skip_signal = True  # Prevent circular update
            event_booking.save()
        
        # Sync meeting rooms
        try:
            # Clear existing rooms first
            event_booking.meeting_rooms.clear()
            # Map EventAgenda room name to MeetingRoom name
            room_name_mapping = {
                'All Halls': 'All Halls',
                'IKMA': 'IKMA',
                'HEGRA': 'HEGRA', 
                'DADAN': 'DADAN',
                'AL JADIDA': 'ALJADIDA',  # Map space to no space
                'Board Room': 'Board Room',
                'Al Badiya': 'Al Badia',  # Map different spelling
                'La Palma': 'La Palma'
            }
            mapped_room_name = room_name_mapping.get(instance.meeting_room_name, instance.meeting_room_name)
            room = MeetingRoom.objects.get(name=mapped_room_name)
            event_booking.meeting_rooms.add(room)
        except MeetingRoom.DoesNotExist:
            pass
            
    except Exception as e:
        print(f"Error syncing EventAgenda to EventBooking: {e}")

@receiver(post_save, sender=EventBooking)
def sync_event_booking_to_agenda(sender, instance, created, **kwargs):
    """
    Automatically sync EventBooking to EventAgenda.
    This ensures bidirectional sync.
    """
    # Skip if this is a signal-triggered save to prevent circular updates
    if hasattr(instance, '_skip_signal'):
        return
        
    try:
        if instance.request:
            # Update Request status and deadline fields to match EventBooking
            request_updated = False
            if instance.request.status != instance.status:
                instance.request.status = instance.status
                request_updated = True
            if instance.request.request_received_date != instance.request_received_date:
                instance.request.request_received_date = instance.request_received_date
                request_updated = True
            if instance.request.offer_acceptance_deadline != instance.offer_acceptance_deadline:
                instance.request.offer_acceptance_deadline = instance.offer_acceptance_deadline
                request_updated = True
            if instance.request.deposit_deadline != instance.deposit_deadline:
                instance.request.deposit_deadline = instance.deposit_deadline
                request_updated = True
            if instance.request.full_payment_deadline != instance.full_payment_deadline:
                instance.request.full_payment_deadline = instance.full_payment_deadline
                request_updated = True
            
            if request_updated:
                instance.request._skip_signal = True  # Prevent circular update
                instance.request.save()
            
            # Get or create EventAgenda for this request
            event_agenda, agenda_created = EventAgenda.objects.get_or_create(
                request=instance.request,
                event_date=instance.event_date,
                defaults={
                    'start_time': instance.start_time,
                    'end_time': instance.end_time,
                    'event_name': instance.event_name,
                    'meeting_room_name': map_meeting_room_to_agenda_name_from_booking(instance),
                    'agenda_details': instance.event_name,
                    'coffee_break_time': instance.coffee_break_time,
                    'lunch_time': instance.lunch_time,
                    'dinner_time': instance.dinner_time,
                    'style': instance.style,
                    'rental_fees_per_day': instance.rental_fees_per_day,
                    'rate_per_person': instance.rate_per_person,
                    'total_persons': instance.total_persons,
                    'packages': instance.packages,
                }
            )
            
            if not agenda_created:
                # Update existing EventAgenda
                event_agenda.start_time = instance.start_time
                event_agenda.end_time = instance.end_time
                event_agenda.event_name = instance.event_name
                event_agenda.meeting_room_name = map_meeting_room_to_agenda_name_from_booking(instance)
                event_agenda.agenda_details = instance.event_name
                event_agenda.coffee_break_time = instance.coffee_break_time
                event_agenda.lunch_time = instance.lunch_time
                event_agenda.dinner_time = instance.dinner_time
                event_agenda.style = instance.style
                event_agenda.rental_fees_per_day = instance.rental_fees_per_day
                event_agenda.rate_per_person = instance.rate_per_person
                event_agenda.total_persons = instance.total_persons
                event_agenda.packages = instance.packages
                event_agenda._skip_signal = True  # Prevent circular update
                event_agenda.save()
                
    except Exception as e:
        print(f"Error syncing EventBooking to EventAgenda: {e}")

@receiver(post_delete, sender=EventAgenda)
def delete_event_booking_on_agenda_delete(sender, instance, **kwargs):
    """
    Delete EventBooking when EventAgenda is deleted.
    """
    try:
        EventBooking.objects.filter(request=instance.request, event_date=instance.event_date).delete()
    except Exception as e:
        print(f"Error deleting EventBooking: {e}")

@receiver(post_delete, sender=EventBooking)
def delete_event_agenda_on_booking_delete(sender, instance, **kwargs):
    """
    Delete EventAgenda when EventBooking is deleted.
    """
    try:
        if instance.request:
            EventAgenda.objects.filter(request=instance.request, event_date=instance.event_date).delete()
    except Exception as e:
        print(f"Error deleting EventAgenda: {e}")
