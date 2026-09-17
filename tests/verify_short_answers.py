"""Small real-model regression set. Review answer accuracy as well as generation."""
import json
import os
import tempfile
from pathlib import Path

CASES = [
    ('per_person', 'I have 12 litres of water for 3 people. Each uses 2 litres per day. How many days will it last? Answer briefly.', '2 days: 12 / (3 * 2)'),
    ('whole_group', 'We have 12 litres of water. Our group of 3 uses 2 litres total per day. How long will it last? Answer briefly.', '6 days: 12 / 2; do not multiply total group usage'),
    ('word_numbers', 'Twelve litres, three people, two litres each per day. How long will it last? Answer briefly.', '2 days'),
    ('fraction', 'We have 9 litres and 3 people using 2 litres each daily. How many days? Answer briefly.', '1.5 days; do not round up to 2 full days'),
    ('missing_usage', 'We have 12 litres for 3 people. How long will it last?', 'Ask daily usage; do not invent a ration'),
    ('short_explanation', 'In one sentence explain why wet clothes feel colder in wind.', 'One short sentence about faster heat loss, including evaporation'),
]


def main():
    root = Path(__file__).resolve().parent.parent
    with tempfile.TemporaryDirectory(prefix='jarviss-answers-') as data:
        os.environ['JARVISS_DATA'] = data
        from jarviss.assistant import messages
        from jarviss.calculations import supply_duration
        from jarviss.model import LocalModel
        from jarviss.setup import model_catalog
        filename = os.environ.get('JARVISS_TEST_MODEL', 'Huihui-gemma-4-E2B-it-abliterated.Q4_K_M.gguf')
        model_path = root / 'models' / filename
        context = next(row['context'] for row in model_catalog() if row['filename'] == filename)
        result = {'model': filename, 'review': 'Successful generation is not an accuracy pass.', 'cases': []}
        target = Path(os.environ.get('JARVISS_TEST_RESULTS', root / 'local-data/short-answer-results.json'))
        model = LocalModel()
        try:
            model.start(model_path, context=context)
            for identifier, question, expected in CASES:
                calculation = supply_duration(question)
                answer = calculation or model.chat(messages({}, [], question), max_tokens=140)
                row = {'id': identifier, 'question': question, 'expected': expected, 'answer': answer, 'source': 'calculation' if calculation else 'model'}
                result['cases'].append(row)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(json.dumps(result, indent=2) + '\n')
                print(json.dumps(row), flush=True)
        finally:
            model.close()


if __name__ == '__main__':
    main()
