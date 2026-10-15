"""Registro -> pendiente -> aprobacion por supervisor -> acceso por correo."""
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models import Operador, Rol
from app.security import hash_pin


REGISTRO = {"usuario": "nuevo", "nombre": "Nuevo Operario",
            "email": "nuevo@itsanet.com", "pin": "secreto123"}


def test_registro_aprobacion_y_desactivacion(db, operadores):
    nuevo = TestClient(app)
    r = nuevo.post("/api/auth/registro", json=REGISTRO)
    assert r.status_code == 201, r.text
    assert r.json()["activo"] is False
    assert r.json()["rol"] == "OPERADOR"
    assert "pin_hash" not in r.json()
    assert nuevo.get("/api/auth/yo").status_code == 401
    r = nuevo.post("/api/auth/login", json={"usuario": REGISTRO["email"], "pin": REGISTRO["pin"]})
    assert r.status_code == 403, r.text
    assert r.json()["detail"]["codigo"] == "PENDIENTE_APROBACION"

    supervisor = TestClient(app)
    supervisor.post("/api/auth/login", json={"usuario": "sup", "pin": "1111"}).raise_for_status()
    fila = next(u for u in supervisor.get("/api/auth/operadores").json() if u["usuario"] == "nuevo")
    assert fila["email"] == REGISTRO["email"]
    assert fila["activo"] is False
    assert supervisor.patch(f"/api/auth/operadores/{fila['id']}", json={"activo": True}).status_code == 200
    for acceso in ("nuevo", " NUEVO@ITSANET.COM "):
        assert nuevo.post("/api/auth/login", json={"usuario": acceso, "pin": REGISTRO["pin"]}).status_code == 200
    assert nuevo.get("/api/auth/yo").json()["email"] == REGISTRO["email"]
    assert supervisor.patch(f"/api/auth/operadores/{fila['id']}", json={"activo": False}).status_code == 200
    assert nuevo.get("/api/auth/yo").status_code == 401


def test_operario_no_aprueba_ni_se_da_rol(db, operadores):
    c = TestClient(app)
    assert c.post("/api/auth/registro", json={**REGISTRO, "rol": "ADMIN", "activo": True}).status_code == 422
    r = c.post("/api/auth/registro", json=REGISTRO)
    assert r.status_code == 201
    assert c.patch(f"/api/auth/operadores/{r.json()['id']}", json={"activo": True}).status_code == 401
    c.post("/api/auth/login", json={"usuario": "op1", "pin": "2222"})
    assert c.get("/api/auth/operadores").status_code == 403
    assert c.patch(f"/api/auth/operadores/{r.json()['id']}", json={"activo": True}).status_code == 403


def test_supervisor_no_promueve_ni_edita_admin(db, operadores):
    admin = Operador(usuario="jefe", nombre="Jefe", pin_hash=hash_pin("123456"), rol=Rol.ADMIN)
    db.add(admin)
    db.commit()
    c = TestClient(app)
    c.post("/api/auth/login", json={"usuario": "sup", "pin": "1111"})
    assert c.patch(f"/api/auth/operadores/{admin.id}", json={"activo": False}).status_code == 403
    assert c.patch(f"/api/auth/operadores/{operadores['op1'].id}", json={"rol": "ADMIN"}).status_code == 403
    assert c.post("/api/auth/operadores", json={**REGISTRO, "rol": "ADMIN"}).status_code == 403
    assert c.patch(f"/api/auth/operadores/{operadores['sup'].id}", json={"activo": False}).status_code == 400


def test_duplicados_y_correo_ambiguo_no_entregan_otra_cuenta(db, operadores):
    c = TestClient(app)
    assert c.post("/api/auth/registro", json=REGISTRO).status_code == 201
    assert c.post("/api/auth/registro", json={**REGISTRO, "usuario": "otro"}).status_code == 409
    assert c.post("/api/auth/registro", json={**REGISTRO, "email": "otro@itsanet.com"}).status_code == 409
    # Una base migrada puede traer correos repetidos: no se modifica ni se
    # elige el primero. Los alias siguen siendo utilizables.
    op = db.scalar(select(Operador).where(Operador.usuario == "nuevo"))
    op.activo = True
    db.add(Operador(usuario="duplicado", nombre="Otro", email=REGISTRO["email"],
                    pin_hash=hash_pin(REGISTRO["pin"]), rol=Rol.OPERADOR))
    db.commit()
    assert c.post("/api/auth/login", json={"usuario": REGISTRO["email"], "pin": REGISTRO["pin"]}).status_code == 409
    assert c.post("/api/auth/login", json={"usuario": "nuevo", "pin": REGISTRO["pin"]}).status_code == 200


def test_actualizar_alias_y_nombre_conserva_identidad_y_password(db, operadores):
    c = TestClient(app)
    c.post("/api/auth/login", json={"usuario": "sup", "pin": "1111"})
    op = operadores["op1"]
    anterior = op.pin_hash
    r = c.patch(f"/api/auth/operadores/{op.id}", json={"usuario": "operario", "nombre": "Nombre corregido"})
    assert r.status_code == 200, r.text
    db.refresh(op)
    assert op.id == operadores["op1"].id and op.pin_hash == anterior
    assert c.patch(f"/api/auth/operadores/{op.id}", json={"email": "otro@itsanet.com"}).status_code == 422
    assert c.patch(f"/api/auth/operadores/{op.id}", json={"usuario": "sup"}).status_code == 409


def test_alta_supervisor_guarda_email_y_logout_revoca_sesion(db, operadores):
    c = TestClient(app)
    c.post("/api/auth/login", json={"usuario": "sup", "pin": "1111"})
    r = c.post("/api/auth/operadores", json=REGISTRO)
    assert r.status_code == 201, r.text
    assert r.json()["email"] == REGISTRO["email"]
    sesion = c.post("/api/auth/login", json={"usuario": REGISTRO["email"], "pin": REGISTRO["pin"]})
    assert sesion.status_code == 200
    token = sesion.json()["token"]
    assert c.post("/api/auth/logout").status_code == 200
    assert TestClient(app).get("/api/auth/yo", headers={"Authorization": f"Bearer {token}"}).status_code == 401
