# Buzz: one-click YouTube transcription

On a YouTube video, click this extension's toolbar icon. It queues the complete
video in the local Buzz app, exports TXT to `Documents/Buzz Transcripts`, and
opens the transcript in Buzz when the saved result is ready. Closing the popup
or browser does not cancel an already queued task.

Requires the browser-enabled macOS Buzz build and Google Chrome. The existing
Buzz API/local model and language settings are used. Local models must already
be downloaded. API use remains billed by the configured provider. The extension
does not contain, request, store or receive API credentials.

## Install locally

1. Install the matching `Buzz.app` in `/Applications`, and restart Buzz.
2. From the source checkout, run:

   ```sh
   uv run --no-sync python scripts/install_browser_extension.py
   ```

   The setup command also prepares the icon from the project's original Buzz artwork.

3. Open `chrome://extensions`, enable Developer mode, choose **Load unpacked**,
   and select this `browser-extension` folder. Pin **Buzz — YouTube to Text**.
4. On a video page, click the pinned icon once. When finished, Buzz opens the
   result. Clicking the same video again reuses the job/result. A failed or
   canceled job is retried only through the explicit **Retry** button.

The manifest's `key` is a public extension identity, not a secret. It keeps the
unpacked extension ID stable. Only this ID is registered in `allowed_origins`.
Its permissions are `activeTab` and `nativeMessaging`: no cookies, browsing
history, content scripts, site-wide access, remote scripts or API endpoint
permissions. The extension sends a validated YouTube URL and job status requests.
The native host only accepts that extension's origin and fixed commands. It
uses a private per-user local queue; it exposes no HTTP port or remote server.

The local queue is separate from disposable audio caches. A task ID is persisted
before submission. Repeated clicks, a popup closing, or a restart never silently
retry a possibly paid task. Already-submitted tasks remain in Buzz's history.

## Uninstall

Remove the extension through Chrome. To unregister the bridge, remove
`~/Library/Application Support/Google/Chrome/NativeMessagingHosts/com.mahmoudbasuony.buzz.json`
and set `enabled` to `false` in
`~/Library/Application Support/Buzz/browser-bridge/enabled.json`, then restart
Buzz. This does not delete transcripts, audio, API credentials or models.

Chrome reference: [native messaging](https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging)
and [activeTab](https://developer.chrome.com/docs/extensions/develop/concepts/activeTab).
