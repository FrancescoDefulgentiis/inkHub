from templates.Display_template import Display_template
import time

class Weather_display(Display_template):
    def write_on_display(self):     # This are all the needed self.data for the interface

        unix_time_now = int(time.time())

        print('Location: ' + self.data['location'])
        print('Max Temp: ' + str(self.data['max_temp']))
        print('Min Temp: ' + str(self.data['min_temp']))
        print('Max Wind: ' + str(self.data['max_wind']))
        print('Total Precip: ' + str(self.data['total_precip']))
        print('Avg Humidity: ' + str(self.data['avg_humidity']))
        print('Sunset: ' + self.data['sunset'])
        print('Sunrise: ' + self.data['sunrise'])
        print('temperatures-> ' + ' -> '.join([str(self.data['forecasts'][key]['temp']) for key in self.data['forecasts']]))
        print('precip-> ' + ' -> '.join([str(self.data['forecasts'][key]['precip']) for key in self.data['forecasts']]))
        for key in self.data['forecasts']:
            if key >= unix_time_now and key < unix_time_now + 3600:
                print('Current forecast: ' + self.data['forecasts'][key]['condition'])
            elif key >= unix_time_now + 7200 and key < unix_time_now + 7200 + 3600:
                print('Forecast in 2 hours: ' + self.data['forecasts'][key]['condition'])
            elif key >= unix_time_now + 43200 and key < unix_time_now + 43200 + 3600:
                print('Forecast in 12 hours: ' + self.data['forecasts'][key]['condition'])