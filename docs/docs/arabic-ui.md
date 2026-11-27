# Arabic interface

Choose **العربية** under Preferences → General → UI Language and restart Buzz.
Arabic is also selected automatically when the system UI locale is Arabic and
no explicit Buzz UI-language preference has been saved. Regional Arabic locales
use the shared `ar` catalog.

The translation uses natural Modern Standard Arabic, consistent terminology and
clear actions. It translates the purpose of a control in its screen context:

| Source | Arabic | Meaning in this product |
| --- | --- | --- |
| Transcribe | تحويل الصوت إلى نص | Recognize the spoken recording |
| Identify speakers | تمييز المتحدثين | Separate speaker turns; not identify a real person |
| Extract speech | عزل الكلام عن الخلفية | Separate speech from background audio |
| Resize | تنسيق المقاطع | Adjust transcript/subtitle segmentation |
| Clear History | حذف من السجل | Delete the selected history records |
| Preferences | الإعدادات | Application settings |

All existing gettext messages, bundled plugin labels and descriptions, and cloud
transcription stages have Arabic translations. Worker status is localized at
the display boundary; checkpoint identities and processing data stay stable.
Arabic has six plural forms in the gettext catalog. Placeholder names, format
specifications and export-template variables are preserved exactly.

The interface uses right-to-left layout. URL, API-key, model-ID and path fields
retain left-to-right text direction. The audio seek slider and its timestamps
also retain their playback direction. Model names, service identifiers and file
extensions retain their original spelling. Qt's Arabic catalog translates its
standard buttons. Native operating-system file dialogs follow the OS language.

This setting controls the interface language. Audio language remains the
transcription option chosen for each recording.
