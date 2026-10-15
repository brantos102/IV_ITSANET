param(
    [ValidateSet('iniciar', 'estado', 'detener', 'logs', 'acceso')]
    [string]$Accion = 'iniciar',
    [ValidateRange(1024, 65535)][int]$Puerto = 3003
)
$ErrorActionPreference = 'Stop'
$Raiz = Split-Path -Parent $PSScriptRoot
$CarpetaLocal = Join-Path $Raiz '.local'
$ArchivoEntorno = Join-Path $CarpetaLocal 'entorno.env'

function NuevaClave {
    $bytes = New-Object byte[] 24
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    return ([BitConverter]::ToString($bytes)).Replace('-', '').ToLowerInvariant()
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw 'Falta Docker Desktop. En PowerShell: winget install --exact --id Docker.DockerDesktop . Abre Docker Desktop, usa contenedores Linux y vuelve a ejecutar este script.'
}
try { & docker compose version | Out-Null }
catch { throw 'Falta Docker Compose v2. Actualiza Docker Desktop.' }
if ($LASTEXITCODE -ne 0) { throw 'Falta Docker Compose v2. Actualiza Docker Desktop.' }
try { $tipoDocker = & docker info --format '{{.OSType}}' 2>$null }
catch { throw 'Docker no esta iniciado. Abre Docker Desktop y espera Engine running.' }
if ($LASTEXITCODE -ne 0) { throw 'Docker no esta iniciado. Abre Docker Desktop y espera a que indique Engine running.' }
if ($tipoDocker -ne 'linux') { throw 'Docker Desktop debe usar Linux containers para este proyecto.' }

if (-not (Test-Path $ArchivoEntorno)) {
    if ($Accion -ne 'iniciar') { throw 'El entorno local aun no existe. Ejecuta primero -Accion iniciar.' }
    New-Item -ItemType Directory -Path $CarpetaLocal -Force | Out-Null
    $lineas = @(
        "ITSANET_LOCAL_MYSQL_PASSWORD=$(NuevaClave)",
        "ITSANET_LOCAL_ROOT_PASSWORD=$(NuevaClave)",
        "ITSANET_LOCAL_SESSION_KEY=$(NuevaClave)",
        "ITSANET_LOCAL_ADMIN_PASSWORD=$(NuevaClave)"
    )
    # No se regenera al reiniciar: MySQL y el administrador conservan su clave.
    [IO.File]::WriteAllLines($ArchivoEntorno, $lineas, [Text.UTF8Encoding]::new($false))
}
$env:ITSANET_LOCAL_PORT = "$Puerto"
$opciones = @('compose', '--project-name', 'iv-itsanet-desarrollo', '--project-directory', $Raiz,
              '--env-file', $ArchivoEntorno, '-f', (Join-Path $Raiz 'compose.local.yaml'))
switch ($Accion) {
    'iniciar' {
        & docker @opciones up --detach --build --wait --wait-timeout 240
        if ($LASTEXITCODE -ne 0) { throw 'El arranque no termino. Ejecuta este script con -Accion logs; conserva .local y los volumenes.' }
        $salud = Invoke-RestMethod -Uri "http://127.0.0.1:$Puerto/health" -TimeoutSec 5
        if ($salud.ok -ne $true) { throw 'La aplicacion no confirma su estado de salud.' }
        Write-Host "ITSANET de pruebas responde en el puerto $Puerto. Abre en el navegador localhost:$Puerto/app/."
        Write-Host 'Usuario: admin. Consulta la clave inicial con: .\scripts\local.ps1 -Accion acceso'
    }
    'estado' { & docker @opciones ps }
    'detener' { & docker @opciones stop }
    'logs' { & docker @opciones logs --tail 80 app mysql }
    'acceso' {
        $clave = Get-Content $ArchivoEntorno | Where-Object { $_.StartsWith('ITSANET_LOCAL_ADMIN_PASSWORD=') }
        Write-Host 'Usuario: admin (solo desarrollo local)'
        Write-Host ('Clave inicial: ' + $clave.Substring($clave.IndexOf('=') + 1))
        Write-Host 'Si la cambiaste desde la app, utiliza la clave nueva. No compartas este archivo.'
    }
}
if ($LASTEXITCODE -ne 0) { throw "Docker termino con codigo $LASTEXITCODE" }
