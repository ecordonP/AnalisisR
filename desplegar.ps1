$ErrorActionPreference = 'Stop'
$package = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot 'dist\AnalisisR')).Path
$manifest = Get-Content -LiteralPath (Join-Path $package 'build-info.json') -Raw | ConvertFrom-Json
if ($manifest.application -ne 'AnalisisR' -or $manifest.format -ne 'onedir') { throw 'El paquete no es de AnalisisR.' }
$validation = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'build\validation.json') -Raw | ConvertFrom-Json
foreach ($name in @('AnalisisR.exe', 'AnalisisRWorker.exe')) {
    $hash = (Get-FileHash -LiteralPath (Join-Path $package $name) -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($hash -ne $manifest.executables.$name) { throw "El ejecutable $name no coincide con la compilación." }
    if ($hash -ne $validation.executables.$name) { throw 'Este paquete no ha pasado la validación.' }
}
$destination = 'C:\AnalisisR'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss_fff'
$staging = "C:\AnalisisR_nuevo_$stamp"
$backup = "C:\AnalisisR_respaldo_$stamp"
if ((Test-Path -LiteralPath $staging) -or (Test-Path -LiteralPath $backup)) { throw 'Ya existe una carpeta de preparación o respaldo con este nombre.' }
foreach ($target in @($destination, $staging, $backup)) {
    if ([IO.Path]::GetFullPath($target) -ne $target -or [IO.Path]::GetDirectoryName($target) -ne 'C:\') {
        throw "Destino no permitido: $target"
    }
    if ((Test-Path -LiteralPath $target) -and ((Get-Item -LiteralPath $target -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw "El destino no puede ser un enlace: $target"
    }
}
if (Get-Process -Name AnalisisR,AnalisisRWorker -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -and $_.Path.StartsWith($destination + '\', [StringComparison]::OrdinalIgnoreCase) }) {
    throw 'Cierra AnalisisR antes de actualizar C:\AnalisisR.'
}
$hasInstallation = (Test-Path -LiteralPath $destination) -and @(
    Get-ChildItem -LiteralPath $destination -Force | Select-Object -First 1).Count -gt 0
if ($hasInstallation) {
    $previous = Join-Path $destination 'build-info.json'
    if (-not (Test-Path -LiteralPath $previous) -or (Get-Content -LiteralPath $previous -Raw | ConvertFrom-Json).application -ne 'AnalisisR') {
        throw 'C:\AnalisisR ya existe y no se reconoce como una instalación de esta aplicación.'
    }
}
$copyDestination = if ($hasInstallation) { $staging } else { $destination }
try {
    & robocopy $package $copyDestination /E /COPY:DAT /DCOPY:DAT /MT:16 /R:1 /W:1 /NFL /NDL /NP /NJH /NJS
    if ($LASTEXITCODE -ge 8 -or -not (Test-Path -LiteralPath (Join-Path $copyDestination 'AnalisisR.exe')) -or
            -not (Test-Path -LiteralPath (Join-Path $copyDestination '_internal'))) {
        throw 'Falló la copia del paquete. Comprueba el permiso de escritura en C:\AnalisisR; no se sustituye una instalación anterior.'
    }
    foreach ($name in @('AnalisisR.exe', 'AnalisisRWorker.exe')) {
        if ((Get-FileHash -LiteralPath (Join-Path $copyDestination $name) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $manifest.executables.$name) {
            throw 'La copia de despliegue no coincide con la compilación.'
        }
    }
    & python (Join-Path $PSScriptRoot 'tools\validar_paquete.py') $copyDestination
    if ($LASTEXITCODE -ne 0) { throw 'Falló la validación de la copia instalada.' }
    if ($hasInstallation) {
        Move-Item -LiteralPath $destination -Destination $backup
        try { Move-Item -LiteralPath $staging -Destination $destination }
        catch {
            if (Test-Path -LiteralPath $backup) { Move-Item -LiteralPath $backup -Destination $destination }
            throw
        }
    }
    Write-Output "Instalado en $destination\AnalisisR.exe"
    $global:LASTEXITCODE = 0
} finally {
    if (Test-Path -LiteralPath $staging) { Remove-Item -LiteralPath $staging -Recurse -Force }
}
