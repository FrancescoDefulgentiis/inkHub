from enum import Enum
from services.meteo import Meteo_controller as meteoController

class StateEnum(Enum):
    STARTUP = "startup"
    TRANSPORT = "transport"
    METEO = "meteo"