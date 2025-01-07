import requests
import threading
import os
from time import sleep
from dotenv import load_dotenv
from templates.Controller_template import Controller_template

class Weather_controller(Controller_template):
    def __init__(self, args):
        load_dotenv()
        self.location = args['location']
        unit = args['unit']
        self.temp_unit = 'c' if unit == 'metric' else 'f'
        self.wind_unit = 'kph' if unit == 'metric' else 'mph'
        self.precip_unit = 'mm' if unit == 'metric' else 'in'
        self.stop_thread= False
        self.response = None
        self.thread = threading.Thread(target=self.thread_function)
        self.key = os.getenv('OPENWEATHER_API_KEY')
        self.forecast_url = 'http://api.weatherapi.com/v1/forecast.json'
        self.refresh = args['refresh']

    def thread_function(self):

        forecast_params = {
            'q': self.location,
            'key': self.key,
            'aqi': 'yes',
        }
        
        while not self.stop_thread:
            forecast_url = requests.Request('GET', self.forecast_url, params=forecast_params).prepare().url

            forecast_response = requests.get(forecast_url)

            if forecast_response.status_code == 200:
                weather_data = forecast_response.json()

                forecasts = {}
                for forecast in weather_data['forecast']['forecastday'][0]['hour']:
                    forecasts[forecast['time_epoch']] = {
                        'temp': forecast['temp_{0}'.format(self.temp_unit)],
                        'condition': forecast['condition']['text'],
                        'precip': forecast['precip_mm']
                }
                                    
                data = {
                    'location': self.location,
                    'max_temp': weather_data['forecast']['forecastday'][0]['day']['maxtemp_{0}'.format(self.temp_unit)],
                    'min_temp': weather_data['forecast']['forecastday'][0]['day']['mintemp_{0}'.format(self.temp_unit)],
                    'max_wind': weather_data['forecast']['forecastday'][0]['day']['maxwind_{0}'.format(self.wind_unit)],
                    'total_precip': weather_data['forecast']['forecastday'][0]['day']['totalprecip_{0}'.format(self.precip_unit)],
                    'avg_humidity': weather_data['forecast']['forecastday'][0]['day']['avghumidity'],
                    'sunset': weather_data['forecast']['forecastday'][0]['astro']['sunset'],
                    'sunrise': weather_data['forecast']['forecastday'][0]['astro']['sunrise'],
                    'forecasts': forecasts
                }
                self.response = data
            else:
                print("Error while fetching data from the API")
                print("status code: ", forecast_response.status_code)

            sleep(self.refresh)

