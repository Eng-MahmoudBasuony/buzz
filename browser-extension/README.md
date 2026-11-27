# Buzz: one-click YouTube transcription

On a YouTube video, click this extension's toolbar icon. It queues the complete
video in the local Buzz app and opens the transcript automatically when ready.
New jobs export TXT to `Documents/Buzz Transcripts`; saved results are reused.
Closing the popup
or browser does not cancel an already queued task.

Requires the browser-enabled macOS Buzz build and Google Chrome. The existing
Buzz API/local model and language settings are used. Local models must already
be downloaded. API use remains billed by the configured provider. The extension
does not contain, request, store or receive API credentials.

## Install locally

1. Install the matching `Buzz.app` in `/Applications`.
2. Download **[Buzz-Chrome-Setup-1.0.1-macOS.zip](https://github.com/Eng-MahmoudBasuony/buzz/releases/download/v1.4.6-mb.1/Buzz-Chrome-Setup-1.0.1-macOS.zip)**
   and extract it. Double-click **Install Buzz Extension.command**. No Python,
   uv, repository checkout or administrator password is needed. Quit and reopen
   Buzz once afterward so it picks up the connection.
3. Open `chrome://extensions`, enable Developer mode and choose **Load unpacked**.
   Press Command+Shift+G and select
   `~/Library/Application Support/Buzz/Chrome/extension`.
   Remove an older Buzz extension loaded from another folder first, then pin
   **Buzz — YouTube to Text**. Chrome requires this manual step once.
4. On a video page, click the pinned icon once. When finished, Buzz opens the
   result. Clicking the same video again reuses the job/result. A failed or
   canceled job is retried only through the explicit **Retry** button.

Setup installs a permanent copy, so deleting the downloaded setup folder does
not break the extension. The package contains an Arabic/English **Quick Start.html**.
For an update, rerun the installer and reload the extension in Chrome.

Developers may still register directly from a source checkout with
`uv run --no-sync python scripts/install_browser_extension.py`; that method
loads this repository's `browser-extension` folder instead.

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
and remove `~/Library/Application Support/Buzz/browser-bridge/enabled.json`
and `~/Library/Application Support/Buzz/Chrome`, then restart Buzz.
This does not delete transcripts, audio, API credentials or models.

Chrome reference: [native messaging](https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging)
and [activeTab](https://developer.chrome.com/docs/extensions/develop/concepts/activeTab).
