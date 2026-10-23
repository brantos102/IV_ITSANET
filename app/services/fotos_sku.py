"""Vínculos de producto vigentes con compatibilidad de fotografías antiguas."""
from sqlalchemy import select
from app.models import AppArchivo, AppArchivoSku, AppEvento, AppEvidencia
from app.services.normalize import normalizar_sku


def ids_sku(db, codigo, sku):
    sku = normalizar_sku(sku)
    activas = db.execute(select(AppEvidencia.archivo_id, AppEvidencia.sku).where(AppEvidencia.recepcion == codigo,
        AppEvidencia.eliminado_en.is_(None), AppEvidencia.sku.is_not(None), AppEvidencia.sku != '')).all()
    vinculadas = {ident for ident, _ in activas}
    ids = {ident for ident, codigo_sku in activas if codigo_sku == sku}
    antiguas = set(db.scalars(select(AppArchivoSku.archivo_id).join(AppArchivo,
        AppArchivo.id == AppArchivoSku.archivo_id).where(AppArchivo.recepcion == codigo, AppArchivoSku.sku == sku)))
    ids.update(antiguas - vinculadas)
    for evento in db.scalars(select(AppEvento).where(AppEvento.recepcion == codigo, AppEvento.sku == sku)):
        for url in (evento.datos or {}).get('fotos', []):
            ident = str(url).split('/api/app/archivos/')[-1].split('?')[0]
            if ident not in vinculadas: ids.add(ident)
    return ids
