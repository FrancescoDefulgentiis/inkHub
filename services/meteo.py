import requests

class Meteo_controller:
    def __init__(self, location, unit):
        self.location = location
        self.unit = unit
        self.api_key = 'your_api_key_here'  
        self.base_url = 'http://api.openweathermap.org/data/2.5/weather'

    def get_weather_data(self):
        params = {
            'q': self.location,
            'units': 'metric' if self.unit == 'C' else 'imperial',
            'appid': self.api_key
        }
        response = requests.get(self.base_url, params=params)
        if response.status_code == 200:
            return response.json()
        else:
            return None
