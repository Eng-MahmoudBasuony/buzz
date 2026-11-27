# Buzz — Mahmoud Basuony fork

[العربية](readme/README.ar.md) · [Upstream project](https://github.com/chidiwilliams/buzz) · [Upstream documentation](https://chidiwilliams.github.io/buzz/) · [中文（上游）](readme/README.zh_CN.md)

Transcribe audio, video files and YouTube videos, then review, edit and export
the resulting text. Local models run on your computer; supported API services
are optional and billed separately by their providers.

This is an independently maintained fork of **[Buzz](https://github.com/chidiwilliams/buzz)**,
originally created by **Chidi Williams** and its contributors. The additions in
this fork are maintained by **[Mahmoud Basuony](https://github.com/Eng-MahmoudBasuony)**.
It is not an official upstream release. The original [MIT license](LICENSE) and
copyright notice are retained.

## What's different in this fork

- **Focused home:** YouTube link entry, language and model selection, recent
  transcripts, real queue status and a searchable library.
- **Dark transcript studio:** editable passages and timestamps, source details,
  search, playback controls and a seekable waveform drawn from decoded audio.
- **Professional Arabic interface:** contextual Arabic translations, RTL layouts,
  bundled plugin translations, and LTR URLs, paths, timestamps and Latin code.
  The interface language and the transcription language are separate settings.
- **One-click YouTube transcription in Chrome:** send the current video to Buzz,
  start transcription and open its text automatically when complete. Repeated
  clicks reopen the saved result rather than starting another transcription.
- **Transcription reliability:** resumable cloud transcription of files and
  YouTube videos, clearer processing phases and explicit retry behavior. API
  credentials remain in Buzz; preparing local file/YouTube jobs and opening
  saved text do not require Keychain access.

The fork retains Buzz's existing local transcription backends, microphone
recording, speaker separation/labeling, watch folders, plugins and **TXT, SRT
and VTT** exports. See the [upstream documentation](https://chidiwilliams.github.io/buzz/)
for the original feature set.

## Getting this version

The modified application and Chrome integration have been tested on **macOS
with Apple Silicon**. The Chrome bridge currently supports **macOS and Google
Chrome**; this does not claim equivalent verification on other platforms.

**No binary release has been published from this fork yet.** Future packaged
builds belong on [this fork's Releases page](https://github.com/Eng-MahmoudBasuony/buzz/releases).
Upstream SourceForge, app-store and `buzz-captions` PyPI packages install the
upstream distribution and do not include these fork-specific changes.

For development, use this repository and its submodules, selecting the branch
or tag containing the changes you want to build. The workspace and browser
changes are tracked in [pull request #3](https://github.com/Eng-MahmoudBasuony/buzz/pull/3).
This checkout requires **Python 3.13** as declared in [pyproject.toml](pyproject.toml).
See [CONTRIBUTING.md](CONTRIBUTING.md) for platform prerequisites and development
guidance, using this fork's repository URL when cloning. Packaging is defined in
[Makefile](Makefile) and [Buzz.spec](Buzz.spec).

## Use the Arabic interface

Choose **Preferences → General → UI Language → العربية**, then restart Buzz.
Choose the spoken language separately when starting a transcription.

Read the [Arabic interface notes](docs/docs/arabic-ui.md) and
[workspace guide](docs/docs/focused-workspace.md) for details.

## Set up the Chrome extension

1. Install a matching build of this fork as `/Applications/Buzz.app`.
2. From a prepared source checkout, register the local bridge:

   ```sh
   uv run --no-sync python scripts/install_browser_extension.py
   ```

3. Open Chrome's extension manager, enable **Developer mode**, choose **Load
   unpacked**, and select the repository's `browser-extension` folder.
4. Pin **Buzz — YouTube to Text**, open a YouTube video, and click its toolbar
   icon. Buzz opens the transcript automatically after completion.

The extension uses Buzz's saved model and language settings. Download a local
model first, or configure an API service in Buzz. API costs, if any, are charged
by the configured provider. The extension does not receive your API key; its
only permissions are `activeTab` and `nativeMessaging`.

A video page is required; channel and playlist pages are not accepted. Closing
the popup does not cancel an already queued task. Failed or canceled jobs need
an explicit retry. See the [extension guide](browser-extension/README.md) for
requirements, setup and removal.

## Validation

Manual tests on the installed macOS application covered:

- Local Arabic transcription, opening text, editing it, and reopening it to
  verify that the changes were saved.
- TXT, SRT and VTT export, including exported text and subtitle timings.
- A real Chrome toolbar click on a previously untranscribed YouTube video:
  Buzz launched, transcribed it locally, and opened the matching text without
  another click.
- Reopening the same video from the extension without creating another
  transcription.

Targeted Python/Qt and extension JavaScript tests also passed. These checks
validate the workflow; recognition accuracy depends on the audio and model.

## Support and attribution

Report fork-specific problems in [this repository's issues](https://github.com/Eng-MahmoudBasuony/buzz/issues),
including the OS, model and reproduction steps. Remove API keys and other
sensitive information before sharing logs.

The original project, documentation and releases remain available at
[chidiwilliams/buzz](https://github.com/chidiwilliams/buzz). This fork keeps its
own changes and release information separate while preserving the upstream
project's attribution and [MIT license](LICENSE).
