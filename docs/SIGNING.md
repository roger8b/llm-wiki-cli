# Code-signing & notarizing the macOS desktop app

The desktop app bundles a PyInstaller Python sidecar (~150 ad-hoc-signed
dylibs). Without **notarization**, macOS runs a one-time Gatekeeper assessment
of those dylibs on first launch (a multi-second stall) and shows an
"unidentified developer" warning on machines that downloaded the app. Signing
with a **Developer ID** + notarizing removes both.

> Ad-hoc signing is already done by PyInstaller/Tauri at build time — it is *not*
> enough for Gatekeeper. You need a paid Apple Developer account (Developer ID
> Application certificate) for the real fix.

## What's already wired

- `ui/src-tauri/entitlements.plist` — hardened-runtime entitlements required to
  notarize a PyInstaller app (`disable-library-validation` so the
  Developer-ID-signed app can load the ad-hoc-signed sidecar dylibs, plus
  JIT/unsigned-memory for CPython).
- `ui/src-tauri/tauri.conf.json` → `bundle.macOS.entitlements` points at it.
- `build_desktop.sh` detaches any stale `/Volumes/llm-wiki` before bundling so
  `bundle_dmg.sh` doesn't fail.

Tauri performs signing **and** notarization automatically during
`tauri build` when the right environment variables are present.

## To sign + notarize (with a Developer ID)

1. Install your **Developer ID Application** certificate in the login keychain.
   Confirm it's visible:
   ```bash
   security find-identity -p codesigning -v
   ```
2. Export the signing + notarization credentials, then build:
   ```bash
   # signing
   export APPLE_SIGNING_IDENTITY="Developer ID Application: Your Name (TEAMID)"

   # notarization — either an app-specific password…
   export APPLE_ID="you@example.com"
   export APPLE_PASSWORD="abcd-efgh-ijkl-mnop"   # app-specific password
   export APPLE_TEAM_ID="TEAMID"

   # …or an App Store Connect API key (preferred for CI):
   # export APPLE_API_ISSUER="..."
   # export APPLE_API_KEY="..."
   # export APPLE_API_KEY_PATH="/path/to/AuthKey_XXXX.p8"

   ./build_desktop.sh
   ```
   Tauri signs the app + DMG with the Developer ID, submits to `notarytool`,
   waits, and staples the ticket.
3. Verify:
   ```bash
   spctl -a -vvv -t install "ui/src-tauri/target/release/bundle/macos/llm-wiki.app"
   # → "accepted / source=Notarized Developer ID"
   ```

When `APPLE_SIGNING_IDENTITY` is **unset** (local dev), the build stays ad-hoc
signed and unnotarized — it runs locally but pays the first-launch Gatekeeper
cost and isn't distributable.

## CI (follow-up)

For automated releases, store the certificate (`APPLE_CERTIFICATE` base64 +
`APPLE_CERTIFICATE_PASSWORD`) and the API-key credentials as CI secrets and run
the same `tauri build` step. See the Tauri macOS distribution guide.
