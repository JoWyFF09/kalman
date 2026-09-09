# Ejecuta la batería de pruebas.
#
# En esta máquina Python viene de Microsoft Store y corre en un contenedor que
# virtualiza AppData\Roaming, de modo que no ve los ficheros del proyecto. La
# solución es espejar el proyecto en una ruta no redirigida y ejecutar allí.
#
# En cualquier máquina con Python instalado desde python.org basta con:
#     python -m pytest

$ErrorActionPreference = "Stop"
$source = Split-Path -Parent $PSScriptRoot
$build = Join-Path $env:TEMP "kalman-build"

if (Test-Path $build) { Remove-Item $build -Recurse -Force }
New-Item -ItemType Directory -Force -Path $build | Out-Null

foreach ($item in @("kalman", "tests", "scripts", "pyproject.toml")) {
    $path = Join-Path $source $item
    if (Test-Path $path) { Copy-Item $path -Destination $build -Recurse -Force }
}

Push-Location $build
try {
    python -m pytest tests -q
} finally {
    Pop-Location
}
