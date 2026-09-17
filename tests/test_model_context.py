"""Long conversations must leave room for a complete answer."""
import unittest
from unittest.mock import patch

from jarviss.model import LocalModel


class ModelContextTests(unittest.TestCase):
    def setUp(self):
        self.model = LocalModel()
        self.model.context = 4096

    def tokenizer(self, counts):
        values = iter(counts)
        def post(endpoint, payload):
            if endpoint == '/apply-template':
                return {'prompt':'formatted'}
            return {'tokens':[0] * next(values)}
        return post

    def test_uses_token_count_and_keeps_complete_current_sources(self):
        messages = [dict(role='system', content='Sources and saved facts'),
                    dict(role='user', content='Old question'), dict(role='assistant', content='Old answer'),
                    dict(role='user', content='Current question')]
        with patch.object(self.model, '_post', side_effect=self.tokenizer([4056, 1000])):
            self.assertEqual(self.model._fit_messages(messages, 600), [messages[0], messages[-1]])
        self.assertEqual(len(messages), 4)

    def test_leaves_fitting_history_unchanged(self):
        messages = [dict(role='system', content='Sources'), dict(role='user', content='Question')]
        with patch.object(self.model, '_post', side_effect=self.tokenizer([3400])):
            self.assertEqual(self.model._fit_messages(messages, 600), messages)

    def test_long_multilingual_background_does_not_consume_answer_budget(self):
        messages = [dict(role='system', content='Saved situation and complete reference passages'),
                    dict(role='user', content='Current question')]
        with patch.object(self.model, '_post', side_effect=self.tokenizer([4056])):
            with self.assertRaisesRegex(ValueError, 'Shorten your question or saved situation'):
                self.model._fit_messages(messages, 600)


if __name__ == '__main__':
    unittest.main()
