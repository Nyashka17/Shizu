"""
█ █ ▀ █▄▀ ▄▀█ █▀█ ▀    ▄▀█ ▀█▀ ▄▀█ █▀▄▀█ ▄▀█
█▀█ █ █ █ █▀█ █▀▄ █ ▄  █▀█  █  █▀█ █ ▀ █ █▀█

Copyright 2022 t.me/hikariatama
Licensed under the GNU GPLv3
"""

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

import collections
import html
import logging

from pyrogram import Client, types

from shizu import loader, utils, version

logger = logging.getLogger(__name__)


@loader.module("ShizuInfo", "hikamoru")
class InformationMod(loader.Module):
    """Info"""

    strings = {}

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "custom_message", None, lambda: self.strings("custom_msg")
            ),
            loader.ConfigValue(
                "custom_buttons",
                {"text": "🤝 Support", "url": "https://t.me/shizu_talks"},
                lambda: self.strings("custom_button"),
            ),
            loader.ConfigValue(
                "photo_url",
                "https://github.com/ibeswipin/Shizu/raw/refs/heads/beta/assets/shizubanner.jpg",
                lambda: self.strings("photo_url"),
            ),
            loader.ConfigValue(
                "rich",
                False,
                lambda: self.strings("rich"),
                validator=loader.validators.Boolean(),
            ),
        )

    async def text_(self, me: types.User, username):
        """Get text"""
        mention = f'<a href="tg://user?id={me.id}">{utils.escape_html(utils.get_display_name(me))}</a>'
        prefix = ", ".join(self.prefix)

        if self.config["custom_message"]:
            values = {
                **await utils.get_placeholders(),
                "mention": mention,
                "version": ".".join(map(str, version.__version__)),
                "prefix": prefix,
                "branch": version.branch,
                "platform": utils.get_platform(),
            }
            return "🐙 Shizu\n" + self.config["custom_message"].format_map(
                collections.defaultdict(str, values)
            )

        stats = utils.render_table(
            [
                [self.strings("label_version"), ".".join(map(str, version.__version__))],
                [self.strings("label_branch"), version.branch],
                [self.strings("label_platform"), utils.get_platform()],
                [self.strings("label_prefix"), prefix],
                [self.strings("label_bot"), f"@{username}"],
            ]
        )
        return f"🐙 <b>Shizu</b> — {mention}\n{stats}"

    async def _rich_banner(self, bot_user) -> str | None:
        """Inline rich media must already be uploaded by the same bot."""
        source = self.config["photo_url"]
        if not source:
            return None

        cached = self.get("rich_banner", {})
        if (
            cached.get("source") == source
            and cached.get("bot_id") == bot_user.id
            and cached.get("file_id")
        ):
            return cached["file_id"]

        uploaded = await self.bot.bot.send_photo(
            self.db.get("shizu.chat", "logs") or self.me.id,
            photo=source,
            disable_notification=True,
        )
        try:
            file_id = uploaded.photo[-1].file_id
            self.set(
                "rich_banner",
                {"source": source, "bot_id": bot_user.id, "file_id": file_id},
            )
            return file_id
        finally:
            try:
                await self.bot.bot.delete_message(
                    uploaded.chat.id, uploaded.message_id
                )
            except Exception:
                logger.debug("Could not delete temporary info banner", exc_info=True)

    async def _rich_message(self, bot_user, fallback_text: str) -> dict:
        """Banner, quoted info table and one button in its own rich row."""
        photo_id = await self._rich_banner(bot_user)
        if self.config["custom_message"]:
            content = fallback_text
        else:
            mention = (
                f'<a href="tg://user?id={self.me.id}">'
                f"{utils.escape_html(utils.get_display_name(self.me))}</a>"
            )
            rows = [
                ("🪐 Version:", "🎯 " + ".".join(map(str, version.__version__))),
                ("✻ Branch:", f"🕯 {version.branch}"),
                ("🌐 Platform:", f"💎 {utils.get_platform()}"),
                ("🪶 Prefix:", "▹ " + ", ".join(self.prefix)),
            ]
            cells = "".join(
                f"<tr><td>{utils.escape_html(label)}</td>"
                f"<td>{utils.escape_html(value)}</td></tr>"
                for label, value in rows
            )
            username = utils.escape_html(bot_user.username)
            cells += (
                '<tr><td>🤖 Bot:</td><td>'
                f'<a href="https://t.me/{username}">@{username}</a></td></tr>'
            )
            content = (
                f"<h2>🐙 Shizu — {mention}</h2>"
                f"<table bordered>{cells}</table>"
            )

        payload = {"html": f"<blockquote>{content}</blockquote>"}
        if photo_id:
            payload["html"] = (
                '<blockquote><img src="tg://photo?id=banner"/></blockquote>'
                + payload["html"]
            )
            payload["media"] = [
                {"id": "banner", "media": {"type": "photo", "media": photo_id}}
            ]

        button = self.config["custom_buttons"]
        if button:
            style = button.get("style", "danger")
            if style not in {"primary", "success", "danger"}:
                style = "danger"
            payload["html"] += (
                '<tg-button-row>'
                f'<tg-button type="url" style="{style}" '
                f'url="{html.escape(button["url"])}">'
                f'{utils.escape_html(button["text"])}</tg-button>'
                '</tg-button-row>'
            )
        return payload

    @loader.command(aliases=["ubinfo", "support"])
    async def info(self, app: Client, message: types.Message):
        """Info about Shizu"""
        bot_user = await self.bot.bot.get_me()
        text = await self.text_(self.me, bot_user.username)
        if self.config["rich"]:
            try:
                payload = await self._rich_message(bot_user, text)
            except Exception:
                logger.warning(
                    "Could not prepare rich info; using the regular info card",
                    exc_info=True,
                )
            else:
                button = self.config["custom_buttons"]
                if button:
                    text += (
                        f'\n<a href="{html.escape(button["url"])}">'
                        f'{utils.escape_html(button["text"])}</a>'
                    )
                return await self.inline.form(
                    text=text,
                    message=message,
                    rich_message=payload,
                )

        if self.config["custom_buttons"]:
            await message.answer(
                response=text,
                reply_markup=[[self.config["custom_buttons"]]],
                photo=self.config["photo_url"],
            )
        else:
            await message.answer(
                response=self.config["photo_url"],
                photo_=True,
                caption=text,
            )
