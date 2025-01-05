from enum import Enum

class StateEnum(Enum):
    STARTUP = "startup"
    METEO = "Meteo"
    COTRAL = "Cotral"
    CLOCK = "Clock"
    PLANTS = "plants"
    MOCK = "mock"