from aiogram.dispatcher.filters.state import State, StatesGroup


class AIDraft(StatesGroup):
    account = State()  # AI operations wait for the payment method; free text / media starts a new analysis
