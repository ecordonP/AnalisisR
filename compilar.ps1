param([switch]$Desplegar)
$ErrorActionPreference = 'Stop'
Push-Location -LiteralPath $PSScriptRoot
try {
    & python -m PyInstaller --noconfirm AnalisisR_onedir.spec
    if ($LASTEXITCODE -ne 0) { throw 'Falló la compilación protegida.' }
    & python tools/validar_paquete.py dist/AnalisisR
    if ($LASTEXITCODE -ne 0) { throw 'Falló la validación del paquete; no se despliega.' }
    if ($Desplegar) { & "$PSScriptRoot/desplegar.ps1" }
} finally {
    Pop-Location
}
