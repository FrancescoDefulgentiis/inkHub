from enums.stateEnum import StateEnum as stateEnum

class Display_controller:

    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.data = None
        self.state = None

    def write_on_display(self, state, data):
        if self.data != data and data is not None:
            self.data = data
            match state:
                case stateEnum.STARTUP:
                    print(data)
                    
                case stateEnum.METEO:
                    print(data)

                case stateEnum.COTRAL:
                    print(data)

                case stateEnum.CLOCK:
                    print(data)
                case _:
                    print("Invalid state.")
        else:
            pass