from datetime import date, datetime, timedelta
import inspect
import logging
from typing import Dict, List
import requests
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, \
    ReplyKeyboardRemove
from telegram.ext import CommandHandler, Updater, CallbackContext, ConversationHandler, \
    CallbackQueryHandler
from telegram_bot_calendar import LSTEP, WMonthTelegramCalendar

example_data = {
    "BASEMENT": [{"id": "SKB-45-25", "start": "2021-12-06T19:15:00Z", "end": "2021-12-06T21:15:00Z", "freeSpots": 4},
                 {"id": "SKB-46-25", "start": "2021-12-06T19:30:00Z", "end": "2021-12-06T21:30:00Z", "freeSpots": 8},
                 {"id": "SKB-47-25", "start": "2021-12-06T19:45:00Z", "end": "2021-12-06T21:45:00Z", "freeSpots": 17},
                 {"id": "SKB-48-25", "start": "2021-12-06T20:00:00Z", "end": "2021-12-06T22:00:00Z", "freeSpots": 17},
                 {"id": "SKB-49-25", "start": "2021-12-06T20:15:00Z", "end": "2021-12-06T22:00:00Z", "freeSpots": 17}],
    "SALAME": [{"id": "SLM-45-25", "start": "2021-11-06T19:15:00Z", "end": "2021-11-06T21:15:00Z", "freeSpots": 4},
               {"id": "SLM-46-25", "start": "2021-11-06T19:30:00Z", "end": "2021-11-06T21:30:00Z", "freeSpots": 8},
               {"id": "SLM-47-25", "start": "2021-11-06T19:45:00Z", "end": "2021-11-06T21:45:00Z", "freeSpots": 17},
               {"id": "SLM-48-25", "start": "2021-11-06T20:00:00Z", "end": "2021-11-06T22:00:00Z", "freeSpots": 17},
               {"id": "SLM-49-25", "start": "2021-11-06T20:15:00Z", "end": "2021-11-06T22:00:00Z", "freeSpots": 17}],
    "PODA": []
}
CALENDAR, PLACE, TIME, CONFIRMATION = range(4)

backend_url = os.environ.get('BACKEND_URL')


class BookingRequest:
    def __init__(self, user_id: int):
        self.place: str = None
        self.start: str = None
        self.end: str = None
        self.id: str = None
        self.user_id = user_id


def _get_user_id(update: Update) -> int:
    return update.effective_chat.id


def easy_to_read(date_str: str) -> str:
    return (datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%SZ") + timedelta(hours=1)).strftime("%H:%M")


def easy_to_read_date(date_str: str) -> str:
    return (datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%SZ") + timedelta(hours=1)).strftime("%d.%m.%Y")


def user_exist(user_id: int) -> bool:
    request_data = requests.get(
        f"""{backend_url}user/{user_id}""")
    return request_data.status_code == 200


class TheBot:
    def __init__(self, token: str):
        self._token = token
        self._user_to_request: Dict[int, BookingRequest] = {}
        self._user_to_data: Dict[int, Dict[str, List[Dict[str, str]]]] = {}

    def welcome(self, update: Update, context: CallbackContext):
        update.message.reply_text(text=inspect.cleandoc("""Welcome human, you can book bouldering spots with me ;)!!
                                       - /book  to start
                                       - /profile   to change your profile (not available yet)"""))

    def show_calendar(self, update: Update, context: CallbackContext):
        user_id = _get_user_id(update)
        print(user_id)
        self._clean_user_data(user_id)

        calendar, step = WMonthTelegramCalendar(min_date=date.today()).build()
        query = update.callback_query
        if query:  # checking if the request is a "back" request
            context.bot.edit_message_text(f"Select {LSTEP[step]} or /cancel",
                                          query.message.chat.id,
                                          query.message.message_id,
                                          reply_markup=calendar)
        else:  # this comes from /booking -> what a mess :P
            context.bot.send_message(user_id,
                                     f"Select {LSTEP[step]} or /cancel",
                                     reply_markup=calendar)
        return CALENDAR

    def manage_calendar(self, update: Update, context: CallbackContext):
        bot = context.bot
        query = update.callback_query
        result, key, step = WMonthTelegramCalendar().process(query.data)
        if not result and key:
            bot.edit_message_text(f"Select {LSTEP[step]} or /cancel",
                                  query.message.chat.id,
                                  query.message.message_id,
                                  reply_markup=key)
            return CALENDAR
        elif result:
            bot.edit_message_text(f"You selected {result}",
                                  query.message.chat.id,
                                  query.message.message_id)
            return self.start_booking(update, context, result)

    def start_booking(self, update: Update, context: CallbackContext, result_date: date):
        request_data = requests.get(
            f"""{backend_url}book?from={result_date.strftime("%Y-%m-%dT%H:%M:%SZ")}&to={result_date.strftime("%Y-%m-%dT23:00:00Z")}""").json()
        query = update.callback_query
        buttons = [[InlineKeyboardButton(text=f"{key} | {len(value)}", callback_data=key)] for key, value in
                   request_data.items() if len(value) > 0]
        user_id = _get_user_id(update)
        if len(buttons) == 0:
            query.edit_message_text(text=f'Sorry, there are no free slots for {result_date.strftime("%Y-%m-%d")} :(')
            return ConversationHandler.END

        self._user_to_request[user_id] = BookingRequest(user_id)
        self._user_to_data[user_id] = request_data

        buttons.append([InlineKeyboardButton(text="🔙",
                                             callback_data="GO-CALENDAR")])  # adding also the go back to Calendar button
        query.edit_message_text(text="Where do you want to go? Or /cancel",
                                reply_markup=InlineKeyboardMarkup(
                                    inline_keyboard=buttons,
                                ))
        return PLACE

    def place(self, update: Update, context: CallbackContext):
        user_id = _get_user_id(update)
        query = update.callback_query

        chosen_boulder_place = query.data
        if chosen_boulder_place == "GO-CALENDAR":
            return self.show_calendar(update, context)

        self._user_to_request[user_id].place = chosen_boulder_place
        query.answer()
        buttons = [InlineKeyboardButton(
            text=f"""{easy_to_read(value["start"])} - {easy_to_read(value["end"])} | {value["freeSpots"]}""",
            callback_data=value["id"])
            for value in
            self._user_to_data[user_id][chosen_boulder_place]]
        grouped_buttons = [buttons[x:x + 2] for x in range(0, len(buttons), 2)]
        grouped_buttons.append([InlineKeyboardButton(text="🔙",
                                                     callback_data="GO-PLACE")])  # adding also the go back to here button

        query.edit_message_text(text="What time do you want to go? Or /cancel",
                                reply_markup=InlineKeyboardMarkup(
                                    inline_keyboard=grouped_buttons,
                                )
                                )
        return TIME

    def time(self, update: Update, context: CallbackContext):
        user_id = _get_user_id(update)
        query = update.callback_query
        query.answer()

        chosen_id = query.data
        if chosen_id == "GO-PLACE":  # this is ugly, but works :/
            self._user_to_request[user_id] = BookingRequest(user_id)
            buttons = [[InlineKeyboardButton(text=f"{key} | {len(value)}", callback_data=key)] for key, value in
                       self._user_to_data[user_id].items() if len(value) > 0]
            buttons.append([InlineKeyboardButton(text="🔙",
                                                 callback_data="GO-CALENDAR")])  # adding also the go back to Calendar button
            query.edit_message_text(text="Where do you want to go? Or /cancel",
                                    reply_markup=InlineKeyboardMarkup(
                                        inline_keyboard=buttons,
                                    ))
            return PLACE

        user_request = self._user_to_request[user_id]

        chosen_slot = next(
            filter(lambda slot: slot["id"] == chosen_id, self._user_to_data[user_id][user_request.place])
        )
        user_request.start = chosen_slot["start"]
        user_request.end = chosen_slot["end"]
        user_request.id = chosen_slot["id"]
        buttons = [
            InlineKeyboardButton(text="Cancel", callback_data="NO")
        ]
        if user_exist(user_id):
            buttons.append(InlineKeyboardButton(text="Yes", callback_data="YES"))

        query.edit_message_text(text=inspect.cleandoc(f"""You chose: 
                                      | {user_request.place} the {easy_to_read_date(user_request.start)}
                                      | from: {easy_to_read(user_request.start)}
                                      | to: {easy_to_read(user_request.end)}
                                      Do you confirm? """),
                                reply_markup=InlineKeyboardMarkup(
                                    inline_keyboard=[buttons, [InlineKeyboardButton(text="🔙",
                                                                                    callback_data="GO-TIME")]],
                                )
                                )
        return CONFIRMATION

    def confirmation(self, update: Update, context: CallbackContext):
        query = update.callback_query
        query.answer()

        user_id = _get_user_id(update)
        user_request = self._user_to_request[user_id]
        if update.callback_query.data == "GO-TIME":
            buttons = [InlineKeyboardButton(
                text=f"""{easy_to_read(value["start"])} - {easy_to_read(value["end"])} | {value["freeSpots"]}""",
                callback_data=value["id"])
                for value in
                self._user_to_data[user_id][user_request.place]]
            grouped_buttons = [buttons[x:x + 2] for x in range(0, len(buttons), 2)]
            grouped_buttons.append([InlineKeyboardButton(text="🔙",
                                                         callback_data="GO-PLACE")])  # adding also the go back to here button

            query.edit_message_text(text="What time do you want to go? Or /cancel",
                                    reply_markup=InlineKeyboardMarkup(
                                        inline_keyboard=grouped_buttons,
                                    )
                                    )
            return TIME

        if user_exist(user_id):
            if update.callback_query.data == "YES":
                query.edit_message_text("Proceeding with the booking!...")

                response = requests.post(f"{backend_url}book",
                                         json=self._user_to_request[user_id].__dict__,
                                         )
                if response.status_code == 200:
                    query.edit_message_text(inspect.cleandoc(f"""Booked at
                                             |  {user_request.place} the {easy_to_read_date(user_request.start)}
                                             |  from: {easy_to_read(user_request.start)}
                                             |  to: {easy_to_read(user_request.end)}
                                             See you next time ;) """))
                else:
                    query.edit_message_text("something went wrong with the booking :(.. Cancelled")
            else:
                query.edit_message_text("Request cancelled :)")
        else:
            query.edit_message_text("I'm sorry, but I don't have enough data to proceed with the booking :(."
                                    " But you can still check the slots")

        self._user_to_data.pop(user_id)
        self._user_to_request.pop(user_id)

        return ConversationHandler.END

    def cancel(self, update: Update, context: CallbackContext):
        query = update.callback_query
        if query:
            query.answer()
            query.edit_message_text("Booking cancelled")
        user_id = _get_user_id(update)
        update.message.reply_text(
            "Booking cancelled. New booking? /book", reply_markup=ReplyKeyboardRemove()
        )
        self._clean_user_data(user_id)
        return ConversationHandler.END

    def _clean_user_data(self, user_id):
        if user_id in self._user_to_data:
            self._user_to_data.pop(user_id)
        if user_id in self._user_to_request:
            self._user_to_request.pop(user_id)

    def go(self):
        logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
        updater = Updater(self._token, use_context=True)

        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('book', self.show_calendar)],
            states={
                CALENDAR: [CallbackQueryHandler(self.manage_calendar)],
                PLACE: [CallbackQueryHandler(self.place, pass_user_data=True)],
                TIME: [CallbackQueryHandler(callback=self.time, pass_user_data=True)],
                CONFIRMATION: [CallbackQueryHandler(callback=self.confirmation, pass_user_data=True)]

            },
            fallbacks=[CommandHandler('cancel', self.cancel)],
        )
        welcome_handler = CommandHandler('start', self.welcome)
        user_data_handler = CommandHandler('profile', self.user_data)

        updater.dispatcher.add_handler(conv_handler)
        updater.dispatcher.add_handler(welcome_handler)
        updater.dispatcher.add_handler(user_data_handler)
        updater.start_polling()

        updater.idle()

    def user_data(self, update: Update, context: CallbackContext):
        user_id = _get_user_id(update)
        request_data = requests.get(
            f"""{backend_url}user/{user_id}""")
        if request_data.status_code == 200:
            update.message.reply_text(request_data.json())
        else:
            update.message.reply_text("Your profile does not exist :(")


if __name__ == '__main__':
    print(f"HELLO, stating communication with {backend_url}")
    dbot = TheBot(token=os.environ.get('TOKEN'))
    dbot.go()
