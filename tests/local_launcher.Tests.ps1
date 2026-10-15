# Contrato del lanzador: simula Docker; no inicia contenedores ni usa bases reales.
$ErrorActionPreference = 'Stop'
$temporal = Join-Path ([IO.Path]::GetTempPath()) ('itsanet-ps-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path (Join-Path $temporal 'scripts') -Force | Out-Null
$origen = Join-Path (Split-Path -Parent $PSScriptRoot) 'scripts/local.ps1'
$scriptLocal = Join-Path $temporal 'scripts/local.ps1'
Copy-Item $origen $scriptLocal
$global:fallarDocker = $false
$global:solicitudesSalud = 0
$global:ordenes = [System.Collections.Generic.List[string]]::new()
function global:docker {
    $global:LASTEXITCODE = 0
    $global:ordenes.Add(($args -join ' '))
    if ($args[0] -eq 'info') { return 'linux' }
    if ($args -contains 'up' -and $global:fallarDocker) { $global:LASTEXITCODE = 1 }
}
function global:Invoke-RestMethod {
    param($Uri, $TimeoutSec)
    if ($Uri -ne 'http://127.0.0.1:3013/health') { throw 'Puerto incorrecto' }
    $global:solicitudesSalud++
    return @{ok = $true}
}
try {
    & $scriptLocal -Puerto 3013 *> $null
    $archivo = Join-Path $temporal '.local/entorno.env'
    $antes = [IO.File]::ReadAllText($archivo)
    if ((Get-Content $archivo).Count -ne 4) { throw 'No se generaron las cuatro claves' }
    if ($antes -notmatch 'ITSANET_LOCAL_ADMIN_PASSWORD=[a-f0-9]{48}') { throw 'Clave aleatoria incorrecta' }
    & $scriptLocal -Puerto 3013 *> $null
    if ($antes -ne [IO.File]::ReadAllText($archivo)) { throw 'Se regeneraron claves existentes' }
    if ($global:solicitudesSalud -ne 2) { throw 'No se comprobo salud tras el arranque' }
    & $scriptLocal -Accion detener *> $null
    if (-not ($global:ordenes | Where-Object { $_ -match ' stop$' })) { throw 'No detuvo el proyecto' }
    if ($global:ordenes | Where-Object { $_ -match 'down|--volumes' }) { throw 'Orden destructiva inesperada' }
    if (-not ($global:ordenes | Where-Object { $_ -match '--project-name iv-itsanet-desarrollo' })) { throw 'Falta aislamiento del proyecto' }
    $global:fallarDocker = $true
    $rechazo = $false
    try { & $scriptLocal -Puerto 3013 *> $null } catch { $rechazo = $true }
    if (-not $rechazo -or $global:solicitudesSalud -ne 2) { throw 'Se ignoro el fallo de Docker' }
    Write-Host 'OK: arranque, puerto, aislamiento, salud, claves persistentes, stop y fallo Docker.'
} finally {
    Remove-Item Function:\docker -ErrorAction SilentlyContinue
    Remove-Item Function:\Invoke-RestMethod -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $temporal -Recurse -Force
}
