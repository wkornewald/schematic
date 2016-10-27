from . import sd
from typing import NamedTuple, List, Union, Optional
from unittest import TestCase

Person = NamedTuple('Person', [
    ('name', str),
    ('age', int),
])
person_tuple_schema = sd.from_typing(Person, ignore_rest=True)
People = NamedTuple('People', [
    ('count', int),
    ('people', List[Person]),
])
people_schema = sd.from_typing(People, ignore_rest=True)
people_schema_strict = sd.from_typing(People)

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

    def test_empty_string(self):
        self.assertEqual(None, sd.String(null=True).convert(''))
        self.assertEqual('', sd.String(blank=True).convert(''))

    def test_person(self):
        self.assertEqual(self.person.convert(self.sample_person),
                         self.sample_person)
        self.assertEqual(self.person.convert(self.sample_person2),
                         self.sample_person)
        self.assertEqual(person_tuple_schema.convert(self.sample_person),
                         Person(name='Albert Fuller', age=9))

    def test_bad_person(self):
        self.assertRaises(sd.Invalid,
                          lambda: self.person.convert(self.bad_sample_person))
        self.assertRaises(sd.Invalid,
                          lambda: self.person.convert(self.bad_sample_person2))
        self.assertEqual(person_tuple_schema.convert(self.bad_sample_person2),
                         Person(name='Albert Fuller', age=10))

    def test_person_list(self):
        self.assertEqual(self.person_list.convert(self.sample_person_list),
                         2 * [self.sample_person])
        self.assertEqual(
            people_schema.convert({'count': 2, 'people': self.sample_person_list}),
            People(count=2, people=2 * [Person(name='Albert Fuller', age=9)]))

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

        union = sd.from_typing(Union[int, str])
        self.assertIsInstance(union, sd.OneOf)
        self.assertEqual({u.__class__ for u in union.choice}, {sd.Int, sd.String})
        optional = sd.from_typing(Optional[int])
        self.assertIsInstance(optional, sd.Int)
        self.assertTrue(optional.null)

    def test_ordered_tuple(self):
        self.assertEqual(self.ordered_tuple.convert((1.1, 45.1)),
                         (1, True))

    def test_email(self):
        self.assertEqual(None, sd.Email(null=True).convert(''))
        self.assertEqual(None, sd.Email(null=True).convert(None))
        self.assertEqual('', sd.Email(blank=True).convert(''))
        self.assertEqual('', sd.Email(null=True, blank=True).convert(''))
        self.assertEqual(None, sd.Email(null=True, blank=True).convert(None))
        self.assertRaises(sd.Invalid, lambda: sd.Email(blank=True).convert(None))

    def test_partial_dict(self):
        value = {'a': 1, 'b': 1}
        schema = sd.Dict({'a': sd.Int()}, ignore_rest=True)
        self.assertEqual({k: value[k] for k in schema.schema}, schema.convert(value))

    def test_partial_list(self):
        value = [1, 'a', 2]
        schema = sd.List([sd.Int(), sd.String()], ignore_rest=True)
        self.assertEqual(value[:len(schema.schema)], schema.convert(value))

    def test_default(self):
        schema = sd.Dict({'a': sd.Int(default=lambda: 2)})
        value = {'a': 1}
        self.assertEqual(value, schema.convert(value))
        self.assertEqual({'a': 2}, schema.convert({}))

    def test_default_for_invalid(self):
        schema = sd.Dict({'a': sd.Int(default=lambda: 2, use_default_for_invalid=True)})
        self.assertEqual({'a': 2}, schema.convert({'a': 'gaga'}))
