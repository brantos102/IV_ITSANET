param([switch]$SinRed)
# PowerShell de Windows. Solo consulta el proyecto del piloto; no reinicia nada.
$ErrorActionPreference = 'Stop'
$Proyecto = 'iv-itsanet-pruebas-publicas-pc'
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Abre Docker Desktop y ejecuta esto desde PowerShell de Windows.' }
$Contenedores = @(& docker ps --filter ('label=com.docker.compose.project='+$Proyecto) --filter 'label=com.docker.compose.service=app' --format '{{.Names}}')
if ($LASTEXITCODE -ne 0) { throw 'Docker no pudo consultar el piloto. No se cambio ningun servicio.' }
if ($Contenedores.Count -ne 1) { throw 'No se encontro una unica app del piloto encendida. Ejecuta publicar_pruebas.ps1 -Accion estado.' }
$Contenedor = $Contenedores[0].Trim()
Write-Output 'DIAGNOSTICO SOLO PRUEBAS: no muestra claves ni envia correos.'
if ($SinRed) {
    & docker exec $Contenedor python scripts/diagnosticar_google_pruebas.py --sin-red
} else {
    & docker exec $Contenedor python scripts/diagnosticar_google_pruebas.py
}
if ($LASTEXITCODE -ne 0) { throw 'El diagnostico no se completo. Conserva la configuracion y los volumenes.' }
$Raiz = Split-Path -Parent $PSScriptRoot
$ArchivoUrl = Join-Path $Raiz '.local/pruebas-publicas/ultimo-enlace.txt'
if (Test-Path $ArchivoUrl) {
    $Url = [IO.File]::ReadAllText($ArchivoUrl).Trim()
    if ($Url -match '^https://([a-z0-9-]+\.trycloudflare\.com)(?:/app)?/?$') {
        $Origen = 'https://'+$Matches[1]
        try {
            $r = Invoke-RestMethod -Uri ($Origen+'/api/auth/entorno') -TimeoutSec 10
            Write-Output ('ENLACE PUBLICO: '+$(if ($r.pruebasPublicas -eq $true) { 'PRUEBAS confirmadas' } else { 'No confirma PRUEBAS; revisa el enlace vigente' }))
        } catch { Write-Output 'ENLACE PUBLICO: sin respuesta valida en 10 segundos. El estado del contenedor aparece arriba.' }
    }
}
