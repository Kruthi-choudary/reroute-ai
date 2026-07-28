from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class FlightStatusResult:
    flight_iata:     str
    status:          str             # "scheduled" | "en-route" | "landed" | "cancelled"
    dep_delayed_min: int  = 0
    arr_delayed_min: int  = 0
    dep_estimated:   Optional[datetime] = None
    arr_estimated:   Optional[datetime] = None
    raw:             dict = field(default_factory=dict, repr=False)


class FlightDataProvider(ABC):
    """
    Contract for all flight status sources.
    The monitor never imports a concrete provider — only this class.
    """

    @abstractmethod
    def get_flight_status(
        self,
        flight_iata: str,
        dep_iata:    str,
        arr_iata:    str,
    ) -> Optional[FlightStatusResult]:
        """Return current status or None if the flight cannot be found."""
        ...

    @property
    def name(self) -> str:
        return self.__class__.__name__
