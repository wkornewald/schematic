from . import sd
from unittest import TestCase

class SchemaTests(TestCase):
    person = sd.Dict({
        'name': sd.String(),
        'age': sd.Int(),
        'age2': sd.Int(optional=True),
        'notes': sd.String(optional=True),
    })
    sample_person = {'name': 'Albert Fuller', 'age': 9}
    sample_person2 = {'name': 'Albert Fuller', 'age': '9'}
    bad_sample_person = {'name': 'Albert Fuller', 'age': None, 'age2': 'hey'}
    bad_sample_person2 = {'name': 'Albert Fuller', 'age': 10, 'foo': 'bar'}

    def test_person(self):
        self.assertEqual(self.person.convert(self.sample_person),
                         self.sample_person)
        self.assertEqual(self.person.convert(self.sample_person2),
                         self.sample_person)

    def test_bad_person(self):
        self.assertRaises(sd.Invalid,
                          lambda: self.person.convert(self.bad_sample_person))
        self.assertRaises(sd.Invalid,
                          lambda: self.person.convert(self.bad_sample_person2))
