import requests
import threading
import os
from time import sleep
from dotenv import load_dotenv
class Meteo_controller:
    def __init__(self, location, unit):
        load_dotenv()
        self.location = location
        self.unit = unit
        self.stop_flag= False
        self.response = None
        self.thread = None
        self.key = os.getenv('OPENWEATHER_API_KEY')
        self.forecast_url = 'http://api.weatherapi.com/v1/forecast.json'

    def setStopFlag(self, status):
        self.stop_flag = status
        
    def thread_function(self):

        forecast_params = {
            'q': self.location,
            'key': self.key,
            'aqi': 'yes',
        }
        
        while not self.stop_flag:
            print("Fetching data from the API")
            forecast_url = requests.Request('GET', self.forecast_url, params=forecast_params).prepare().url

            forecast_response = requests.get(forecast_url)

            if forecast_response.status_code == 200:
                weather_data = forecast_response.json()

                forecasts = {}
                for forecast in weather_data['forecast']['forecastday'][0]['hour']:
                    forecasts[forecast['time']] = {
                        'temp': forecast['temp_c'],
                        'condition': forecast['condition']['text'],
                        'precip': forecast['precip_mm']
                }

                data = {
                    'location': self.location,
                    'unit': self.unit,
                    'max_temp': weather_data['forecast']['forecastday'][0]['day']['maxtemp_c'],
                    'min_temp': weather_data['forecast']['forecastday'][0]['day']['mintemp_c'],
                    'max_wind': weather_data['forecast']['forecastday'][0]['day']['maxwind_kph'],
                    'total_precip': weather_data['forecast']['forecastday'][0]['day']['totalprecip_mm'],
                    'avg_humidity': weather_data['forecast']['forecastday'][0]['day']['avghumidity'],
                    'sunset': weather_data['forecast']['forecastday'][0]['astro']['sunset'],
                    'sunrise': weather_data['forecast']['forecastday'][0]['astro']['sunrise'],
                    'forecasts': forecasts
                }

                self.response = data
            else:
                print("Error while fetching data from the API")
                print("status code: ", forecast_response.status_code)

            sleep(1)

        
    def start_thread(self,):
        self.stop_flag = False
        self.thread = threading.Thread(target=self.thread_function)
        self.thread.start()
