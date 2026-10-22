# README gallery

Captured on October 22, 2026 from source revision `9a9d05d`.

| Image | Source | Capture |
| --- | --- | --- |
| `desktop-orbit.png` | `1.AXX/Axx.html` | Existing character renderer and circular menu; 500 × 500 CSS-pixel capture at 2× resolution |
| `mobile-pairing.png` | `mobile/client.html` and operational scripts | Pairing dialog, before entering any link |
| `mobile-trackpad.png` | `mobile/js/remote-control.js` | Control surface before PC authorization |
| `mobile-keyboard.png` | `mobile/js/remote-control.js` | Text and shortcut controls before PC authorization |

Mobile viewports are 412 × 780 CSS pixels at 2× resolution. Captures use the operational `mobile/www` bundle, not the historical mobile prototype.

These are isolated Chromium presentation captures. The desktop host geometry is supplied by a fixture; the mobile native fixture reports an unpaired device. No live pairing token, personal conversation or provider credential is included. No real PC input was injected. The character and UI pixels come from the existing application renderer and components; they were not generated or retouched.

These images do not certify connectivity, Android permissions, remote control or voice. See [the verification report](../../mobile/PAIRING-VERIFICATION.md) for executed checks and remaining acceptance work.
