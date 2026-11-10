# Archivos para pruebas end-to-end

Coloque aquí el packing list real (`.xlsx`) para ejecutar las pruebas
end-to-end, o apunte la variable `VAL_TEST_XLSX` a su ubicación:

```bash
VAL_TEST_XLSX=/ruta/al/packing_list.xlsx python -m pytest -q
```

Estos archivos **no se versionan**: llevan datos del cliente.
Sin ellos, las pruebas end-to-end se omiten y el resto corre igual.
