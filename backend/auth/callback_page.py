"""Aesthetic branded callback HTML for Axx OAuth authentication."""
from __future__ import annotations
import base64
from pathlib import Path

def get_callback_html(success: bool, message: str, user_name: str | None = None) -> bytes:
    icon_b64 = ""
    icon_path = Path(__file__).resolve().parents[2] / 'master_icon.png'
    if icon_path.exists():
        try:
            icon_b64 = "data:image/png;base64," + base64.b64encode(icon_path.read_bytes()).decode('ascii')
        except Exception:
            pass

    is_invalid_client = "invalid_client" in message.lower()
    status_icon = "✓" if success else ("⚠️" if is_invalid_client else "✕")
    status_title = "¡Conexión completada!" if success else ("Diagnóstico: Cliente OAuth no registrado" if is_invalid_client else "No se pudo completar la conexión")
    if success:
        status_sub = f"Bienvenido, <strong>{user_name}</strong>. Tu suscripción de ChatGPT se ha vinculado a Axx con éxito.<br>Ya puedes cerrar esta ventana y regresar a tu escritorio."
    elif is_invalid_client:
        status_sub = (
            "<strong>Diagnóstico:</strong> OpenAI requiere registro previo de aplicación en su plataforma para autorizaciones directas en clientes de escritorio locales.<br><br>"
            "<strong>Solución recomendada:</strong> Regresa a Axx Desktop y usa tu <strong>Clave de API</strong> (OpenAI, OpenRouter o compatible) en la pestaña <code>🔑 Por API</code> para activación inmediata sin restricciones."
        )
    else:
        status_sub = f"Ocurrió un inconveniente al validar la autorización:<br><code>{message}</code><br>Puedes cerrar esta ventana e intentarlo nuevamente desde Ajustes de Axx."
    accent_color = "#38bdf8" if success else ("#f59e0b" if is_invalid_client else "#f43f5e")
    glow_color = "rgba(56, 189, 248, 0.35)" if success else ("rgba(245, 158, 11, 0.35)" if is_invalid_client else "rgba(244, 63, 94, 0.35)")

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Axx Desktop · Autorización ChatGPT</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <style>
    :root {{
      --bg: #07090e;
      --card-bg: rgba(15, 20, 31, 0.75);
      --border: rgba(255, 255, 255, 0.1);
      --accent: {accent_color};
      --glow: {glow_color};
    }}
    * {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }}
    body {{
      background: var(--bg);
      color: #f1f5f9;
      font-family: 'Plus Jakarta Sans', system-ui, -apple-system, sans-serif;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      overflow: hidden;
      position: relative;
    }}
    /* Glowing liquid ambient orbs */
    .ambient {{
      position: absolute;
      width: 500px;
      height: 500px;
      border-radius: 50%;
      filter: blur(120px);
      opacity: 0.5;
      pointer-events: none;
      animation: float 10s ease-in-out infinite alternate;
    }}
    .ambient-1 {{
      top: -100px;
      left: -100px;
      background: radial-gradient(circle, #38bdf8 0%, #6366f1 100%);
    }}
    .ambient-2 {{
      bottom: -100px;
      right: -100px;
      background: radial-gradient(circle, #a855f7 0%, #06b6d4 100%);
      animation-delay: -5s;
    }}
    @keyframes float {{
      0% {{ transform: translate(0, 0) scale(1); }}
      100% {{ transform: translate(40px, 40px) scale(1.1); }}
    }}
    .card {{
      position: relative;
      background: var(--card-bg);
      backdrop-filter: blur(24px);
      -webkit-backdrop-filter: blur(24px);
      border: 1px solid var(--border);
      border-radius: 28px;
      padding: 48px 40px;
      width: 90%;
      max-width: 480px;
      text-align: center;
      box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.7), 0 0 40px var(--glow);
      z-index: 10;
      animation: scaleIn 0.6s cubic-bezier(0.16, 1, 0.3, 1);
    }}
    @keyframes scaleIn {{
      0% {{ opacity: 0; transform: scale(0.92) translateY(20px); }}
      100% {{ opacity: 1; transform: scale(1) translateY(0); }}
    }}
    .avatar-wrapper {{
      position: relative;
      width: 110px;
      height: 110px;
      margin: 0 auto 24px auto;
      display: flex;
      align-items: center;
      justify-content: center;
    }}
    .avatar-glow {{
      position: absolute;
      inset: -10px;
      border-radius: 50%;
      background: radial-gradient(circle, var(--accent) 0%, transparent 70%);
      opacity: 0.6;
      animation: pulse 3s ease-in-out infinite alternate;
    }}
    @keyframes pulse {{
      0% {{ transform: scale(0.95); opacity: 0.4; }}
      100% {{ transform: scale(1.15); opacity: 0.8; }}
    }}
    .avatar-img {{
      position: relative;
      width: 96px;
      height: 96px;
      border-radius: 50%;
      object-fit: contain;
      z-index: 2;
      filter: drop-shadow(0 10px 15px rgba(0, 0, 0, 0.5));
    }}
    .badge {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      background: rgba(255, 255, 255, 0.06);
      border: 1px solid var(--border);
      padding: 6px 16px;
      border-radius: 999px;
      font-size: 13px;
      font-weight: 600;
      letter-spacing: 0.5px;
      color: var(--accent);
      margin-bottom: 20px;
      text-transform: uppercase;
    }}
    .badge-dot {{
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--accent);
      box-shadow: 0 0 10px var(--accent);
    }}
    h1 {{
      font-size: 26px;
      font-weight: 700;
      letter-spacing: -0.5px;
      margin-bottom: 12px;
      background: linear-gradient(135deg, #ffffff 0%, #cbd5e1 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }}
    p {{
      font-size: 15px;
      line-height: 1.6;
      color: #94a3b8;
      margin-bottom: 32px;
    }}
    p strong {{
      color: #e2e8f0;
      font-weight: 600;
    }}
    code {{
      font-family: 'JetBrains Mono', monospace;
      font-size: 13px;
      background: rgba(0, 0, 0, 0.4);
      padding: 2px 6px;
      border-radius: 6px;
      color: #fca5a5;
    }}
    .btn {{
      display: inline-block;
      width: 100%;
      padding: 14px 24px;
      border-radius: 16px;
      background: linear-gradient(135deg, #0284c7 0%, #6366f1 100%);
      color: #ffffff;
      font-weight: 600;
      font-size: 15px;
      text-decoration: none;
      cursor: pointer;
      border: none;
      box-shadow: 0 10px 20px -5px rgba(2, 132, 199, 0.5);
      transition: all 0.2s ease;
    }}
    .btn:hover {{
      transform: translateY(-2px);
      box-shadow: 0 14px 26px -5px rgba(2, 132, 199, 0.65);
    }}
    .btn:active {{
      transform: translateY(0);
    }}
    .footer-note {{
      margin-top: 24px;
      font-size: 12px;
      color: #64748b;
    }}
  </style>
</head>
<body>
  <div class="ambient ambient-1"></div>
  <div class="ambient ambient-2"></div>
  
  <div class="card">
    <div class="avatar-wrapper">
      <div class="avatar-glow"></div>
      {"<img src='" + icon_b64 + "' alt='Axx' class='avatar-img'>" if icon_b64 else "<div style='font-size: 48px; position: relative; z-index: 2;'>✨</div>"}
    </div>
    
    <div class="badge">
      <span class="badge-dot"></span>
      Axx Desktop Assistant
    </div>
    
    <h1>{status_title}</h1>
    <p>{status_sub}</p>
    
    <button class="btn" onclick="window.close();">Cerrar pestaña</button>
    <div class="footer-note">Axx está ejecutándose y esperándote sobre tu escritorio.</div>
  </div>
</body>
</html>
"""
    return html.encode('utf-8')
