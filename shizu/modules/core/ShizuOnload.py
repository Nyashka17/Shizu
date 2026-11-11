# Shizu Copyright (C) 2023-2026  Ibeswipin

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

# meta banner: https://github.com/ibeswipin/Shizu/raw/refs/heads/beta/assets/banners/ShizuOnload.png

import contextlib
import logging
import re
import time

from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.exceptions import TelegramBadRequest, TelegramUnauthorizedError
from pyrogram import Client, enums
from pyrogram.errors import (
    AuthKeyDuplicated,
    AuthKeyUnregistered,
    BadRequest,
    ChannelInvalid,
    ChannelPrivate,
    MessageIdInvalid,
    PeerIdInvalid,
    SessionExpired,
    SessionRevoked,
    UserDeactivated,
    UserDeactivatedBan,
)
from pyrogram.raw import functions
from pyrogram.raw import types as typ

from shizu import fsm, loader, utils
from shizu.health import reporter
from shizu.version import __version__, branch


@loader.module(name="ShizuOnload", author="hikamoru")
class ShizuOnload(loader.Module):
    """Handles Shizu startup events"""

    strings = {}

    AVATARS_VERSION = 7
    BOT_AVATAR_VERSION = 4

    SERVICE_CHATS = (
        (
            "logs",
            "Shizu-logs",
            "📫 Shizu logs. Do not delete this group, or the bot will break",
            "assets/logs.png",
        ),
        (
            "backup",
            "Shizu-backup",
            "📫 Shizu backups. Do not delete this group, or the bot will break",
            "assets/backups.png",
        ),
        (
            "besafe",
            "Shizu-besafe",
            "🛡 Shizu BeSafe confirmations. Do not delete this group, or the bot will break",
            "assets/besafe.png",
        ),
        (
            "experiments",
            "Shizu-Expiriments",
            "Shizu playground for commands, modules and experiments.",
            "assets/experiments.png",
        ),
    )

    WELCOME_PREFIX = "shizu_welcome:"
    WELCOME_LANGS = (
        ("en", "🇬🇧 English"),
        ("ru", "🇷🇺 Русский"),
        ("uz", "🇺🇿 O'zbekcha"),
    )

    START_TEXT = (
        "🌘 <b><a href='https://github.com/ibeswipin/Shizu'>Shizu Userbot</a></b>"
    )

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "status",
                True,
                lambda m: self.strings("cfg_doc_enable_start_text"),
                label=lambda: self.strings("cfg_label_status"),
            ),
            loader.ConfigValue(
                "custom text",
                None,
                lambda m: self.strings("cfg_doc_start_text"),
                label=lambda: self.strings("cfg_label_custom_text"),
            ),
        )

    def _welcome_markup(self):
        current = self.db.get("shizu.me", "lang", "en")
        return self.bot._generate_markup(
            [
                [
                    {
                        "text": f"✓ {label}" if code == current else label,
                        "data": self.WELCOME_PREFIX + code,
                    }
                    for code, label in self.WELCOME_LANGS
                ],
                [{"text": "👥 Support", "url": "https://t.me/shizu_talks"}],
            ]
        )

    async def _greet(self):
        if self.db.get("shizu.me", "notified", None):
            return
        await self._bot.send_photo(
            self.me.id,
            FSInputFile("assets/welcome.png"),
            caption=self.strings("welcome"),
            reply_markup=self._welcome_markup(),
        )
        self.db.set("shizu.me", "notified", True)

    async def welcome_callback_handler(self, call: CallbackQuery):
        if not (call.data or "").startswith(self.WELCOME_PREFIX):
            return
        if call.from_user.id != self.me.id:
            return await call.answer()
        lang = call.data[len(self.WELCOME_PREFIX) :]
        if lang not in dict(self.WELCOME_LANGS):
            return await call.answer()
        self.db.set("shizu.me", "lang", lang)
        await call.answer()
        with contextlib.suppress(TelegramBadRequest):
            await call.message.edit_caption(
                self.strings("welcome"), reply_markup=self._welcome_markup()
            )

    @loader.on_bot(
        lambda self, app, m: (
            m.text == "/start"
            and m.chat.type == "private"
            and (self.bot._is_owner(m.from_user.id) or not self._feedback_enabled())
        )
    )
    async def start_message_handler(self, app, message):
        markup = self.bot._generate_markup(
            [
                [
                    {
                        "text": "🐈‍⬛ Source",
                        "url": "https://github.com/ibeswipin/Shizu",
                    },
                    {
                        "text": "🪭 Chief Developer",
                        "url": "https://t.me/hikamoru",
                    },
                ],
                [
                    {
                        "text": "👥 Support",
                        "url": "https://t.me/shizu_talks",
                    },
                ],
            ]
        )

        if self.config["status"]:
            text = self.config["custom text"] or self.START_TEXT
            await self.bot.bot.send_message(
                message.chat.id,
                text,
                reply_markup=markup,
                disable_web_page_preview=True,
            )

            # Send an HTML widget after the welcome message
            widget_html = """<div widget="true" style="height: 100vh; display: flex; flex-direction: column; justify-content: center; align-items: center; overflow: hidden; position: relative; background-color: #0a0a0a; color: #e5e5e5; font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;">
  <div style="position: absolute; inset: 0; background-image: linear-gradient(rgba(255,255,255,0.02) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.02) 1px, transparent 1px); background-size: 60px 60px; pointer-events: none;"></div>
  <div style="position: absolute; width: 600px; height: 600px; background: radial-gradient(circle, rgba(255,255,255,0.03) 0%, transparent 70%); top: 50%; left: 50%; transform: translate(-50%, -50%); pointer-events: none;"></div>
  <div style="text-align: center; z-index: 1; padding: 0 24px; max-width: 600px; width: 100%;">
    <div style="width: 48px; height: 48px; border: 1px solid rgba(255,255,255,0.15); border-radius: 12px; margin: 0 auto 40px; display: flex; align-items: center; justify-content: center;">
      <div style="width: 12px; height: 12px; background: #fff; border-radius: 3px;"></div>
    </div>
    <h1 style="font-size: clamp(1.5rem, 4vw, 2.5rem); font-weight: 300; color: #e5e5e5; margin: 0 0 20px; letter-spacing: -0.02em; line-height: 1.2;">Скоро здесь <strong style="font-weight: 500; color: #fff;">что-то будет</strong></h1>
    <p style="font-size: clamp(0.875rem, 2vw, 1rem); color: rgba(255,255,255,0.35); font-weight: 400; line-height: 1.6; margin: 0 0 48px;">Что-то должно быть<br>А возможно тут ничего не будет.</p>
    <div style="width: 40px; height: 1px; background: rgba(255,255,255,0.1); margin: 0 auto 48px;"></div>
    <button onclick="sendQuery('hello')" style="display: inline-flex; align-items: center; gap: 10px; font-size: 0.8125rem; color: rgba(255,255,255,0.3); letter-spacing: 0.05em; text-transform: uppercase; background: none; border: none; cursor: pointer; padding: 0;">
      <span style="width: 6px; height: 6px; background: #4ade80; border-radius: 50%;"></span>
      Нажми меня
    </button>
    <p id="result" style="margin: 16px 0 0; font-size: 0.75rem; color: rgba(255,255,255,0.15); letter-spacing: 0.02em;"></p>
  </div>
  <div style="position: absolute; bottom: 32px; font-size: 0.75rem; color: rgba(255,255,255,0.15); letter-spacing: 0.02em;">© 2026 - by Dream</div>
</div>
<script>
function sendQuery(data) {
  const result = document.getElementById('result');
  result.textContent = 'Sending...';
  Telegram.WebApp.sendWidgetQuery(
    { type: 'query', data: data },
    function(response) {
      result.textContent = 'Response: ' + JSON.stringify(response);
    }
  );
}
</script>"""
            try:
                from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

                markup = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="🐈‍⬛ Source",
                                url="https://github.com/ibeswipin/Shizu",
                            ),
                            InlineKeyboardButton(
                                text="🪭 Chief Developer",
                                url="https://t.me/hikamoru",
                            ),
                        ],
                        [
                            InlineKeyboardButton(
                                text="👥 Support",
                                url="https://t.me/shizu_talks",
                            ),
                        ],
                    ]
                )
                await self.bot.send_widget(
                    chat_id=message.chat.id,
                    html=widget_html,
                    allow_queries=True,
                    caption="Скоро здесь что-то будет",
                    reply_markup=markup,
                )
            except Exception as e:
                logging.exception("Failed to send widget on /start: %s", e)

    async def demo_widget_query_handler(self, query):
        """Answer queries from the widget sent on /start."""
        data = query.query_data or ""
        if data == "hello":
            await query.answer(
                notification_text="Привет от Shizu! 🐙 Виджет работает через Bot API 10.4",
            )
        else:
            await query.answer(notification_text="Unknown query")

    DEAD_SESSION = (
        AuthKeyUnregistered,
        AuthKeyDuplicated,
        SessionRevoked,
        SessionExpired,
        UserDeactivated,
        UserDeactivatedBan,
    )

    @loader.loop(interval=300, autostart=True, wait_before=True)
    async def health_loop(self):
        """Check that the Telegram session and the bot token still work"""
        try:
            await self.app.get_me()
        except self.DEAD_SESSION:
            await reporter.send(
                reporter.SESSION_ENDED + "\n\nShizu restarts to start the login."
            )
            utils.restart()
            return
        except Exception:
            return

        try:
            await self._bot.get_me()
        except TelegramUnauthorizedError as error:
            reporter.problem(
                "bot_token", reporter.BOT_TOKEN.format(utils.escape_html(str(error)))
            )
        except Exception:
            return

    async def on_load(self, app: Client):
        self.adopt_config("ShizuStart")
        try:
            await self._greet()
        except Exception:
            logging.exception("Could not send the welcome message")

        with contextlib.suppress(Exception):
            async for _ in app.get_dialogs():
                pass

        for key, *_ in self.SERVICE_CHATS:
            chat_id = self.db.get("shizu.chat", key)
            if not chat_id:
                continue
            try:
                await app.resolve_peer(chat_id)
            except (ChannelInvalid, ChannelPrivate, PeerIdInvalid):
                logging.warning(
                    "Service chat %s (%s) is gone, recreating", key, chat_id
                )
                self.db.pop("shizu.chat", key)

        if missing := [
            chat
            for chat in self.SERVICE_CHATS
            if not self.db.get("shizu.chat", chat[0])
        ]:
            logging.info("Trying to create service chats")
            app.me = await app.get_me()
            for key, title, description, _ in missing:
                chat = await utils.create_chat(
                    app, title, description, True, True, True
                )
                self.db.set("shizu.chat", key, chat.id)
            logging.info("Service chats created")
            utils.restart()

        chats = {key: self.db.get("shizu.chat", key) for key, *_ in self.SERVICE_CHATS}

        for key, chat_id in chats.items():
            try:
                await utils.ensure_bot_in_chat(app, chat_id)
            except Exception:
                logging.exception("Could not add the bot to service chat %s", key)

        avatars = self.db.get("shizu.chat", "avatars")
        if not isinstance(avatars, dict):
            avatars = {}
        for key, _, _, photo in self.SERVICE_CHATS:
            if avatars.get(str(chats[key])) == self.AVATARS_VERSION:
                continue
            try:
                await app.set_chat_photo(chat_id=chats[key], photo=photo)
                avatars[str(chats[key])] = self.AVATARS_VERSION
            except Exception:
                logging.exception("Could not set the photo of service chat %s", key)
        self.db.set("shizu.chat", "avatars", avatars)

        if self.db.get("shizu.bot", "avatar") != self.BOT_AVATAR_VERSION:
            try:
                async with fsm.Conversation(app, "@BotFather") as conv:
                    await conv.ask("/cancel")
                    await conv.get_response()
                    await conv.ask("/setuserpic")
                    await conv.get_response()
                    await conv.ask(f"@{self.db.get('shizu.bot', 'username')}")
                    await conv.get_response()
                    await conv.ask_media("assets/bot.png", media_type="photo")
                    await conv.get_response()
                self.db.set("shizu.bot", "avatar", self.BOT_AVATAR_VERSION)
            except Exception:
                logging.exception("Could not update the bot avatar")

        peers = sorted(chats.values())
        if bot_username := self.db.get("shizu.bot", "username"):
            peers.append(f"@{bot_username}")
        if self.db.get("shizu.folder", "peers") != peers:
            try:
                await app.invoke(
                    functions.messages.UpdateDialogFilter(
                        id=250,
                        filter=typ.DialogFilter(
                            id=250,
                            title=typ.TextWithEntities(text="Shizu", entities=[]),
                            include_peers=[await app.resolve_peer(i) for i in peers],
                            pinned_peers=[],
                            exclude_peers=[],
                            emoticon="❤️",
                        ),
                    )
                )
                self.db.set("shizu.folder", "peers", peers)
            except Exception:
                logging.exception("Could not create the Shizu chat folder")

        if restart := self.db.get("shizu.updater", "restart"):
            restarted_text = None

            if restart["type"] == "restart":
                start_time = restart.get("start")
                if isinstance(start_time, str):
                    start_time = float(start_time)
                elapsed = round(time.time() - start_time)
                restarted_text = self.strings("start_r").format(elapsed)

            elif restart["type"] == "update":
                start_time = restart.get("start")
                if isinstance(start_time, str):
                    start_time = float(start_time)
                elapsed = round(time.time() - start_time)
                restarted_text = self.strings("start_u").format(elapsed)

            if restarted_text and restart.get("bot"):
                try:
                    await self._bot.edit_message_text(
                        re.sub(r"</?emoji[^>]*>", "", restarted_text),
                        chat_id=restart["chat"],
                        message_id=restart["id"],
                        parse_mode="html",
                    )
                except Exception:
                    logging.exception("Could not edit update message in bot chat")
            elif restarted_text:
                try:
                    try:
                        await app.edit_message_caption(
                            restart["chat"],
                            restart["id"],
                            caption=restarted_text,
                            parse_mode=enums.ParseMode.HTML,
                        )
                    except (BadRequest, MessageIdInvalid):
                        await app.edit_message_text(
                            restart["chat"],
                            restart["id"],
                            restarted_text,
                            parse_mode=enums.ParseMode.HTML,
                        )
                except Exception:
                    logging.exception(
                        "Could not edit restart message, sending a new one"
                    )
                    with contextlib.suppress(Exception):
                        await app.send_message(
                            restart["chat"],
                            restarted_text,
                            parse_mode=enums.ParseMode.HTML,
                        )

            self.db.pop("shizu.updater", "restart")

        commit = utils.get_git_hash()
        build = (
            f' · <a href="https://github.com/ibeswipin/Shizu/commit/{commit}">{commit[:7]}</a>'
            if commit
            else ""
        )
        prefixes = " ".join(
            f"<code>{utils.escape_html(p)}</code>"
            for p in self.db.get("shizu.loader", "prefixes", ["."])
        )
        started_text = (
            "静 <b>Shizu is online</b>\n\n"
            f"<b>Version</b> <code>v{'.'.join(map(str, __version__))}</code> · <code>{branch}</code>{build}\n"
            f"<b>Prefix</b> {prefixes}\n"
            f"<b>Host</b> {utils.get_named_platform()}\n\n"
            f"⚙️ Control panel: /panel in @{self.db.get('shizu.bot', 'username', '')}"
        )
        try:
            await self._bot.send_photo(
                chat_id=self.db.get("shizu.chat", "logs", None),
                photo=FSInputFile("assets/Shizu.png"),
                caption=started_text,
                parse_mode="html",
            )
        except TelegramBadRequest:

            await utils.invite_bot(app, self.db.get("shizu.chat", "logs", None))
            await self._bot.send_photo(
                chat_id=self.db.get("shizu.chat", "logs", None),
                photo=FSInputFile("assets/Shizu.png"),
                caption=started_text,
                parse_mode="html",
            )
        except Exception:
            pass
