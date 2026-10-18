"""La validación solo escribe en columnas de resultado, nunca en datos del cliente."""
import re
import unicodedata
from fastapi import HTTPException

ALIAS={
 'depot':['OK','OK DEPOT','EXISTE EN DEPOT','ESTADO DEPOT'],
 'marca':['MARCA'],'cliente':['CLIENTE'],
 'fisica':['CANTIDAD FISICA','CANTIDADFISICA','CANT FISICA','CANTIDAD VALIDADA'],
 'validacion':['VALIDACION','ESTADO'],'desface':['DESFACE','DESFASE','DIFERENCIA'],
 'pallet':['PALLET','PALETA'],'posicion':['POSICION','POSICION REAL'],
 'codigoBarra':['CODIGO BARRA','CODIGOBARRA','CODIGO BARRAS','CODIGO DE BARRAS'],
 'cantidadIncidencia':['CANT CON INCIDENCIA','CANTIDAD CON INCIDENCIA','CANT CON INCIDENCIA DIFERENCIA'],
 'incidencia':['TIPO DE INCIDENCIA','TIPO INCIDENCIA','INCIDENCIA','INCIDENCIAS'],
 'observacion':['OBSERVACION','OBSERVACIONES'],
 'evidencia':['EVIDENCIA FOTOGRAFICA DIR URL DRIVE','CARPETA DRIVE','CARPETA DRIVE DEL SKU']}

def normalizar(v):
 return re.sub('[^A-Z0-9]+',' ',unicodedata.normalize('NFKD',str(v)).encode('ascii','ignore').decode().upper()).strip()

def validar_columnas(formato,columnas):
 protegidas={v for k,v in formato.get('columnas',{}).items() if k not in ALIAS}
 for rol,i in columnas.items():
  titulo=formato['encabezados'][i];clave=normalizar(titulo)
  roles=[k for k,vs in ALIAS.items() if clave in vs]
  if clave in {'SKU','ITEM','CODIGO','DESCRIPCION','CANTIDAD','FACTURA','EMBARQUE','REFERENCIAPEDIDO','REFERENCIA PEDIDO','PRECIOUNIT','PRECIOTOTAL'} or i in protegidas or roles and rol not in roles or not roles and formato.get('columnas',{}).get(rol)!=i:
   raise HTTPException(422,f'La columna {i+1} · {titulo} es de origen o corresponde a otro dato. Selecciona una columna de resultado de {rol}; si no existe, usa el informe con columnas adicionales.')
