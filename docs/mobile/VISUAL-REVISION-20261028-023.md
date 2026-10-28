# Android 0.2.3 — visual revision

Date: 2026-10-28. Android versionCode 24. Windows version unchanged by this delivery.

## Changes

- Light surfaces, restrained blue accents, a quieter PC connection chip and a floating four-tab bar.
- One entry to chat on the home screen. Repeated connection copy and inline settings were removed; gestures and microphone controls remain accessible from the character sheet.
- Chat uses a compact composer and readable operation states instead of internal receipt IDs. Applications, catalog, notes, permissions, pending-operation recovery and Stop remain available.
- Remote mouse and keyboard surfaces share the light styling and Spanish labels. Their input ordering, approval and lease logic is unchanged.
- The operational entrypoint no longer loads the prototype stylesheet that overrode headings, typography and colors.
- Text defaults to the app's standard 100% size. The PC settings pane can opt into Android system sizing; the Samsung reported 170%. This preference is local to Axx and does not change Android's global accessibility setting. Invalid native modes are rejected and a failed preference change retains the confirmed selection.
- Native system bars use Capacitor's light-surface setting, keeping time and navigation icons readable. The static/reduced-motion character can use the balanced raster resolution; animated views retain the existing economy mode. This is not a high-frame-rate claim.

## Verification

All 12 browser contracts passed. They cover reconnection, drafts, permissions/catalog refresh, changing desktop appearance, typed parameters, uncertain results without replay, pairing errors, readable chat receipts, text-preference errors, layout at 339 px and a 299 px keyboard viewport, input ordering and Stop. The two remote input contracts were rerun after the final input stylesheet change.

Android built successfully with JDK 21 and was installed in place on the physical Samsung SM-A217M. Its installed APK hash matched the build:

`8013275739b12e77bcba97156ddd9d6f666a94c7cc225b4aa72c41a4f1f4e672`

The existing encrypted pairing identity and draft were preserved. Native standard/system sizing returned 100/170% respectively, the composer stayed above navigation with the real keyboard in both modes, and an invalid native text mode was rejected. The character sheet opened and closed. The phone's palette, shape and material matched the live PC snapshot. A typed `estado del sistema` order reached the installed Windows 0.22.19 executor with `state=succeeded` and `postconditions_passed=true`. The app was left at home in standard text mode.

Actual Android home, PC and input surfaces were captured locally and inspected. The input surface was opened without acquiring a lease or sending text to Windows. Physical acceptance of remote cursor/key effects and audio remains separate. Optical QR scanning was explicitly deferred by the user and was not reopened for this visual revision. No subjective design approval from the user is claimed.
