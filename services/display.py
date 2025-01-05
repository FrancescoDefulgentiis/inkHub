from enums.stateEnum import StateEnum as stateEnum

class Display_controller:

    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.data = None
        self.state = None
#{'location': 'Monterotondo', 'max_temp': 13.4, 'min_temp': 7.3, 'max_wind': 10.8, 'total_precip': 0.03, 'avg_humidity': 83, 'sunset': '04:52 PM', 'sunrise': '07:38 AM', 'forecasts': {'2025-01-05 00:00': {'temp': 7.3, 'condition': 'Patchy rain nearby', 'precip': 0.01}, '2025-01-05 01:00': {'temp': 7.6, 'condition': 'Partly Cloudy ', 'precip': 0.0}, '2025-01-05 02:00': {'temp': 8.1, 'condition': 'Partly Cloudy ', 'precip': 0.0}, '2025-01-05 03:00': {'temp': 8.6, 'condition': 'Patchy rain nearby', 'precip': 0.01}, '2025-01-05 04:00': {'temp': 8.8, 'condition': 'Patchy rain nearby', 'precip': 0.01}, '2025-01-05 05:00': {'temp': 8.8, 'condition': 'Patchy rain nearby', 'precip': 0.01}, '2025-01-05 06:00': {'temp': 9.4, 'condition': 'Partly Cloudy ', 'precip': 0.0}, '2025-01-05 07:00': {'temp': 9.5, 'condition': 'Partly Cloudy ', 'precip': 0.0}, '2025-01-05 08:00': {'temp': 9.8, 'condition': 'Overcast ', 'precip': 0.0}, '2025-01-05 09:00': {'temp': 10.3, 'condition': 'Overcast ', 'precip': 0.0}, '2025-01-05 10:00': {'temp': 10.9, 'condition': 'Overcast ', 'precip': 0.0}, '2025-01-05 11:00': {'temp': 11.8, 'condition': 'Cloudy ', 'precip': 0.0}, '2025-01-05 12:00': {'temp': 12.4, 'condition': 'Overcast ', 'precip': 0.0}, '2025-01-05 13:00': {'temp': 12.7, 'condition': 'Overcast ', 'precip': 0.0}, '2025-01-05 14:00': {'temp': 13.0, 'condition': 'Overcast ', 'precip': 0.0}, '2025-01-05 15:00': {'temp': 13.4, 'condition': 'Partly Cloudy ', 'precip': 0.0}, '2025-01-05 16:00': {'temp': 12.3, 'condition': 'Partly Cloudy ', 'precip': 0.0}, '2025-01-05 17:00': {'temp': 12.4, 'condition': 'Partly cloudy', 'precip': 0.0}, '2025-01-05 18:00': {'temp': 9.8, 'condition': 'Cloudy ', 'precip': 0.0}, '2025-01-05 19:00': {'temp': 9.5, 'condition': 'Partly Cloudy ', 'precip': 0.0}, '2025-01-05 20:00': {'temp': 9.2, 'condition': 'Partly Cloudy ', 'precip': 0.0}, '2025-01-05 21:00': {'temp': 9.0, 'condition': 'Partly Cloudy ', 'precip': 0.0}, '2025-01-05 22:00': {'temp': 9.0, 'condition': 'Cloudy ', 'precip': 0.0}, '2025-01-05 23:00': {'temp': 9.1, 'condition': 'Overcast ', 'precip': 0.0}}}
    def write_on_display(self, state, data):
        if self.data != data and data is not None:
            self.data = data
            match state:
                case stateEnum.STARTUP:
                    print(data)
                    
                case stateEnum.METEO:
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

                case stateEnum.COTRAL:
                    print(data)

                case stateEnum.CLOCK:
                    print(data)
                case _:
                    print("Invalid state.")
        else:
            pass