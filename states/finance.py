from aiogram.dispatcher.filters.state import State, StatesGroup


class FinanceForm(StatesGroup):
    amount = State()  # waiting for the operation amount (typed or quick button)
