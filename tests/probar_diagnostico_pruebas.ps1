param([string]$Diagnostico = (Join-Path (Split-Path -Parent $PSScriptRoot) 'scripts/diagnosticar_google_pruebas.ps1'))
$ErrorActionPreference='Stop'
$raiz=Join-Path ([IO.Path]::GetTempPath()) ('itsanet-diagnostico-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path (Join-Path $raiz 'scripts') -Force | Out-Null
Copy-Item $Diagnostico (Join-Path $raiz 'scripts/diagnosticar_google_pruebas.ps1')
$s=Join-Path $raiz 'scripts/diagnosticar_google_pruebas.ps1'
$global:QA48=@{Contenedores=1;Llamadas=@();Fallo=$false;Publico=$true}
function docker {
 $global:LASTEXITCODE=0;$q=$global:QA48;$cmd=$args -join ' ';$q.Llamadas+=,$cmd
 if($cmd -like 'ps --filter label=com.docker.compose.project=iv-itsanet-pruebas-publicas-pc --filter label=com.docker.compose.service=app --format *'){
  if($q.Contenedores -eq 0){return};'piloto-app';if($q.Contenedores -gt 1){'otra-app'};return
 }
 if($cmd -like 'exec piloto-app python scripts/diagnosticar_google_pruebas.py*'){
  if($q.Fallo){$global:LASTEXITCODE=3;return};return '{"entorno":"PRUEBAS","conexiones":[]}'
 }
 throw ('Comando Docker no permitido: '+$cmd)
}
function Invoke-RestMethod { param($Uri,$TimeoutSec);if($Uri -ne 'https://prueba-sintetica.trycloudflare.com/api/auth/entorno'){throw 'URL incorrecta'};if(-not $global:QA48.Publico){throw 'Enlace sin respuesta'};return @{pruebasPublicas=$true} }
function assert($x,$m){if(-not $x){throw $m}}
function rechaza($p){$e='';try{& $s -SinRed | Out-Null}catch{$e=$_.Exception.Message};assert ($e -like $p) ('Rechazo faltante: '+$p)}
try{
 $o=@(& $s -SinRed);assert (($global:QA48.Llamadas -join '\n') -like '*diagnosticar_google_pruebas.py --sin-red*') 'No aplico modo sin red';'OK lectura limitada al proyecto y modo sin red'
 $global:QA48.Llamadas=@();& $s | Out-Null;assert ($global:QA48.Llamadas[-1] -eq 'exec piloto-app python scripts/diagnosticar_google_pruebas.py') 'Comando de comprobacion incorrecto';'OK verificacion explicita sin reinicios'
 $global:QA48.Contenedores=0;rechaza '*unica app*';'OK rechaza piloto detenido'
 $global:QA48.Contenedores=2;rechaza '*unica app*';'OK rechaza seleccion ambigua'
 $global:QA48.Contenedores=1;$global:QA48.Fallo=$true;rechaza '*no se completo*';$global:QA48.Fallo=$false;'OK fallo Python conserva configuracion'
 New-Item -ItemType Directory -Path (Join-Path $raiz '.local/pruebas-publicas') -Force | Out-Null
 [IO.File]::WriteAllText((Join-Path $raiz '.local/pruebas-publicas/ultimo-enlace.txt'),'https://prueba-sintetica.trycloudflare.com/app/')
 $o=@(& $s);assert (($o -join '\n') -like '*PRUEBAS confirmadas*') 'No confirma enlace';'OK consulta publica de lectura'
 $global:QA48.Publico=$false;$o=@(& $s);assert (($o -join '\n') -like '*sin respuesta valida*') 'No distingue enlace caido';'OK enlace sin respuesta conserva diagnostico local'
 assert (-not (($global:QA48.Llamadas -join '\n') -match '(up |restart |stop |volume |inspect |down )')) 'Mutacion Docker detectada'
 '7 comprobaciones PowerShell aprobadas; Docker y HTTP simulados.'
}finally{Remove-Item -Recurse -Force $raiz}
