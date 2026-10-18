param([string]$Lanzador = (Join-Path (Split-Path -Parent $PSScriptRoot) 'scripts/publicar_pruebas.ps1'))
# Ejecutar con powershell.exe/pwsh -NoProfile -File. No necesita Pester ni Docker.
# Docker y HTTP son simulados; no crea contenedores, volumenes ni enlaces reales.
$ErrorActionPreference = 'Stop'
$CarpetaPruebas = Join-Path ([IO.Path]::GetTempPath()) ('itsanet-lanzador-'+[guid]::NewGuid().ToString('N'))
$Pasadas = 0
$Falladas = 0
function Afirmar($Condicion, $Mensaje) { if (-not $Condicion) { throw $Mensaje } }
function EsperarError([scriptblock]$Accion, [string]$Patron) {
    $mensaje = ''
    try { & $Accion | Out-Null } catch { $mensaje = $_.Exception.Message }
    Afirmar ($mensaje -like $Patron) ('Falta rechazo esperado: '+$Patron)
}
function Caso([string]$Nombre,[scriptblock]$Prueba) {
    $global:ITSANET_QA_PC = @{Volumen=$false;ConsultaVolumen='ok';Imagen=$true;ConsultaImagen='ok';FalloUp=$false;Salud=$true;Publico=$true;Intentos=0;Llamadas=@();EntornoConfig=@{}}
    $carpeta = Join-Path $CarpetaPruebas ([guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path (Join-Path $carpeta 'scripts') -Force | Out-Null
    Copy-Item $Lanzador (Join-Path $carpeta 'scripts/publicar_pruebas.ps1')
    $s = Join-Path $carpeta 'scripts/publicar_pruebas.ps1'
    $archivo = Join-Path $carpeta '.local/pruebas-publicas/entorno.env'
    $url = Join-Path $carpeta '.local/pruebas-publicas/ultimo-enlace.txt'
    try { & $Prueba; $script:Pasadas++; Write-Output ('OK '+$Nombre) }
    catch { $script:Falladas++; Write-Output ('FALLA '+$Nombre+': '+$_.Exception.Message) }
}
function docker {
    $global:LASTEXITCODE = 0
    $cmd = $args -join ' '
    $q = $global:ITSANET_QA_PC
    $q.Llamadas += ,$cmd
    if ($cmd -like '* config --quiet') {
        foreach ($nombre in @('ITSANET_LOCAL_MYSQL_PASSWORD','ITSANET_LOCAL_ROOT_PASSWORD','ITSANET_LOCAL_SESSION_KEY','ITSANET_LOCAL_ADMIN_PASSWORD','ITSANET_PRUEBAS_SUP_PASSWORD','ITSANET_PRUEBAS_OP_PASSWORD')) {
            $q.EntornoConfig[$nombre]=[Environment]::GetEnvironmentVariable($nombre,'Process')
        }
    }
    if ($cmd -eq 'info --format {{.OSType}}') { return 'linux' }
    # Reproduce la detencion de Windows PowerShell 5.1 ante la consulta anterior.
    if ($cmd -like 'volume inspect *') { throw 'NativeCommandError: no such volume' }
    if ($cmd -like 'image inspect *') { throw 'NativeCommandError: no such image' }
    if ($cmd -like 'volume ls *') {
        Afirmar ($cmd -eq 'volume ls --quiet --filter name=^iv-itsanet-pruebas-publicas-pc_mysql_pruebas$') 'Filtro de volumen no exacto.'
        if ($q.ConsultaVolumen -eq 'stderr') { throw 'NativeCommandError: daemon unavailable' }
        if ($q.ConsultaVolumen -eq 'fallo') { $global:LASTEXITCODE=27; return }
        if ($q.Volumen) { return 'iv-itsanet-pruebas-publicas-pc_mysql_pruebas' }
        return
    }
    if ($cmd -like 'image ls *') {
        if ($q.ConsultaImagen -eq 'fallo') { $global:LASTEXITCODE=28; return }
        if ($q.Imagen) { return 'sha256:imagen-sintetica' }
        return
    }
    if ($cmd -like '* up *mysql app' -and $q.FalloUp) { $global:LASTEXITCODE=29; return }
    if ($cmd -like '* logs --since *') { return 'enlace-https | https://ejemplo-sintetico.trycloudflare.com' }
}
function Invoke-RestMethod {
    param($Uri,$TimeoutSec)
    $q=$global:ITSANET_QA_PC
    if ($Uri -like 'http://127.0.0.1:*/health') { return @{ok=$q.Salud} }
    if ($Uri -like 'http://127.0.0.1:*/api/auth/entorno') { return @{pruebasPublicas=$true} }
    if ($Uri -eq 'https://ejemplo-sintetico.trycloudflare.com/api/auth/entorno') {
        $q.Intentos++
        return @{pruebasPublicas=($q.Publico -and $q.Intentos -ge 2)}
    }
    throw 'Destino HTTP inesperado.'
}
function Start-Sleep { param($Seconds) }
try {
    Caso 'Primera ejecucion: volumen inexistente permite preparar y genera claves privadas' {
        & $s -Accion preparar -Puerto 19109 6>&1 | Out-Null
        Afirmar (Test-Path $archivo) 'No preparo su archivo privado.'
        $claves = @([IO.File]::ReadAllLines($archivo) | Where-Object { $_ -notlike 'ITSANET_LOCAL_PORT=*' } | ForEach-Object { $_.Substring($_.IndexOf('=')+1) })
        Afirmar ($claves.Count -eq 6 -and @($claves | Select-Object -Unique).Count -eq 6) 'Claves incompletas o repetidas.'
        Afirmar (@($claves | Where-Object { $_.Length -lt 16 }).Count -eq 0) 'Clave inicial demasiado corta.'
        Afirmar (-not (Test-Path $url)) 'Preparar no debe abrir un enlace.'
    }
    Caso 'Volumen existente sin claves: detiene antes de generar o reemplazar datos' {
        $global:ITSANET_QA_PC.Volumen=$true
        EsperarError { & $s -Accion preparar -Puerto 19109 } '*Existen datos*'
        Afirmar (-not (Test-Path $archivo)) 'Genero claves sobre un volumen existente.'
    }
    Caso 'Fallo de listado Docker: conserva la proteccion de datos' {
        $global:ITSANET_QA_PC.ConsultaVolumen='fallo'
        EsperarError { & $s -Accion preparar -Puerto 19109 } '*No se pudieron consultar los volumenes*'
        Afirmar (-not (Test-Path $archivo)) 'Confundio un error del daemon con volumen ausente.'
    }
    Caso 'Error nativo PowerShell: detiene sin generar claves' {
        $global:ITSANET_QA_PC.ConsultaVolumen='stderr'
        EsperarError { & $s -Accion preparar -Puerto 19109 } '*No se pudieron consultar los volumenes*'
        Afirmar (-not (Test-Path $archivo)) 'Genero claves tras un error nativo.'
    }
    Caso 'Repetir conserva claves y restaura variables ajenas de la consola' {
        & $s -Accion preparar -Puerto 19109 6>&1 | Out-Null
        $hash=(Get-FileHash $archivo -Algorithm SHA256).Hash
        $anteriorClave=[Environment]::GetEnvironmentVariable('ITSANET_LOCAL_MYSQL_PASSWORD','Process')
        $anteriorPuerto=[Environment]::GetEnvironmentVariable('ITSANET_LOCAL_PORT','Process')
        try {
            $env:ITSANET_LOCAL_MYSQL_PASSWORD='variable-ajena-para-la-prueba';$env:ITSANET_LOCAL_PORT='19999'
            $global:ITSANET_QA_PC.Volumen=$true
            & $s -Accion preparar 6>&1 | Out-Null
            Afirmar ((Get-FileHash $archivo -Algorithm SHA256).Hash -eq $hash) 'Cambio claves o puerto.'
            Afirmar ($env:ITSANET_LOCAL_MYSQL_PASSWORD -eq 'variable-ajena-para-la-prueba' -and $env:ITSANET_LOCAL_PORT -eq '19999') 'No restauro variables.'
        } finally {
            [Environment]::SetEnvironmentVariable('ITSANET_LOCAL_MYSQL_PASSWORD',$anteriorClave,'Process')
            [Environment]::SetEnvironmentVariable('ITSANET_LOCAL_PORT',$anteriorPuerto,'Process')
        }
    }
    Caso 'Reanudar con archivo privado existente conserva todos los caracteres de las claves' {
        New-Item -ItemType Directory -Path (Split-Path -Parent $archivo) -Force | Out-Null
        $nombres=@('ITSANET_LOCAL_MYSQL_PASSWORD','ITSANET_LOCAL_ROOT_PASSWORD','ITSANET_LOCAL_SESSION_KEY','ITSANET_LOCAL_ADMIN_PASSWORD','ITSANET_PRUEBAS_SUP_PASSWORD','ITSANET_PRUEBAS_OP_PASSWORD')
        $lineas=@($nombres | ForEach-Object { $_+'=prueba-privada-0123456789==valor' })+@('ITSANET_LOCAL_PORT=19109')
        [IO.File]::WriteAllLines($archivo,[string[]]$lineas,[Text.UTF8Encoding]::new($false))
        $hash=(Get-FileHash $archivo -Algorithm SHA256).Hash
        $global:ITSANET_QA_PC.Volumen=$true
        & $s -Accion preparar 6>&1 | Out-Null
        foreach ($nombre in $nombres) { Afirmar ($global:ITSANET_QA_PC.EntornoConfig[$nombre] -ceq 'prueba-privada-0123456789==valor') 'Se modifico el valor leido del archivo privado.' }
        Afirmar ((Get-FileHash $archivo -Algorithm SHA256).Hash -eq $hash) 'Reescribio las claves al reanudar.'
        Afirmar (@($global:ITSANET_QA_PC.Llamadas | Where-Object { $_ -like 'volume *' }).Count -eq 0) 'Intento generar un entorno nuevo al reanudar.'
    }
    Caso 'Archivo privado incompleto se rechaza sin cambiarlo ni arrancar Docker' {
        New-Item -ItemType Directory -Path (Split-Path -Parent $archivo) -Force | Out-Null
        [IO.File]::WriteAllLines($archivo,[string[]]@('ITSANET_LOCAL_MYSQL_PASSWORD=prueba-existente-0123456789'),[Text.UTF8Encoding]::new($false))
        $hash=(Get-FileHash $archivo -Algorithm SHA256).Hash
        EsperarError { & $s -Accion preparar -Puerto 19109 } '*Archivo privado incompleto*'
        Afirmar ((Get-FileHash $archivo -Algorithm SHA256).Hash -eq $hash) 'Regenero un archivo incompleto.'
        Afirmar (@($global:ITSANET_QA_PC.Llamadas | Where-Object { $_ -like '* up *' }).Count -eq 0) 'Arranco con claves incompletas.'
    }
    Caso 'SinConstruir sin imagen: mensaje claro y ningun arranque' {
        $global:ITSANET_QA_PC.Imagen=$false
        EsperarError { & $s -Accion preparar -Puerto 19109 -SinConstruir } '*No hay imagen preparada*'
        Afirmar (@($global:ITSANET_QA_PC.Llamadas | Where-Object { $_ -like '* up *' }).Count -eq 0) 'Arranco sin imagen.'
    }
    Caso 'SinConstruir con imagen: prepara usando la imagen comprobada' {
        & $s -Accion preparar -Puerto 19109 -SinConstruir 6>&1 | Out-Null
        Afirmar (@($global:ITSANET_QA_PC.Llamadas | Where-Object { $_ -like '* up *--no-build*mysql app' }).Count -eq 1) 'No uso la imagen existente.'
    }
    Caso 'Fallo de consulta de imagen: no lo confunde con imagen ausente' {
        $global:ITSANET_QA_PC.ConsultaImagen='fallo'
        EsperarError { & $s -Accion preparar -Puerto 19109 -SinConstruir } '*No se pudieron consultar las imagenes*'
    }
    Caso 'Fallo de arranque Docker: mantiene claves y no anuncia un enlace' {
        $global:ITSANET_QA_PC.FalloUp=$true
        EsperarError { & $s -Puerto 19109 } '*Docker no completo la accion*29*'
        Afirmar ((Test-Path $archivo) -and -not (Test-Path $url)) 'No conservo estado privado tras el fallo.'
    }
    Caso 'Salud no confirmada: impide publicar el tunel' {
        $global:ITSANET_QA_PC.Salud=$false
        EsperarError { & $s -Puerto 19109 } '*La app no confirma*'
        Afirmar (@($global:ITSANET_QA_PC.Llamadas | Where-Object { $_ -like '* up --detach enlace-https' }).Count -eq 0) 'Abrio tunel sin salud.'
    }
    Caso 'Publicacion: espera confirmacion externa antes de entregar el enlace' {
        $salida=(& $s -Puerto 19109 6>&1 | Out-String)
        Afirmar ($global:ITSANET_QA_PC.Intentos -eq 2 -and (Test-Path $url)) 'No espero la confirmacion externa.'
        Afirmar ($salida -like '*PRUEBAS HTTPS:*') 'No entrego el enlace confirmado.'
    }
    Caso 'Proveedor sin confirmar: falla sin anunciar ni guardar un enlace' {
        $global:ITSANET_QA_PC.Publico=$false
        EsperarError { & $s -Puerto 19109 } '*no se confirmo un enlace publico*'
        Afirmar ($global:ITSANET_QA_PC.Intentos -eq 25 -and -not (Test-Path $url)) 'Conservo un enlace no confirmado.'
    }
} finally {
    Remove-Item $CarpetaPruebas -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Variable ITSANET_QA_PC -Scope Global -ErrorAction SilentlyContinue
}
Write-Output ("$Pasadas pasadas, $Falladas falladas")
if ($Falladas -gt 0) { exit 1 }
