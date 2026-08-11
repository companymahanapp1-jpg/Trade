# Fixed V3

- Centralized exact text for the three primary Reply Keyboard buttons.
- Fixed handler mismatch: handlers match the actual KeyboardButton text, without emoji prefixes.
- Preserved `icon_custom_emoji_id` and `style` on Reply Keyboard buttons.
- Removed Inline Keyboard / CallbackQuery from the project.
- Moved all startup execution to the end of the file so every handler is registered before polling.
- Added non-destructive V3 SQLite migrations.
- Added generic lesson media storage: video/document/photo/audio/voice/animation/video-note/sticker/text.
- Video duration is requested only for videos.
- Added lesson publish state and detailed lesson profile.
- Added quiz/question management, correct option, per-question timer, retry mode and question ordering.
- Added sequential course locking and learner progress.
- Added user search/profile/progress/reset/block/access/message.
- Added ticket history and admin replies.
- Added username-based forced join management and membership test.
- Added admin management with owner protection.
- Added statistics and editable settings.
- Broadcast isolates per-user send failures.
- Added Python syntax/import-level static validation.
