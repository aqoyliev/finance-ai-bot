"""Starter accounts and categories, created once in the language the user picks first.

Names become ordinary user data after seeding: changing the language later does not rename them.
"""

# (name, kind, currency)
DEFAULT_ACCOUNTS = {
    "en": [("Cash", "cash", "UZS"), ("Cash (USD)", "cash", "USD"), ("UOB", "debit", "UZS"),
           ("Infinbank", "debit", "UZS"), ("Hamkorbank", "debit", "UZS"), ("Credit card", "credit", "UZS")],
    "ru": [("Наличные", "cash", "UZS"), ("Наличные (USD)", "cash", "USD"), ("UOB", "debit", "UZS"),
           ("Infinbank", "debit", "UZS"), ("Hamkorbank", "debit", "UZS"), ("Кредитная карта", "credit", "UZS")],
    "uz": [("Naqd pul", "cash", "UZS"), ("Naqd pul (USD)", "cash", "USD"), ("UOB", "debit", "UZS"),
           ("Infinbank", "debit", "UZS"), ("Hamkorbank", "debit", "UZS"), ("Kredit karta", "credit", "UZS")],
}

DEFAULT_CATEGORIES = {
    "en": {
        "Small expenses": ["Coffee", "Soda and water", "Sweets", "Snacks", "Light meals", "Other"],
        "Home and household": ["Meat", "Groceries for home", "Household chemicals", "Household purchases"],
        "Family": ["Family needs", "Clothing", "Personal expenses"],
        "Children": ["Food", "Clothing", "Toys", "School and clubs", "Medicine"],
        "Utilities": ["Rent", "Electricity", "Gas", "Water", "Wi-Fi", "Phone"],
        "Transport": ["Fuel", "Taxi", "Car maintenance", "Parking"],
        "Health": ["Pharmacy", "Doctor", "Checkups"],
        "Other": ["Gifts", "Entertainment", "Miscellaneous"],
    },
    "ru": {
        "Мелкие расходы": ["Кофе", "Газировка и вода", "Сладости", "Снеки", "Перекус", "Другое"],
        "Дом и хозяйство": ["Мясо", "Продукты для дома", "Бытовая химия", "Покупки для дома"],
        "Семья": ["Нужды семьи", "Одежда", "Личные расходы"],
        "Дети": ["Питание", "Одежда", "Игрушки", "Школа и кружки", "Лекарства"],
        "Коммунальные услуги": ["Аренда", "Электричество", "Газ", "Вода", "Wi-Fi", "Телефон"],
        "Транспорт": ["Топливо", "Такси", "Обслуживание авто", "Парковка"],
        "Здоровье": ["Аптека", "Врач", "Обследования"],
        "Прочее": ["Подарки", "Развлечения", "Разное"],
    },
    "uz": {
        "Mayda xarajatlar": ["Qahva", "Gazli ichimlik va suv", "Shirinliklar", "Gazaklar", "Yengil ovqat",
                             "Boshqa"],
        "Uy-ro'zg'or": ["Go'sht", "Uy uchun oziq-ovqat", "Maishiy kimyo", "Uy uchun xaridlar"],
        "Oila": ["Oila ehtiyojlari", "Kiyim-kechak", "Shaxsiy xarajatlar"],
        "Bolalar": ["Ovqat", "Kiyim-kechak", "O'yinchoqlar", "Maktab va to'garaklar", "Dori-darmon"],
        "Kommunal to'lovlar": ["Ijara", "Elektr", "Gaz", "Suv", "Wi-Fi", "Telefon"],
        "Transport": ["Yoqilg'i", "Taksi", "Avtomobilga xizmat", "Avtoturargoh"],
        "Salomatlik": ["Dorixona", "Shifokor", "Tibbiy ko'rik"],
        "Boshqa": ["Sovg'alar", "Ko'ngilochar", "Turli xil"],
    },
}

INCOME_CATEGORIES = {
    "en": ["Salary", "Extra income", "Transfer from another person", "Debt repayment", "Other income"],
    "ru": ["Зарплата", "Дополнительный доход", "Перевод от другого человека", "Возврат долга", "Прочий доход"],
    "uz": ["Maosh", "Qo'shimcha daromad", "Boshqa odamdan o'tkazma", "Qarz qaytarilishi", "Boshqa daromad"],
}
