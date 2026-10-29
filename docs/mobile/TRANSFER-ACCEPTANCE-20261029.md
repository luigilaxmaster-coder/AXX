# Axx Transfer — physical phone-to-PC acceptance

Date: **29 October 2026**. Result: **the tested LAN and Tailscale phone-to-PC copies passed**.

## Tested configuration

| Component | Observed configuration |
| --- | --- |
| Phone | Physical Samsung SM_A217M |
| Android app | Axx Mobile `0.2.5-companion`, build `26` |
| Desktop app | Axx Windows `0.22.25` |
| Product transport | Authenticated HTTPS through LAN and Tailscale endpoints; both runs used the same underlying Wi-Fi |
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

The LAN receipt is retained at `build/physical-transfer-20261029/upload.json`.

## Tailscale route

A second real transfer used the PC's Tailscale endpoint with the gateway bound
only to its Tailscale interface. Re-pairing through the Android UI preserved the
device identity, certificate and existing file permissions: reception enabled,
reading disabled.

The phone sent a separately named generated fixture of the same 1,049,652 bytes
in five blocks. The PC confirmed completion, and **Guardar en Descargas** produced
a file matching the size and SHA-256 above. The private receipt is retained at
`build/physical-transfer-20261029/tailscale-transfer.json`.

**The underlying network was still the same Wi-Fi.** This verifies that the
Tailscale endpoint and authenticated transfer work on the tested devices; it does
not demonstrate a transfer between two separate Internet connections.

Private environment fields, device identifiers, network addresses and destination
paths from either receipt are not reproduced here.

After a normal restart of the installed Windows app, the phone reconnected to
the same Tailscale endpoint. The completed transfer and file permissions remained
available. This checks app restart persistence, not interrupted-transfer recovery.

## Scope of this acceptance

These runs verify real phone-to-PC transfers through both endpoints and the
subsequent save through the desktop UI. They do not establish PC-to-phone delivery,
operation between separate Internet connections, dictation, background transfer,
device reboot or interruption recovery, large-file performance, or behavior on other
devices. Those cases require separate acceptance.
