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


## V4 — Admin Panel Entry & Keyboard/Handler Audit

- Added the missing `F.text == BUTTON_ADMIN` Reply Keyboard handler with strict admin/owner access control.
- Added a global `BUTTON_BACK` handler before FSM handlers so Back is not swallowed by generic state handlers.
- Removed the orphan `support_ticket` FSM state.
- Audited `user_kb()` and `admin_kb()` button texts against registered handlers.
- Rechecked duplicate handlers, duplicate registry button texts, orphan FSM states, main() placement, Premium Emoji fields, and Inline Keyboard/CallbackQuery usage.
