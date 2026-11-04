# =============================================================================
# SCRIPT SEGURO PARA CREAR COMMITS PROGRESIVOS Y SUBIR A GITHUB (PowerShell)
# Proyecto: LocalSync_SistemasOperativos_G1 (Grupo G1)
# Integrantes Oficiales:
#   - Valery Michell Herrera Roca
#   - Daniel Felipe Rojas Gonzales
# =============================================================================

$ErrorActionPreference = "Stop"
Write-Host "Preparando repositorio local Git para LocalSync_SistemasOperativos_G1..." -ForegroundColor Cyan

if (-not (Test-Path ".git")) {
    git init -b main
}

git add README.md LICENSE .gitignore requirements.txt config/
git commit -m "chore(init): estructurar proyecto LocalSync G1, configuracion y README actualizado"

git add documentacion/descripcion_proyecto.pdf documentacion/requerimientos.pdf documentacion/levantamiento_informacion/ documentacion/sistemas_operativos.pdf documentacion/tecnologias_herramientas.pdf
git commit -m "docs(proyecto): incorporar formulacion, levantamiento de problematica, requerimientos y relacion con SO"

git add documentacion/arquitectura_inicial.pdf documentacion/modelo_relacional.pdf documentacion/documento_tecnico_completo.pdf documentacion/diagramas/ recursos/imagenes/
git commit -m "docs(arquitectura): agregar diagramas P2P, fuentes Mermaid y documento tecnico consolidado"

git add src/bd/
git commit -m "feat(bd): implementar esquema SQLite3 con restriccion compuesta UNIQUE(id_carpeta, ruta_relativa)"

git add src/__init__.py src/backend/
git commit -m "feat(backend): implementar calculo SHA-256, validacion de rutas, gestor SQLite y endpoints FastAPI"

git add src/frontend/ recursos/systemd/ pruebas/ scripts/ subir_a_github.ps1 subir_a_github.sh
git commit -m "test(calidad): agregar interfaz web Fase 1, unidad systemd y suite de pruebas automatizadas"

Write-Host "`nCommits locales creados correctamente:" -ForegroundColor Green
git log --oneline
