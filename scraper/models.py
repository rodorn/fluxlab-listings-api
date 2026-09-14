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
    # Pola dodatkowe (wstecznie kompatybilne — istniejący klienci ignorują nadmiarowe klucze).
    offset: int = Field(0, description="Przesunięcie zastosowane do wyników")
    limit: int = Field(20, description="Zastosowany limit liczby wyników")
    sort: Optional[str] = Field(
        None, description="Zastosowane sortowanie (np. price_asc / price_desc)"
    )
    total_available: int = Field(
        0,
        description="Liczba rekordów pobranych ze źródła w oknie (przed offset/limit)",
    )


class SourceInfo(BaseModel):
    """Opis jednego dostępnego źródła danych."""

    id: str = Field(..., description="Identyfikator źródła używany wewnętrznie")
    name: str = Field(..., description="Czytelna nazwa źródła")
    url: str = Field(..., description="Strona źródła")
    attribution_required: bool = Field(
        ..., description="Czy źródło wymaga atrybucji przy publikacji danych"
    )
    description: str = Field(..., description="Krótki opis zawartości źródła")


class SourcesResponse(BaseModel):
    count: int
    sources: list[SourceInfo]
