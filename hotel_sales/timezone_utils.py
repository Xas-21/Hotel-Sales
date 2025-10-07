"""
Timezone detection and management utilities.
"""
import json
import requests
from django.utils import timezone
from django.conf import settings
import pytz


def get_timezone_from_coordinates(lat, lon):
    """
    Get timezone from coordinates using timezone API.
    """
    try:
        # Using timezone API to get timezone from coordinates
        response = requests.get(
            f'https://api.timezonedb.com/v2.1/get-time-zone',
            params={
                'key': 'YOUR_API_KEY',  # You can get free API key from timezonedb.com
                'format': 'json',
                'by': 'position',
                'lat': lat,
                'lng': lon
            },
            timeout=5
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get('status') == 'OK':
                return data.get('zoneName')
    except Exception as e:
        print(f"Error getting timezone from coordinates: {e}")
    
    return None


def get_timezone_from_country_code(country_code):
    """
    Get timezone from country code (fallback method).
    """
    country_timezones = {
        'SA': 'Asia/Riyadh',  # Saudi Arabia
        'AE': 'Asia/Dubai',   # UAE
        'KW': 'Asia/Kuwait',  # Kuwait
        'QA': 'Asia/Qatar',   # Qatar
        'BH': 'Asia/Bahrain', # Bahrain
        'OM': 'Asia/Muscat',  # Oman
        'EG': 'Africa/Cairo', # Egypt
        'JO': 'Asia/Amman',   # Jordan
        'LB': 'Asia/Beirut',  # Lebanon
        'SY': 'Asia/Damascus', # Syria
        'IQ': 'Asia/Baghdad', # Iraq
        'US': 'America/New_York', # United States
        'GB': 'Europe/London', # United Kingdom
        'DE': 'Europe/Berlin', # Germany
        'FR': 'Europe/Paris',  # France
        'IT': 'Europe/Rome',   # Italy
        'ES': 'Europe/Madrid', # Spain
        'NL': 'Europe/Amsterdam', # Netherlands
        'BE': 'Europe/Brussels', # Belgium
        'CH': 'Europe/Zurich', # Switzerland
        'AT': 'Europe/Vienna', # Austria
        'SE': 'Europe/Stockholm', # Sweden
        'NO': 'Europe/Oslo',   # Norway
        'DK': 'Europe/Copenhagen', # Denmark
        'FI': 'Europe/Helsinki', # Finland
        'PL': 'Europe/Warsaw', # Poland
        'CZ': 'Europe/Prague', # Czech Republic
        'HU': 'Europe/Budapest', # Hungary
        'RO': 'Europe/Bucharest', # Romania
        'BG': 'Europe/Sofia', # Bulgaria
        'GR': 'Europe/Athens', # Greece
        'TR': 'Europe/Istanbul', # Turkey
        'RU': 'Europe/Moscow', # Russia
        'CN': 'Asia/Shanghai', # China
        'JP': 'Asia/Tokyo',    # Japan
        'KR': 'Asia/Seoul',    # South Korea
        'IN': 'Asia/Kolkata',  # India
        'TH': 'Asia/Bangkok',  # Thailand
        'SG': 'Asia/Singapore', # Singapore
        'MY': 'Asia/Kuala_Lumpur', # Malaysia
        'ID': 'Asia/Jakarta',  # Indonesia
        'PH': 'Asia/Manila',   # Philippines
        'VN': 'Asia/Ho_Chi_Minh', # Vietnam
        'AU': 'Australia/Sydney', # Australia
        'NZ': 'Pacific/Auckland', # New Zealand
        'CA': 'America/Toronto', # Canada
        'MX': 'America/Mexico_City', # Mexico
        'BR': 'America/Sao_Paulo', # Brazil
        'AR': 'America/Argentina/Buenos_Aires', # Argentina
        'CL': 'America/Santiago', # Chile
        'CO': 'America/Bogota', # Colombia
        'PE': 'America/Lima',  # Peru
        'VE': 'America/Caracas', # Venezuela
        'ZA': 'Africa/Johannesburg', # South Africa
        'NG': 'Africa/Lagos', # Nigeria
        'KE': 'Africa/Nairobi', # Kenya
        'MA': 'Africa/Casablanca', # Morocco
        'TN': 'Africa/Tunis',  # Tunisia
        'DZ': 'Africa/Algiers', # Algeria
        'LY': 'Africa/Tripoli', # Libya
        'SD': 'Africa/Khartoum', # Sudan
        'ET': 'Africa/Addis_Ababa', # Ethiopia
        'GH': 'Africa/Accra',  # Ghana
        'SN': 'Africa/Dakar',  # Senegal
        'CI': 'Africa/Abidjan', # Ivory Coast
        'CM': 'Africa/Douala', # Cameroon
        'UG': 'Africa/Kampala', # Uganda
        'TZ': 'Africa/Dar_es_Salaam', # Tanzania
        'ZW': 'Africa/Harare', # Zimbabwe
        'BW': 'Africa/Gaborone', # Botswana
        'NA': 'Africa/Windhoek', # Namibia
        'ZM': 'Africa/Lusaka', # Zambia
        'MW': 'Africa/Blantyre', # Malawi
        'MZ': 'Africa/Maputo', # Mozambique
        'MG': 'Indian/Antananarivo', # Madagascar
        'MU': 'Indian/Mauritius', # Mauritius
        'SC': 'Indian/Mahe',   # Seychelles
        'RE': 'Indian/Reunion', # Reunion
        'YT': 'Indian/Mayotte', # Mayotte
        'KM': 'Indian/Comoro', # Comoros
        'DJ': 'Africa/Djibouti', # Djibouti
        'SO': 'Africa/Mogadishu', # Somalia
        'ER': 'Africa/Asmara', # Eritrea
        'SS': 'Africa/Juba',   # South Sudan
        'CF': 'Africa/Bangui', # Central African Republic
        'TD': 'Africa/Ndjamena', # Chad
        'NE': 'Africa/Niamey', # Niger
        'BF': 'Africa/Ouagadougou', # Burkina Faso
        'ML': 'Africa/Bamako', # Mali
        'GN': 'Africa/Conakry', # Guinea
        'SL': 'Africa/Freetown', # Sierra Leone
        'LR': 'Africa/Monrovia', # Liberia
        'GM': 'Africa/Banjul', # Gambia
        'GW': 'Africa/Bissau', # Guinea-Bissau
        'CV': 'Atlantic/Cape_Verde', # Cape Verde
        'ST': 'Africa/Sao_Tome', # Sao Tome and Principe
        'GQ': 'Africa/Malabo', # Equatorial Guinea
        'GA': 'Africa/Libreville', # Gabon
        'CG': 'Africa/Brazzaville', # Republic of the Congo
        'CD': 'Africa/Kinshasa', # Democratic Republic of the Congo
        'AO': 'Africa/Luanda', # Angola
        'BI': 'Africa/Bujumbura', # Burundi
        'RW': 'Africa/Kigali', # Rwanda
    }
    
    return country_timezones.get(country_code, 'Asia/Riyadh')  # Default to Riyadh


def get_user_timezone(request):
    """
    Get user's timezone from session or detect from location.
    """
    # Check if timezone is already stored in session
    user_timezone = request.session.get('user_timezone')
    if user_timezone:
        return user_timezone
    
    # Default to Riyadh timezone
    return 'Asia/Riyadh'


def set_user_timezone(request, timezone_name):
    """
    Set user's timezone in session.
    """
    if timezone_name and timezone_name in pytz.all_timezones:
        request.session['user_timezone'] = timezone_name
        return True
    return False


def get_timezone_aware_datetime(dt, user_timezone=None):
    """
    Convert datetime to user's timezone.
    """
    if user_timezone:
        try:
            user_tz = pytz.timezone(user_timezone)
            if dt.tzinfo is None:
                # If datetime is naive, assume it's in UTC
                dt = pytz.UTC.localize(dt)
            return dt.astimezone(user_tz)
        except Exception:
            pass
    
    # Fallback to default timezone
    return timezone.localtime(dt)


def format_datetime_for_user(dt, user_timezone=None, format_string='%Y-%m-%d %H:%M:%S'):
    """
    Format datetime for user's timezone.
    """
    local_dt = get_timezone_aware_datetime(dt, user_timezone)
    return local_dt.strftime(format_string)

