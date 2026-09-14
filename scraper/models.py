from typing import Optional

from pydantic import BaseModel, Field


class Listing(BaseModel):
    """Znormalizowany rekord oferty (jeden deal na grę)."""

    title: str = Field(..., description="Nazwa gry / tytuł oferty")
    price: Optional[float] = Field(
        None, description="Cena promocyjna. None gdy brak danych"
    )
    currency: Optional[str] = Field(None, description="Kod waluty ISO-4217, np. USD")
    url: str = Field(..., description="Link do oferty (redirect do sklepu)")
    location: Optional[str] = Field(
        None, description="Sklep / miejsce oferty, np. Steam"
    )
    image: Optional[str] = Field(None, description="URL miniatury")
    posted_at: Optional[str] = Field(None, description="Data publikacji w ISO-8601 UTC")


class ListingsResponse(BaseModel):
    query: str
    count: int
    source: str
    results: list[Listing]
