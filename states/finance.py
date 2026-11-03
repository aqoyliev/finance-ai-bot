from aiogram.dispatcher.filters.state import State, StatesGroup


class FinanceForm(StatesGroup):
    amount = State()  # waiting for the operation amount (typed or quick button)


class TransferForm(StatesGroup):
    amount = State()  # waiting for the transfer amount


class AccountForm(StatesGroup):
    name = State()  # new account: name
    opening = State()  # new account: opening balance (cash/debit)
    limit = State()  # new account: credit limit
    debt = State()  # new account: current credit debt


class AccountEdit(StatesGroup):
    name = State()
    opening = State()  # opening balance, or opening debt for a credit account
    limit = State()


class OperationEdit(StatesGroup):
    amount = State()


class AIDraft(StatesGroup):
    review = State()  # AI drafts are shown; free text / media starts a new analysis
    amount = State()  # typing a corrected amount for the current draft
    date = State()  # typing a corrected date for the current draft


class BudgetForm(StatesGroup):
    amount = State()  # typing the monthly limit of a category
