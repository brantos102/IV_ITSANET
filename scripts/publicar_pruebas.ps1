param(
    [ValidateSet('iniciar','preparar','estado','detener','logs','acceso')]
    [string]$Accion = 'iniciar',
    [ValidateRange(0,65535)][int]$Puerto = 0,
    [switch]$SinConstruir
)
# Ejecutar en PowerShell de la PC, no dentro de la terminal SSH del servidor.
$ErrorActionPreference = 'Stop'
$Raiz = Split-Path -Parent $PSScriptRoot
$Proyecto = 'iv-itsanet-pruebas-publicas-pc'
$Privado = Join-Path $Raiz '.local/pruebas-publicas'
$ArchivoEntorno = Join-Path $Privado 'entorno.env'
$ArchivoAccesos = Join-Path $Privado 'accesos-iniciales.txt'
$ArchivoUrl = Join-Path $Privado 'ultimo-enlace.txt'
$Variables = @('ITSANET_LOCAL_MYSQL_PASSWORD','ITSANET_LOCAL_ROOT_PASSWORD','ITSANET_LOCAL_SESSION_KEY',
              'ITSANET_LOCAL_ADMIN_PASSWORD','ITSANET_PRUEBAS_SUP_PASSWORD','ITSANET_PRUEBAS_OP_PASSWORD')

function NuevaClavePruebas {
    $bytes = New-Object byte[] 24
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    return ([BitConverter]::ToString($bytes)).Replace('-','').ToLowerInvariant()
}
function EscribirPrivado($Ruta,$Lineas) {
    [IO.File]::WriteAllLines($Ruta,[string[]]$Lineas,[Text.UTF8Encoding]::new($false))
    if ($env:OS -ne 'Windows_NT') { & chmod 600 $Ruta; if ($LASTEXITCODE -ne 0) { throw 'No se pudo restringir el archivo privado.' } }
}
function PuertoLibre([int]$Numero) {
    $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback,$Numero)
    try { $listener.Start(); return $true } catch { return $false } finally { $listener.Stop() }
}
function DockerPruebas {
    & docker @opciones @args
    if ($LASTEXITCODE -ne 0) { throw "Docker no completo la accion. Conserva .local y los volumenes de pruebas. Codigo: $LASTEXITCODE" }
}
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    $binario = Join-Path $env:ProgramFiles 'Docker/Docker/resources/bin/docker.exe'
    if (Test-Path $binario) { $env:Path = (Split-Path -Parent $binario) + ';' + $env:Path }
}
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Abre Docker Desktop con contenedores Linux. Este lanzador se ejecuta en la PC Windows.' }
& docker compose version | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Se necesita Docker Compose v2.' }
$tipo = & docker info --format '{{.OSType}}' 2>$null
if ($LASTEXITCODE -ne 0 -or $tipo -ne 'linux') { throw 'Espera a que Docker Desktop indique Engine running y Linux containers.' }
if (-not (Test-Path $ArchivoEntorno)) {
    if ($Accion -notin @('iniciar','preparar')) { throw 'Primero ejecuta -Accion preparar o iniciar.' }
    # Nunca regenerar contraseñas si ya existe un volumen de esta instancia.
    & docker volume inspect ($Proyecto+'_mysql_pruebas') *> $null
    if ($LASTEXITCODE -eq 0) { throw 'Existen datos de estas pruebas pero falta su archivo privado. Recuperalo antes de continuar; no se regeneraron claves.' }
    New-Item -ItemType Directory -Path $Privado -Force | Out-Null
    if ($env:OS -eq 'Windows_NT') {
        $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
        & icacls $Privado '/inheritance:r' '/grant:r' ('*'+$sid+':(OI)(CI)F') '/grant:r' '*S-1-5-18:(OI)(CI)F' | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'No se pudieron restringir los permisos de la carpeta privada.' }
    } else {
        & chmod 700 $Privado
        if ($LASTEXITCODE -ne 0) { throw 'No se pudo restringir la carpeta privada.' }
    }
    $valores = @{}
    foreach ($nombre in $Variables) { $valores[$nombre] = NuevaClavePruebas }
    EscribirPrivado $ArchivoEntorno @($Variables | ForEach-Object { $_+'='+$valores[$_] })
    EscribirPrivado $ArchivoAccesos @('SOLO PRUEBAS. Comparte individualmente por un canal privado. Cambia la clave desde Mi cuenta.',
        ('admin : '+$valores['ITSANET_LOCAL_ADMIN_PASSWORD']),
        ('supervisor.prueba : '+$valores['ITSANET_PRUEBAS_SUP_PASSWORD']),
        ('operario.prueba : '+$valores['ITSANET_PRUEBAS_OP_PASSWORD']))
}
$valores = @{}
foreach ($linea in [IO.File]::ReadAllLines($ArchivoEntorno)) {
    if ($linea.Contains('=')) { $par = $linea.Split(@('='),2); $valores[$par[0]] = $par[1] }
}
foreach ($nombre in $Variables) {
    if (-not $valores[$nombre] -or $valores[$nombre].Length -lt 16) { throw 'Archivo privado incompleto. No borres ni regeneres claves con datos existentes.' }
}
if ($Puerto -ne 0 -and $Puerto -lt 1024) { throw 'El puerto local debe ser 1024 o superior.' }
if ($Puerto -eq 0) {
    if ($valores['ITSANET_LOCAL_PORT']) { $Puerto = [int]$valores['ITSANET_LOCAL_PORT'] }
    elseif (PuertoLibre 3003) { $Puerto = 3003 }
    elseif (PuertoLibre 3005) { $Puerto = 3005; Write-Host '3003 ya esta ocupado. Se conserva y se usa 3005 para estas pruebas aisladas.' }
    else { throw '3003 y 3005 estan ocupados. Elige otro puerto libre con -Puerto; no se detuvo ningun servicio.' }
}
# Compose da prioridad al entorno del proceso sobre --env-file. Usamos solo
# las claves de este piloto y restauramos las variables de la consola al salir.
$Anteriores = @{}
foreach ($nombre in ($Variables + @('ITSANET_LOCAL_PORT'))) {
    $Anteriores[$nombre] = [Environment]::GetEnvironmentVariable($nombre,'Process')
}
try {
    foreach ($nombre in $Variables) { [Environment]::SetEnvironmentVariable($nombre,$valores[$nombre],'Process') }
    $env:ITSANET_LOCAL_PORT = [string]$Puerto
    $opciones = @('compose','--project-name',$Proyecto,'--project-directory',$Raiz,'--env-file',$ArchivoEntorno,
                  '-f',(Join-Path $Raiz 'compose.local.yaml'),'-f',(Join-Path $Raiz 'compose.pruebas-publicas.yaml'))
    DockerPruebas config --quiet
    if ($Accion -eq 'acceso') {
        Write-Host "Las cuentas iniciales estan en: $ArchivoAccesos"
        Write-Host 'Abre el archivo localmente. Comparte solo una cuenta de prueba por persona; no lo publiques ni lo pegues en GitHub.'
        return
    }
    if ($Accion -eq 'estado') { DockerPruebas ps; if (Test-Path $ArchivoUrl) { Write-Host ('Ultimo enlace: '+[IO.File]::ReadAllText($ArchivoUrl).Trim()) }; return }
    if ($Accion -eq 'logs') { DockerPruebas logs --tail 60 enlace-https app; return }
    if ($Accion -eq 'detener') { DockerPruebas stop enlace-https; Write-Host 'Enlace publico detenido. Datos de pruebas y servidor empresarial conservados.'; return }
    $propia = DockerPruebas ps --quiet app
    if (-not $propia -and -not (PuertoLibre $Puerto)) { throw "El puerto $Puerto esta ocupado. Usa -Puerto con otro puerto libre; no se modifico el servicio existente." }
    $lineas = @($Variables | ForEach-Object { $_+'='+$valores[$_] }) + @('ITSANET_LOCAL_PORT='+$Puerto)
    EscribirPrivado $ArchivoEntorno $lineas
    if ($SinConstruir) {
        & docker image inspect ($Proyecto+'-app') *> $null
        if ($LASTEXITCODE -ne 0) { throw 'No hay imagen preparada para este proyecto. Ejecuta sin -SinConstruir.' }
        DockerPruebas up --detach --no-build --wait --wait-timeout 300 mysql app
    } else { DockerPruebas up --detach --build --wait --wait-timeout 300 mysql app }
    $salud = Invoke-RestMethod -Uri "http://127.0.0.1:$Puerto/health" -TimeoutSec 5
    $entorno = Invoke-RestMethod -Uri "http://127.0.0.1:$Puerto/api/auth/entorno" -TimeoutSec 5
    if ($salud.ok -ne $true -or $entorno.pruebasPublicas -ne $true) { throw 'La app no confirma que sea la instancia de pruebas. No se abrio el enlace.' }
    Write-Host "Instancia aislada comprobada. Puerto local $Puerto. Claves privadas: $ArchivoAccesos"
    if ($Accion -eq 'preparar') { Write-Host 'Todavia no se abrio un enlace publico.'; return }
    $inicio = [DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')
    if (DockerPruebas ps --quiet enlace-https) { DockerPruebas restart enlace-https }
    else { DockerPruebas up --detach enlace-https }
    for ($intento=0; $intento -lt 25; $intento++) {
        $registro = (DockerPruebas logs --since $inicio --no-color --tail 150 enlace-https) -join "`n"
        $coincidencias = [regex]::Matches($registro,'https://[a-z0-9-]+\.trycloudflare\.com')
        if ($coincidencias.Count -gt 0) {
            $url = $coincidencias[$coincidencias.Count-1].Value
            try {
                $publico = Invoke-RestMethod -Uri ($url+'/api/auth/entorno') -TimeoutSec 5
                if ($publico.pruebasPublicas -eq $true) {
                    EscribirPrivado $ArchivoUrl @($url+'/app/')
                    Write-Host ('PRUEBAS HTTPS: '+$url+'/app/')
                    Write-Host 'Comparte esa URL y una cuenta individual. La PC y Docker deben permanecer encendidos. Los supervisores no necesitan VPN.'
                    Write-Host 'No se habilito facturacion ni se modifico Firebase o el servidor empresarial.'
                    return
                }
            } catch { }
        }
        Start-Sleep -Seconds 2
    }
    throw 'La instancia local funciona, pero no se confirmo un enlace publico. Usa -Accion logs; revisa salida HTTPS y TCP 7844 de la PC/VPN. No se anuncio una URL como lista.'
} finally {
    foreach ($nombre in $Anteriores.Keys) { [Environment]::SetEnvironmentVariable($nombre,$Anteriores[$nombre],'Process') }
}
