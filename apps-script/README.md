# ITSANET IMS — app actual en Apps Script

Revisión de la app en producción y parche de los defectos que rompen el ciclo
principal.

| Archivo | Qué es |
|---|---|
| [`ANALISIS.md`](ANALISIS.md) | Revisión contra los nueve requerimientos iniciales, hallazgos y recomendación |
| [`PARCHE-CRITICO.md`](PARCHE-CRITICO.md) | Corrección de los tres defectos, lista para pegar en el editor |
| [`repro-bugs.js`](repro-bugs.js) | Reproduce los tres defectos sin desplegar nada |

```bash
node apps-script/repro-bugs.js ruta/al/Index.html
```

Sale con código 1 mientras quede alguno; con 0 cuando el parche está aplicado.
