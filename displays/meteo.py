from Display_template import Display_template

class Meteo_display(Display_template):
    def write_on_display(self):     # This are all the needed self.data for the interface
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
        print('now: ' + self.data['forecasts']['2025-01-05 00:00']['condition'] + '\nin an hour: ' + self.data['forecasts']['2025-01-05 01:00']['condition'] + '\nin three hours: ' + self.data['forecasts']['2025-01-05 03:00']['condition'] + '\nin twelve hours: ' + self.data['forecasts']['2025-01-05 12:00']['condition'])