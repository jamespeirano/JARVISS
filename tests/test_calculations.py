import unittest
from jarviss.calculations import supply_duration


class DurationTests(unittest.TestCase):
    def test_explicit_daily_rates(self):
        cases = [
            ('I have 12 litres of water for 3 people. Each uses 2 litres per day. How many days will it last?', '2 days.'),
            ('Twelve litres, three people, two litres each per day. How long will it last?', '2 days.'),
            ('We have 9 liters and 3 people using 2 liters each daily. How many days?', '1.5 days.'),
            ('We have 12 litres. Our group of 3 uses 2 litres total per day. How long will it last?', '6 days.'),
            ('We have 12 litres for 3 people using 2 litres per person per day. How long will it last?', '2 days.'),
            ('We have 12 L for 3 of us using 2 litres each per day. How long will it last?', '2 days.'),
            ('We have 12 litres of safe water for a family of 3 using 2 litres each daily. How long will it last?', '2 days.'),
            ('We use 2 cans each daily, for 3 people, and have 12 cans. How long will it last?', '2 days.'),
            ('We have 1 gallon and use 3 gallons total daily. How long will it last?', 'About 0.33 days.'),
            ('We have 0 litres for 3 people using 2 litres each daily. How many days?', '0 days.'),
        ]
        for question, expected in cases:
            with self.subTest(question=question):
                self.assertTrue(supply_duration(question).startswith(expected))

    def test_missing_or_ambiguous_inputs_do_not_invent_usage(self):
        self.assertIsNone(supply_duration('We have 12 litres for 3 people. How long will it last?'))
        self.assertIn('each person or for the whole group', supply_duration('We have 12 litres for 3 people using 2 litres per day. How long will it last?'))
        self.assertIn('How many people', supply_duration('We have 12 litres, using 2 litres each daily. How long will it last?'))
        self.assertIsNone(supply_duration('We have 12 litres and use 2 gallons each daily. How long will it last?'))
        self.assertIsNone(supply_duration('We have 12 litres plus 6 litres and use 2 litres daily. How many days?'))
        self.assertIsNone(supply_duration('We have twelve litres and use one point five litres daily. How long will it last?'))
        self.assertIsNone(supply_duration('We have 10-12 litres and use 2 litres daily. How long will it last?'))

    def test_unsuitable_water_is_not_replaced_with_a_duration(self):
        self.assertIsNone(supply_duration('We have 12 litres of diesel-contaminated water for 3 people using 2 litres each daily. How long will it last if we boil it?'))
        self.assertIsNone(supply_duration('We have 12 litres for 3 people using 2 litres each daily. How long will it last and is it safe to drink?'))

    def test_non_duration_requests_are_not_intercepted(self):
        self.assertIsNone(supply_duration('Where is the nearest running water?'))
        self.assertIsNone(supply_duration('I have 12 litres for 3 people using 2 litres each daily. What should we do first?'))

    def test_invalid_rates_do_not_divide_by_zero(self):
        self.assertIn('greater than zero', supply_duration('We have 12 litres and use 0 litres daily. How long will it last?'))


if __name__ == '__main__':
    unittest.main()
