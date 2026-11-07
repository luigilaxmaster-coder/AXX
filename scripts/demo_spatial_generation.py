"""Demonstration script: Generates concrete outputs for Ollama vs. GPT-6.1 Sol Fast."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.spatial_plan import (
    extract_or_build_spatial_plan,
    validate_spatial_plan,
    is_gpt_fast_model
)

def run_demo():
    print("=" * 70)
    print("DEMOSTRACIÓN DE GENERACIÓN ESPACIAL EN AXX: OLLAMA vs. GPT-6.1 SOL FAST")
    print("=" * 70)

    # -------------------------------------------------------------
    # ESCENARIO 1: Usuario con Ollama / Gemma (ej. gemma4:31b)
    # Señalamiento preciso con flechas, cajas y diagrama 2D
    # -------------------------------------------------------------
    provider_ollama = "ollama"
    model_ollama = "gemma4:31b"
    allowed_ollama = is_gpt_fast_model(provider_ollama, model_ollama)

    # Gemma identifica elementos y emite coordenadas para señalar y diagramar
    ollama_raw_response = """
He analizado la selección de la placa. Aquí tienes los señalamientos y diagrama de componentes:
```json
{
  "mode": "diagram_2d",
  "summary": "Diagrama de flujo de alimentación y procesamiento de la placa.",
  "annotations_2d": [
    {
      "id": "elem_pwr",
      "type": "arrow",
      "target_box_normalized": [0.10, 0.15, 0.25, 0.30],
      "label": "Entrada 12V",
      "color": "#f59e0b"
    },
    {
      "id": "elem_reg",
      "type": "box",
      "target_box_normalized": [0.35, 0.20, 0.50, 0.40],
      "label": "Regulador de Voltaje",
      "color": "#22c55e"
    },
    {
      "id": "elem_cpu",
      "type": "arrow",
      "target_box_normalized": [0.45, 0.45, 0.75, 0.75],
      "label": "Microprocesador ARM",
      "color": "#38bdf8"
    },
    {
      "id": "elem_led",
      "type": "spotlight",
      "target_box_normalized": [0.80, 0.70, 0.90, 0.82],
      "label": "LED de Estado",
      "color": "#ec4899"
    }
  ]
}
```
"""

    plan_ollama = extract_or_build_spatial_plan(
        ollama_raw_response,
        selection={'shape': 'rect', 'bounds': [120, 80, 540, 420]},
        spatial_3d_allowed=allowed_ollama,
        provider_name=provider_ollama,
        model_name=model_ollama
    )

    print("\n[ESCENARIO 1: OLLAMA / LOCAL (gemma4:31b)]")
    print(f"¿3D Espacial Habilitado?: {allowed_ollama} (Strict Gating enforced)")
    print(f"Modo de presentación: {plan_ollama['mode']}")
    print(f"Resumen para voz: {plan_ollama['summary']}")
    print(f"Plan JSON estructurado generado:")
    print(json.dumps(plan_ollama, indent=2, ensure_ascii=False))

    # -------------------------------------------------------------
    # ESCENARIO 2: Usuario con GPT-6.1 Sol Fast (OpenAI / ChatGPT fast)
    # -------------------------------------------------------------
    provider_gpt = "openai"
    model_gpt = "gpt-6.1-sol-fast"
    allowed_gpt = is_gpt_fast_model(provider_gpt, model_gpt)

    # GPT-6.1 Sol Fast genera el plan declarativo 3D con mallas procedurales y ensamblaje cinemático
    gpt_raw_response = """
Aquí tienes la explicación mecánica completa del pistón:
```json
{
  "mode": "interactive_3d",
  "summary": "Mecanismo de pistón y biela con desplazamiento vertical cíclico.",
  "annotations_2d": [
    {
      "id": "ann_chamber",
      "type": "box",
      "target_box_normalized": [0.05, 0.2, 0.95, 0.8],
      "label": "Cámara de combustión",
      "color": "#38bdf8"
    },
    {
      "id": "ann_spark",
      "type": "spotlight",
      "target_box_normalized": [0.1, 0.45, 0.25, 0.55],
      "label": "Punto de ignición",
      "color": "#f59e0b"
    }
  ],
  "scene_3d": {
    "root_primitives": [
      {
        "id": "cylinder_block",
        "type": "cylinder",
        "dimensions": [4.0, 7.0, 4.0],
        "position": [0.0, 0.0, 0.0],
        "rotation": [0.0, 0.0, 0.0],
        "color": "#475569",
        "exploded_offset": [0.0, 0.0, 0.0]
      },
      {
        "id": "piston_head",
        "type": "piston",
        "dimensions": [3.6, 2.2, 3.6],
        "position": [0.0, 1.5, 0.0],
        "rotation": [0.0, 0.0, 0.0],
        "color": "#38bdf8",
        "exploded_offset": [0.0, 4.5, 0.0]
      },
      {
        "id": "connecting_rod",
        "type": "shaft",
        "dimensions": [0.8, 5.0, 0.8],
        "position": [0.0, -1.8, 0.0],
        "rotation": [0.0, 0.0, 0.15],
        "color": "#94a3b8",
        "exploded_offset": [2.5, -2.0, 0.0]
      },
      {
        "id": "crankshaft_pin",
        "type": "cylinder",
        "dimensions": [1.4, 1.4, 2.0],
        "position": [0.5, -4.2, 0.0],
        "rotation": [1.57, 0.0, 0.0],
        "color": "#f59e0b",
        "exploded_offset": [0.0, -5.0, 0.0]
      }
    ]
  }
}
```
"""

    plan_gpt = extract_or_build_spatial_plan(
        gpt_raw_response,
        selection={'shape': 'rect', 'bounds': [100, 100, 600, 600]},
        spatial_3d_allowed=allowed_gpt,
        provider_name=provider_gpt,
        model_name=model_gpt
    )

    print("\n" + "=" * 70)
    print("[ESCENARIO 2: GPT-6.1 SOL FAST (gpt-6.1-sol-fast)]")
    print(f"¿3D Espacial Habilitado?: {allowed_gpt}")
    print(f"Modo de presentación: {plan_gpt['mode']}")
    print(f"Resumen para voz: {plan_gpt['summary']}")
    print(f"Primitivas 3D sintetizadas: {len(plan_gpt['scene_3d']['root_primitives'])}")
    print("Piezas del ensamblaje:")
    for p in plan_gpt['scene_3d']['root_primitives']:
        print(f"  - [{p['type'].upper()}] id={p['id']}, color={p['color']}, exploded_offset={p['exploded_offset']}")
    print(f"\nPlan JSON estructurado generado:")
    print(json.dumps(plan_gpt, indent=2, ensure_ascii=False))
    print("=" * 70)

if __name__ == '__main__':
    run_demo()
