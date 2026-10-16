"""Contratos de entrada/salida de la API."""
from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    pin: str = Field(min_length=4, max_length=128)
    rol: str = "OPERADOR"
    email: str | None = Field(default=None, max_length=160)

    @field_validator("usuario")
    @classmethod
    def validar_usuario(cls, value: str) -> str:
        value = value.strip().lower()
        if not re.fullmatch(r"[a-z0-9._-]{3,50}", value):
            raise ValueError("Usuario: de 3 a 50 letras, numeros, puntos o guiones")
        return value

    @field_validator("email")
    @classmethod
    def validar_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]{2,}", value):
            raise ValueError("Escribe un correo electronico valido")
        return value


class RegistroIn(OperadorIn):
    # La peticion publica nunca elige rol ni se activa a si misma.
    model_config = ConfigDict(extra="forbid")
    rol: str = Field(default="OPERADOR", exclude=True, pattern="^OPERADOR$")
    email: str = Field(max_length=160)
    pin: str = Field(min_length=6, max_length=128)


class OperadorCambio(BaseModel):
    model_config = ConfigDict(extra="forbid")
    usuario: str | None = Field(default=None, min_length=3, max_length=50)
    nombre: str | None = Field(default=None, min_length=2, max_length=120)
    rol: str | None = None
    activo: bool | None = None
    email: str | None = Field(default=None, max_length=160)

    @field_validator('email')
    @classmethod
    def validar_email(cls, value):
        return OperadorIn.validar_email(value)

    @field_validator("usuario")
    @classmethod
    def validar_usuario(cls, value: str | None) -> str | None:
        return OperadorIn.validar_usuario(value) if value is not None else None

    @field_validator("nombre")
    @classmethod
    def validar_nombre(cls, value: str | None) -> str | None:
        if value is not None and len(value.strip()) < 2:
            raise ValueError("Escribe nombre y apellido")
        return value.strip() if value is not None else None


class PendienteIn(BaseModel):
    estado: str
    ean: str | None = None
    notas: str | None = None
