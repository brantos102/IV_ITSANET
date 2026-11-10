"""Indicadores y trazabilidad historica."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Operador
from app.security import usuario_actual
from app.services import kpi as kpi_svc

router = APIRouter(prefix="/api/kpi", tags=["kpi"])


@router.get("/resumen")
def resumen(desde: str | None = None, hasta: str | None = None,
            db: Session = Depends(get_db), _: Operador = Depends(usuario_actual)):
    return kpi_svc.kpis_globales(db, desde, hasta)


@router.get("/operadores")
def operadores(desde: str | None = None, hasta: str | None = None,
               db: Session = Depends(get_db), _: Operador = Depends(usuario_actual)):
    return kpi_svc.kpis_por_operador(db, desde, hasta)


@router.get("/skus")
def skus(limite: int = 100, solo_problematicos: bool = False,
         db: Session = Depends(get_db), _: Operador = Depends(usuario_actual)):
    return kpi_svc.kpis_por_sku(db, limite, solo_problematicos)


@router.get("/serie")
def serie(dias: int = 30, db: Session = Depends(get_db),
          _: Operador = Depends(usuario_actual)):
    return kpi_svc.serie_diaria(db, dias)


@router.get("/pendientes")
def pendientes(db: Session = Depends(get_db), _: Operador = Depends(usuario_actual)):
    return kpi_svc.skus_pendientes_creacion(db)
