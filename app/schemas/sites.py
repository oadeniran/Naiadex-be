from typing import Any

from pydantic import BaseModel, Field


class City(BaseModel):
    id: str
    name: str
    longitude: float
    latitude: float


class Site(BaseModel):
    code: str
    name: str = ""                       # some official sites have blank names
    city: City | None = None
    latitude: float
    longitude: float
    altitude: float | None = None
    polygon: dict[str, Any] | None = None   # GeoJSON FeatureCollection, passed through


class UserSiteCreate(BaseModel):
    name: str
    latitude: float
    longitude: float


class UserSite(UserSiteCreate):
    id: str
    username: str