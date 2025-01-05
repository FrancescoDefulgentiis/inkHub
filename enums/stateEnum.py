from enum import Enum

class StateEnum(Enum):
    STARTUP = "startup"
    
    METEO = "meteo"
    COTRAL = "Cotral"
    CLOCK = "Clock"
    PLANTS = "plants"
    MOCK = "mock"