"""Regresión documental: enlaces locales, bloques Markdown y fuentes Mermaid.

Unittest para ejecutarse también en CI de Windows/Ubuntu sin dependencias extra.
"""
from __future__ import annotations

from pathlib import Path
import re
import unittest
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
DOCUMENTOS = [
    "README.md",
    "CHANGELOG.md",
    "documentacion/ARQUITECTURA.md",
    "documentacion/PROTOCOLO_TCP.md",
    "documentacion/API_Y_DATOS.md",
    "documentacion/MANUAL_USUARIO.md",
    "documentacion/SEGURIDAD_Y_ERRORES.md",
    "documentacion/PRUEBAS_Y_VALIDACION.md",
    "documentacion/CONTROL_DE_VERSIONES.md",
    "documentacion/integracion_api_frontend.md",
    "documentacion/diagramas/README.md",
    "simulacion/README.md",
    "pruebas/GUIA_PRUEBA_LAN.md",
    "recursos/systemd/INSTALACION_TCP.md",
]

ENLACE = re.compile(r"\[[^\]]+\]\(([^)\n]+)\)")
TIPOS_MERMAID = ("flowchart ", "sequenceDiagram", "erDiagram", "stateDiagram-v2", "gitGraph")


class TestDocumentacion(unittest.TestCase):
    def test_documentos_son_legibles_y_bloques_cerrados(self):
        for nombre in DOCUMENTOS:
            with self.subTest(documento=nombre):
                ruta = ROOT / nombre
                self.assertTrue(ruta.is_file(), f"Falta documento {nombre}")
                texto = ruta.read_text(encoding="utf-8")
                self.assertTrue(texto.startswith("#"), f"Falta encabezado: {nombre}")
                cierres = sum(line.lstrip().startswith("```") for line in texto.splitlines())
                self.assertEqual(cierres % 2, 0, f"Bloque Markdown sin cerrar: {nombre}")

    def test_enlaces_a_archivos_locales_existen(self):
        for nombre in DOCUMENTOS:
            archivo = ROOT / nombre
            texto = archivo.read_text(encoding="utf-8")
            for match in ENLACE.finditer(texto):
                href = match.group(1).split(" ", 1)[0].strip()
                if href.startswith(("http://", "https://", "mailto:", "#", "data:")):
                    continue
                destino = unquote(href.split("#", 1)[0])
                if not destino:
                    continue
                objetivo = (archivo.parent / destino).resolve()
                with self.subTest(archivo=nombre, enlace=href):
                    self.assertTrue(objetivo.is_relative_to(ROOT),
                                    f"Enlace fuera del repositorio: {href}")
                    self.assertTrue(objetivo.exists(), f"Enlace roto: {nombre} → {href}")

    def test_fuentes_mermaid_editables_presentes(self):
        base = ROOT / "documentacion/diagramas/fuentes_mermaid"
        nombres = [
            "arquitectura_p2p.mmd",
            "estructura_y_flujo.mmd",
            "flujo_sincronizacion_8_etapas.mmd",
            "modelo_relacional.mmd",
            "despliegue_lan.mmd",
            "estados_transferencia.mmd",
        ]
        for nombre in nombres:
            with self.subTest(diagrama=nombre):
                texto = (base / nombre).read_text(encoding="utf-8")
                sin_comentarios = "\n".join(
                    linea for linea in texto.splitlines()
                    if linea.strip() and not linea.lstrip().startswith("%%")
                ).lstrip()
                self.assertTrue(sin_comentarios.startswith(TIPOS_MERMAID),
                                f"Diagrama Mermaid sin tipo conocido: {nombre}")


if __name__ == "__main__":
    unittest.main()
