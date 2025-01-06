from Display_template import Display_template

class meteo_display(Display_template):
    def write_on_display(self,data):
            # This are all the needed data for the interface
        print('Location: ' + data['location'])
        print('Max Temp: ' + str(data['max_temp']))
        print('Min Temp: ' + str(data['min_temp']))
        print('Max Wind: ' + str(data['max_wind']))
        print('Total Precip: ' + str(data['total_precip']))
        print('Avg Humidity: ' + str(data['avg_humidity']))
        print('Sunset: ' + data['sunset'])
        print('Sunrise: ' + data['sunrise'])
        print('temperatures-> ' + ' -> '.join([str(data['forecasts'][key]['temp']) for key in data['forecasts']]))
        print('precip-> ' + ' -> '.join([str(data['forecasts'][key]['precip']) for key in data['forecasts']]))
        print('now: ' + data['forecasts']['2025-01-05 00:00']['condition'] + '\nin an hour: ' + data['forecasts']['2025-01-05 01:00']['condition'] + '\nin three hours: ' + data['forecasts']['2025-01-05 03:00']['condition'] + '\nin twelve hours: ' + data['forecasts']['2025-01-05 12:00']['condition'])
