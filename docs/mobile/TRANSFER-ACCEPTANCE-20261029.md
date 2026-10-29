# Axx Transfer — physical phone-to-PC acceptance

Date: **29 October 2026**. Result: **the tested phone-to-PC copy passed**.

## Tested configuration

| Component | Observed configuration |
| --- | --- |
| Phone | Physical Samsung SM_A217M |
| Android app | Axx Mobile `0.2.5-companion`, build `26` |
| Desktop app | Axx Windows `0.22.25` |
| Product transport | Authenticated HTTPS over Wi-Fi, using the existing paired PC |
| Test data | A generated binary fixture; no user document |
| Size | 1,049,652 bytes in five 256 KiB-or-smaller blocks |

The Android update used an in-place installation and preserved the existing pairing.
ADB and CDP prepared the fixture, operated the real UI and inspected the result.
The system document picker (SAF), native Android plugin, installed Windows backend
and HTTPS transfer were real; no transport mocks were used. USB was used for test
setup and inspection, not for the Axx copy from the phone to the PC.

## Observed result

1. The phone selected the fixture through Android's document picker and sent it
   from **Archivos → Enviar archivo**.
2. The phone displayed **Recibido y verificado en tu PC** and cleared its pending
   transfer record.
3. The PC recorded `direction=to_pc`, `state=completed`, `stored=true`, five
   confirmed blocks and 1,049,652 confirmed bytes.
4. **Guardar en Descargas** in the PC UI produced the final exported file.
5. The exported file's size and SHA-256 matched the fixture and transfer receipt:

```text
c4b97b48a5aeb7328d462fef66b29350d770f05d64c88eb5d37af4dc3bd89c49
```

The local receipt is retained at `build/physical-transfer-20261029/upload.json`.
Its private environment fields, device identifiers and destination paths are not
reproduced here.

## Scope of this acceptance

This run verifies one real phone-to-PC transfer on the same Wi-Fi network and the
subsequent save through the desktop UI. It does not establish PC-to-phone delivery,
different-network/Tailscale operation, dictation, background transfer, restart or
interruption recovery, large-file performance, or behavior on other devices.
Those cases require separate acceptance; Tailscale verification remains pending.
