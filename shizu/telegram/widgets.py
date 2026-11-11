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

"""Custom aiogram methods for Telegram Bot API 10.4 HTML widgets.

These classes wrap the widget-related API methods so they can be called
through the standard aiogram Bot instance via ``await bot(method)``.
"""

from typing import Any

from aiogram.methods import TelegramMethod
from aiogram.types import (
    ForceReply,
    InlineKeyboardMarkup,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    ReplyParameters,
)


class SendWidget(TelegramMethod[Message]):
    """Send a message with an HTML widget (Bot API 10.4).

    Source: https://core.telegram.org/bots/api#sendwidget
    """

    __api_method__ = "sendWidget"
    __returning__ = Message

    chat_id: int | str
    html: str
    message_thread_id: int | None = None
    width: int | None = None
    height: int | None = None
    public_data: str | None = None
    chat_data: str | None = None
    caption: str | None = None
    parse_mode: str | None = None
    show_caption_above_media: bool | None = None
    allow_queries: bool | None = None
    is_shared: bool | None = None
    disable_notification: bool | None = None
    protect_content: bool | None = None
    allow_paid_broadcast: bool | None = None
    message_effect_id: str | None = None
    reply_parameters: ReplyParameters | None = None
    reply_markup: InlineKeyboardMarkup | ReplyKeyboardMarkup | ReplyKeyboardRemove | ForceReply | None = None


class AnswerWidgetQuery(TelegramMethod[bool]):
    """Send an answer to a query from a widget (Bot API 10.4).

    Source: https://core.telegram.org/bots/api#answerwidgetquery
    """

    __api_method__ = "answerWidgetQuery"
    __returning__ = bool

    widget_query_id: str
    notification_text: str | None = None
    url: str | None = None


class WidgetQuery:
    """Represents a query from a widget (Bot API 10.4).

    Source: https://core.telegram.org/bots/api#widgetquery
    """

    def __init__(self, **kwargs: Any) -> None:
        for key, value in kwargs.items():
            setattr(self, key, value)
        self._bot = None
        self._event = None

    async def answer(
        self,
        notification_text: str | None = None,
        url: str | None = None,
    ) -> bool:
        """Send an answer to this widget query."""
        if self._bot is None:
            raise RuntimeError("WidgetQuery is not bound to a bot instance")
        return await self._bot(
            AnswerWidgetQuery(
                widget_query_id=self.id,
                notification_text=notification_text,
                url=url,
            )
        )