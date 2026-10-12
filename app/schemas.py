"""Contratos de entrada/salida de la API."""
from __future__ import annotations

from pydantic import BaseModel, Field


class LoginIn(BaseModel):
    usuario: str
    pin: str


class LookupIn(BaseModel):
    codigo: str = Field(min_length=1, max_length=120)


class ScanIn(BaseModel):
    codigo: str = Field(min_length=1, max_length=120)
    cantidad: float
    pallet: str = Field(min_length=1, max_length=40)
    estado_fisico: str = "BUENO"
    ean: str | None = None
    observacion: str | None = None
    confirmar_sobrante: bool = False
    idempotency_key: str | None = Field(default=None, max_length=80)
    dispositivo: str | None = None


class AjusteIn(BaseModel):
    codigo: str
    cantidad: float
    pallet: str
    motivo: str = Field(min_length=3)


class AnularIn(BaseModel):
    motivo: str = Field(min_length=3, max_length=300)


class MotivoIn(BaseModel):
    motivo: str = Field(min_length=3, max_length=300)


class RecepcionIn(BaseModel):
    codigo: str = Field(min_length=1, max_length=80)
    cliente: str = "VENTURA"
    descripcion: str | None = None
    bultos_declarados: int | None = None


class OperadorIn(BaseModel):
    usuario: str = Field(min_length=3, max_length=50)
    nombre: str = Field(min_length=2, max_length=120)
    pin: str = Field(min_length=4, max_length=20)
    rol: str = "OPERADOR"


class PendienteIn(BaseModel):
    estado: str
    ean: str | None = None
    notas: str | None = None
