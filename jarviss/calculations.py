"""Supply-duration arithmetic for explicit amounts and daily rates."""
import re
from decimal import Decimal

WORDS = 'zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty'.split()
AMOUNT = re.compile(r'(?<![\w.])(-?\d+(?:\.\d+)?)\s*(lit(?:er|re)s?|l|gallons?|bottles?|cans?|kilograms?|kg|grams?|g|pounds?|lb)\b')


def supply_duration(question):
    text = question.lower()
    if not re.search(r'\b(?:how long|how many days|will .+ last)\b', text):
        return None
    if re.search(r'\b(?:contaminat\w*|diesel|fuel|bleach|boil\w*|filter\w*|purif\w*)\b|\b(?:is|are)\b.{0,40}\bsafe\b|\b(?:can|should) (?:i|we) drink\b', text):
        return None  # A suitability or treatment question needs the reference-guided answer.
    if re.search(r'\b(?:point|half|quarter|dozen|hundred|thousand|less than|more than|up to|at least)\b|\d\s*[-–]\s*\d', text):
        return None  # Do not extract a partial number from a range or compound quantity.
    text = re.sub(r'\b(' + '|'.join(WORDS) + r')\b', lambda m: str(WORDS.index(m[0])), text)
    amounts = list(AMOUNT.finditer(text))
    if len(amounts) != 2:
        return None
    if any(len(amount[1]) > 16 for amount in amounts):
        return None
    rates = []
    for index, amount in enumerate(amounts):
        end = amounts[index+1].start() if index+1 < len(amounts) else len(text)
        tail = re.split(r'[.!?;]', text[amount.end():end], maxsplit=1)[0]
        if re.search(r'\b(?:per day|a day|each day|daily)\b|/day\b', tail):
            rates.append((index, tail))
    if len(rates) != 1:
        return None
    index, tail = rates[0]
    rate, stock = amounts[index], amounts[1-index]
    def unit(value):
        value = value.rstrip('s')
        return {'liter':'litre', 'l':'litre', 'kg':'kilogram', 'g':'gram', 'lb':'pound'}.get(value, value)
    if unit(rate[2]) != unit(stock[2]):
        return None
    available, daily = Decimal(stock[1]), Decimal(rate[1])
    if available < 0 or daily <= 0:
        return 'Use a non-negative supply amount and daily use greater than zero.'
    start = amounts[index-1].end() if index else 0
    prefix = re.split(r'[.!?;]', text[start:rate.start()])[-1]
    usage = prefix + ' ' + tail
    per_person = bool(re.search(r'\b(?:each(?! day)|per person|per adult|per child)\b', usage))
    group_total = bool(re.search(r'\b(?:total|combined|whole group|altogether|between us|all of us)\b', usage))
    people = re.findall(r'\b(\d+)\s+(?:people|persons|adults|children|of us)\b|\b(?:group|family|party) of (\d+)\b', text)
    if per_person and group_total:
        return 'Is that daily use for each person or for the whole group?'
    if per_person:
        if len(people) != 1:
            return 'How many people share this supply?'
        count_text = next(value for value in people[0] if value)
        if len(count_text) > 12: return None
        count = Decimal(count_text)
        if count <= 0:
            return 'How many people share this supply?'
    elif people and not group_total:
        return 'Is that daily use for each person or for the whole group?'
    else:
        count = Decimal(1)
    total = daily * count
    days = available / total
    def number(value, places=2):
        return format(value, f'.{places}f').rstrip('0').rstrip('.')
    approximate = 'About ' if days != Decimal(format(days, '.2f')) else ''
    # Small rations (5 g of salt a day) must not display as "÷ (0 per day)".
    usage_calculation = f'{number(count)} × {number(daily, 6)}' if per_person else number(daily, 6)
    return f'{approximate}{number(days)} days. {number(available)} ÷ ({usage_calculation} per day) = {number(days)} days.'
