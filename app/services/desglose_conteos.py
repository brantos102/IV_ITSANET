"""Unidades por conteo, condición y ubicación, a partir del libro mayor activo."""

def segmentos(eventos,sku=None):
    anulados={e.get('anulaA') or e.get('refEvento') for e in eventos if e.get('tipo')=='ANULACION' or e.get('anulaA') or e.get('refEvento')}
    activos=[e for e in eventos if e.get('tipo')!='ANULACION' and not e.get('anulado') and e.get('id') not in anulados]
    correcciones={e['eventoId']:e['incidencias'] for e in activos if e.get('tipo')=='CALIDAD' and e.get('eventoId') and 'incidencias' in e}
    salida=[]
    for e in activos:
        if e.get('tipo') not in (None,'CONTEO') or float(e.get('cantidad') or 0)<=0 or sku is not None and e.get('sku')!=sku:continue
        cantidad=float(e['cantidad']);restante=cantidad
        incidencias=correcciones.get(e.get('id'),e.get('incidencias'))
        if incidencias is None:incidencias=[{'tipo':'MAL_ESTADO','nombre':'PNC','cantidad':cantidad,'pnc':True}] if e.get('estadoFisico')=='PNC' else []
        for f in incidencias:
            n=min(restante,max(0,float(f.get('cantidad') or 0)))
            if not n:continue
            restante-=n
            salida.append({'sku':e['sku'],'eventoId':e.get('id',''),'origen':e.get('origen',''),
                'cantidad':n,'estado':'PNC' if f.get('pnc') else 'INCIDENCIA','incidencia':f.get('nombre') or f.get('tipo',''),
                'pallet':f.get('pallet') or e.get('pallet',''),'posicion':e.get('posicionReal',''),'observacion':e.get('observacion',''),
                'sinDetalleUbicacion':bool(e.get('sinDetalleUbicacion') or '-' in str(e.get('pallet') or ''))})
        if restante>0:salida.append({'sku':e['sku'],'eventoId':e.get('id',''),'origen':e.get('origen',''),
            'cantidad':restante,'estado':'CONFORME','incidencia':'','pallet':e.get('pallet',''),
            'posicion':e.get('posicionReal',''),'observacion':e.get('observacion',''),
            'sinDetalleUbicacion':bool(e.get('sinDetalleUbicacion') or '-' in str(e.get('pallet') or ''))})
    return salida


def texto_ubicaciones(eventos,sku):
    return ' | '.join(f"{p['cantidad']:g} u. {p['estado']} · Pallet {p['pallet'] or 'sin registrar'} · Posición {p['posicion'] or 'sin registrar'}"+(f" · {p['incidencia']}" if p['incidencia'] else '')+(' · Distribución por pallet/posición por revisar' if p['sinDetalleUbicacion'] else '') for p in segmentos(eventos,sku))
