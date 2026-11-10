"""El nuevo generador no reutiliza como vigente un documento anterior defectuoso."""
from app.models import AppInforme
from app.services import informes,app_modelo as m
from tests.test_adjuntos_independientes_65 import generar,cuenta_correo


def test_revision_64_se_conserva_historica_pero_obliga_regenerar(cliente,db,cuenta_correo,monkeypatch):
    codigo,_=cuenta_correo
    f=generar(cliente,codigo)
    # La API confirmó en otra sesión; renovar la instantánea REPEATABLE READ.
    db.rollback();r=m.obtener(db,codigo)
    actual=informes.huella_contenido(db,r);original=informes.json.dumps
    def formato64(valor,*args,**kwargs):
        if isinstance(valor,dict) and 'revisionFormato' in valor:valor={**valor,'revisionFormato':64}
        return original(valor,*args,**kwargs)
    with monkeypatch.context() as contexto:
        contexto.setattr(informes.json,'dumps',formato64)
        anterior=informes.huella_contenido(db,r)
    assert anterior!=actual
    registro=db.get(AppInforme,f['id']);assert registro is not None
    registro.datos={**registro.datos,'huellaContenido':anterior};db.commit()
    ruta='/api/operacion/recepciones/'+codigo
    assert not cliente.get(ruta+'/informe-actual?formato=envio-ampliado').json()['actual']
    assert cliente.get('/api/operacion/informes/'+f['id']+'/descarga').status_code==200
    assert cliente.get(ruta+'/informes').json()[0]['id']==f['id']
