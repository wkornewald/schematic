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

    person_list = sd.List(person)
    sample_person_list = [sample_person, sample_person2]
    bad_sample_person_list = [bad_sample_person, bad_sample_person2]

    int_set = sd.Set(sd.Int())
    tuple_set = sd.Set(sd.Tuple(sd.Int()))

    ordered_tuple = sd.Tuple((sd.Int(), sd.Bool()))

    one_of = sd.OneOf([(lambda x: isinstance(x, dict), person),
                       (lambda x: True, int_set)])

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

    def test_person_list(self):
        self.assertEqual(self.person_list.convert(self.sample_person_list),
                         2 * [self.sample_person])

    def test_bad_person_list(self):
        self.assertRaises(sd.Invalid,
                          lambda: self.person_list.convert(self.bad_sample_person))

    def test_set(self):
        self.assertEqual(self.int_set.convert([1.1, 45.1, 45]),
                         {1, 45})
        self.assertEqual(self.tuple_set.convert([(1.1, 45.1), [1, 45], (2, 45.5)]),
                         {(1, 45), (2, 45)})

    def test_or(self):
        self.assertEqual(self.one_of.convert([1.1, 45.1, 45]),
                         {1, 45})
        self.assertEqual(self.one_of.convert(self.sample_person2),
                         self.sample_person)
        self.assertRaises(sd.Invalid,
                          lambda: self.one_of.convert(self.bad_sample_person))

    def test_ordered_tuple(self):
        self.assertEqual(self.ordered_tuple.convert((1.1, 45.1)),
                         (1, True))
