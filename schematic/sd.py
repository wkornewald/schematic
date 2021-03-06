from datetime import datetime, date, time
import re
import typing

try:
    from pytz import utc as UTC
except ImportError:
    UTC = None

_UNDEFINED = object()

class Invalid(Exception):
    def __init__(self, raisor, path=(), message='', children=(), bad_value=_UNDEFINED):
        self.raisor = raisor
        self.message = message
        if not isinstance(children, (list, tuple)):
            children = [children]
        self.children = {}
        if message:
            self.children[path] = [self]
        self.add(children)
        self.bad_value = bad_value

    def __repr__(self):
        return str(self)

    def __str__(self):
        result = []
        for path, children in self.flattened().items():
            prefix = path + ': ' if path else ''
            index = 0
            for child in children:
                if not child.message:
                    continue
                if index == 0:
                    result.append(prefix + child.message)
                else:
                    result.append(child.message.rjust(len(prefix)))
                    index += 1

        if self.bad_value is not _UNDEFINED:
            result.append(f'\nOriginal value: {self.bad_value!r}')
        if len(result) == 1:
            return result[0]
        return '\n' + '\n'.join(result)

    def flattened(self):
        return {'.'.join(map(str, path)): children
                for path, children in self.children.items()}

    def add(self, errors):
        if not hasattr(errors, '__iter__'):
            errors = (errors,)

        for error in errors:
            for path, children in error.children.items():
                self.children.setdefault(path, []).extend(children)

    def filter(self, filter_func):
        values = []
        for value in self.children.values():
            values.extend(value)
        return [v for v in values if filter_func(v)]

class MinLengthError(Invalid):
    pass

class MinLength(object):
    def __init__(self, min_length):
        self.min_length = min_length

    def check(self, value, path):
        min_length = self.get_value()
        if len(value) < min_length:
            raise MinLengthError(self, path,
                                 f'Ensure this value has at most {min_length} entries '
                                 f'(it has {len(value)}).',
                                 bad_value=value)

    def get_value(self):
        min_length = self.min_length
        if callable(min_length):
            min_length = min_length()
        return min_length

class MaxLengthError(Invalid):
    pass

class MaxLength(object):
    def __init__(self, max_length):
        self.max_length = max_length

    def check(self, value, path):
        max_length = self.get_value()
        if len(value) > max_length:
            raise MaxLengthError(self, path,
                                 f'Ensure this value has at most {max_length} entries '
                                 f'(it has {len(value)}).',
                                 bad_value=value)

    def get_value(self):
        max_length = self.max_length
        if callable(max_length):
            max_length = max_length()
        return max_length

class MinValueError(Invalid):
    pass

class MinValue(object):
    def __init__(self, min_value):
        self.min_value = min_value

    def check(self, value, path):
        min_value = self.get_value()
        if value < min_value:
            raise MinValueError(self, path,
                                f'This value must be larger than {min_value}.',
                                bad_value=value)

    def get_value(self):
        min_value = self.min_value
        if callable(min_value):
            min_value = min_value()
        return min_value

class MaxValueError(Invalid):
    pass

class MaxValue(object):
    def __init__(self, max_value):
        self.max_value = max_value

    def check(self, value, path):
        max_value = self.get_value()
        if value > max_value:
            raise MaxValueError(self, path,
                                f'This value must be smaller than {max_value}.',
                                bad_value=value)

    def get_value(self):
        max_value = self.max_value
        if callable(max_value):
            max_value = max_value()
        return max_value

class EqualsError(Invalid):
    pass

class Equals(object):
    def __init__(self, value):
        self.value = value

    def check(self, value, path):
        _value = self.get_value()
        if value != _value:
            raise EqualsError(self, path,
                              f'This value must be equal to {_value!r}.',
                              bad_value=value)

    def get_value(self):
        value = self.value
        if callable(value):
            return value()
        return value

class InError(Invalid):
    pass

class In(object):
    def __init__(self, choice):
        self.choice = list(choice)

    def check(self, value, path):
        if value not in self.choice:
            allowed = ', '.join(map(repr, self.choice))
            raise InError(self, path, f'This value must be one of: {allowed}',
                          bad_value=value)

    def get_value(self):
        return self.choice

email_re = re.compile(
    # dot-atom
    r"(^[-!#$%&'*+/=?^_`{}|~0-9A-Z]+(\.[-!#$%&'*+/=?^_`{}|~0-9A-Z]+)*"
    # quoted-string, see also http://tools.ietf.org/html/rfc2822#section-3.2.5
    r'|^"([\001-\010\013\014\016-\037!#-\[\]-\177]|\\[\001-\011\013\014\016-\177])*"'
    # domain
    r')@((?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?$)'
    # literal form, ipv4 address (SMTP 4.1.3)
    r'|\[(25[0-5]|2[0-4]\d|[0-1]?\d?\d)(\.(25[0-5]|2[0-4]\d|[0-1]?\d?\d)){3}\]$',
    re.IGNORECASE)

class EmailValidatorError(Invalid):
    pass

class EmailValidator(object):
    def check(self, value, path):
        orig_value = value
        if not email_re.match(value):
            # Trivial case failed. Try for possible IDN domain-part
            if value and '@' in value:
                parts = value.split('@')
                try:
                    parts[-1] = parts[-1].encode('idna')
                except UnicodeError:
                    raise
                value = '@'.join(parts)
            if email_re.match(value):
                return
            raise EmailValidatorError(self, path, 'Enter a valid e-mail address.',
                                      bad_value=orig_value)

class Schema:
    default_validators = []

    def __init__(self, null=False, optional=False, validators=None, default=_UNDEFINED,
                 use_default_for_invalid=False):
        self.null = null
        self.optional = optional
        self.default = default
        self.use_default_for_invalid = use_default_for_invalid
        self.validators = self.default_validators[:]
        if validators:
            self.validators.extend(validators)

    def has_default(self):
        return self.default is not _UNDEFINED

    def get_default(self, path):
        if self.default is _UNDEFINED:
            raise Invalid(self, path, 'This value is required.')
        if callable(self.default):
            return self.default()
        return self.default

    def convert(self, value, path=(), **kwargs):
        # Forms can only represent empty strings, but not None. Convert empty strings.
        if value == '':
            value = None

        if value is None:
            if not self.null:
                if self.use_default_for_invalid:
                    return self.get_default(path)
                raise Invalid(self, path, 'This value is required.')
            return None
        try:
            value = self._convert(value, path, **kwargs)
        except Invalid:
            if self.use_default_for_invalid:
                return self.get_default(path)
            raise

        errors = []
        for validator in self.validators:
            try:
                validator.check(value, path)
            except Invalid as error:
                if self.use_default_for_invalid:
                    return self.get_default(path)
                errors.append(error)
        if errors:
            raise Invalid(self, path, children=errors, bad_value=value)
        return value

    def _convert(self, value, path=(), **kwargs):
        raise NotImplementedError()

    def get_validators(self, validator_type):
        return [v for v in self.validators if isinstance(v, validator_type)]

class OneOf(Schema):
    def __init__(self, choice=(), **kwargs):
        self.choice = list(choice)
        super().__init__(**kwargs)

    def _convert(self, value, path, **kwargs):
        for schema in self.choice:
            if isinstance(schema, (tuple, list)):
                checker, schema = schema
                try:
                    if not checker(value):
                        continue
                except:
                    continue
                return schema.convert(value, path, **kwargs)
            else:
                try:
                    return schema.convert(value, path, **kwargs)
                except Invalid:
                    pass
        raise Invalid(self, path, "This value doesn't match any acceptable schema.", bad_value=value)

class NestedSchema(Schema):
    def __init__(self, schema=None, ignore_rest=False, **kwargs):
        self.schema = schema
        self.ignore_rest = ignore_rest
        super().__init__(**kwargs)

class MissingEntry(Invalid):
    pass

class UnconvertedValues(Invalid):
    pass

class Dict(NestedSchema):
    def _convert(self, value, path, **kwargs):
        if not isinstance(value, dict):
            raise Invalid(self, path, 'This value must be a dict.', bad_value=value)

        if self.schema is None:
            return dict(value)

        errors = []
        result = {}
        # We support two modes of operation.
        # a) Only the type of the key and the value are specified. Any keys are accepted.
        #    In this case, self.schema is a tuple.
        # b) The complete set of allowed keys is specified (or incomplete if ignore_rest).
        #    In this case self.schema is a dict.
        if isinstance(self.schema, (tuple, list)):
            key_schema, value_schema = self.schema
            for key, val in value.items():
                try:
                    result_key = key_schema.convert(key, path + (key,), **kwargs)
                except Invalid as error:
                    errors.append(error)
                try:
                    result[result_key] = value_schema.convert(val, path + (key,), **kwargs)
                except Invalid as error:
                    errors.append(error)

                if errors:
                    raise Invalid(self, path, children=errors, bad_value=value)
        else:
            seen = set()
            for key, schema in self.schema.items():
                try:
                    if not isinstance(schema, Schema):
                        seen.add(key)
                        if key not in value or schema != value[key]:
                            raise Invalid(self, path + (key,),
                                          f'This value must be equal to {schema!r}.')
                        result[key] = value[key]
                        continue
                    elif schema.optional and key not in value:
                        continue

                    seen.add(key)

                    if key not in value:
                        if schema.has_default():
                            result[key] = schema.get_default(path + (key,))
                            continue
                        raise MissingEntry(self, path + (key,),
                                           f'The {key!r} entry is missing.')
                    result[key] = schema.convert(value[key], path + (key,), **kwargs)
                except Invalid as error:
                    errors.append(error)

            error = None
            if not self.ignore_rest:
                non_converted = set(value) - seen
                if non_converted:
                    error = UnconvertedValues(self, path,
                        f"Unconverted values: {', '.join(non_converted)}",
                        bad_value=value)
            if errors:
                if not error:
                    error = Invalid(self, path, bad_value=value)
                error.add(errors)
            if error is not None:
                raise error

        return result

class IterableSchema(NestedSchema):
    _type_error = None
    _type = None

    def _convert(self, value, path, **kwargs):
        if not hasattr(value, '__iter__') or isinstance(value, str):
            raise Invalid(self, path, self._type_error, bad_value=value)

        if self.schema is None:
            return self._type(value)

        errors = []
        result = []

        # We support two modes of operation.
        # a) The schema is an ordered list of entries. Each entry must match a certain
        #    schema and the length of the value is fixed.
        #    In this case, self.schema is a tuple.
        # b) All entries have the same schema and the length of the value doesn't matter.
        #    In this case self.schema is a schema instance.
        if isinstance(self.schema, (tuple, list)):
            check_value = value[:len(self.schema)] if self.ignore_rest else value
            if len(check_value) != len(self.schema):
                error = Invalid(self, path,
                                f'This value must have {len(self.schema)} entries.',
                                bad_value=value)
                errors.append(error)
            else:
                for index, subvalue in enumerate(check_value):
                    schema = self.schema[index]
                    try:
                        result.append(schema.convert(subvalue, path + (index,), **kwargs))
                    except Invalid as error:
                        errors.append(error)
        else:
            for index, subvalue in enumerate(value):
                try:
                    result.append(self.schema.convert(subvalue, path + (index,), **kwargs))
                except Invalid as error:
                    errors.append(error)

        if errors:
            raise Invalid(self, path, children=errors, bad_value=value)

        return self._type(result)

class List(IterableSchema):
    _type_error = 'This value must be a list.'
    _type = list

class Tuple(IterableSchema):
    _type_error = 'This value must be a tuple.'
    _type = tuple

class Set(IterableSchema):
    _type_error = 'This value must be a set.'
    _type = set

class Generic(Schema):
    def _convert(self, value, path, **kwargs):
        if not isinstance(value, str):
            value = value.decode('utf-8')
        return value

class String(Schema):
    # Let's wrap the converter in a list, so it won't become a method.
    _converters = [(lambda x: x if isinstance(x, str) else (bytes(x).decode('utf-8')))]

    def __init__(self, blank=False, strip_whitespace=True, **kwargs):
        super().__init__(**kwargs)
        self.blank = blank
        self.strip_whitespace = strip_whitespace

    def convert(self, value, path=(), **kwargs):
        # Check for blank
        if self.strip_whitespace and isinstance(value, str) and value:
            value = value.strip()
        if value == '':
            if self.blank:
                return value
            if self.null:
                return None
            raise Invalid(self, path, 'This value is required.')
        return super().convert(value, path, **kwargs)

    def _convert(self, value, path, **kwargs):
        for converter in self._converters:
            value = converter(value)
        return value

class Blob(String):
    _converters = [(lambda x: x.encode('utf-8') if isinstance(x, str) else bytes(x))]

class Number(Schema):
    # Let's wrap the converter in a list, so it won't become a method.
    _converters = []
    _error = None

    def _convert(self, value, path, **kwargs):
        try:
            for converter in self._converters:
                value = converter(value)
            return value
        except (ValueError, TypeError) as e:
            raise Invalid(self, path, self._error)

class Int(Number):
    _converters = [int]
    _error = 'This value must be an integer.'

class Float(Number):
    _converters = [float]
    _error = 'This value must be a number.'

class Bool(Schema):
    def _convert(self, value, path, **kwargs):
        if isinstance(value, str):
            return value.lower() not in ('0', 'false')
        return bool(value)

class DateTime(Schema):
    def __init__(self, timezone_aware=True, **kwargs):
        self.timezone_aware = timezone_aware
        super().__init__(**kwargs)

    def _convert(self, value, path, **kwargs):
        if isinstance(value, str):
            return parse_datetime(self, value, path, self.timezone_aware)
        if not isinstance(value, datetime):
            raise Invalid(self, path, 'Please provide a datetime object.')
        return value

class Date(Schema):
    def _convert(self, value, path, **kwargs):
        if isinstance(value, str):
            return parse_date(self, value, path)
        if isinstance(value, datetime):
            return value.date()
        if not isinstance(value, date):
            raise Invalid(self, path, 'Please provide a date object.')
        return value

class Time(Schema):
    def _convert(self, value, path, **kwargs):
        if isinstance(value, str):
            return parse_time(self, value, path)
        if isinstance(value, datetime):
            return value.time()
        if not isinstance(value, time):
            raise Invalid(self, path, 'Please provide a time object.')
        return value

class Email(String):
    default_validators = [MaxLength(254), EmailValidator()]

    def _convert(self, value, path, **kwargs):
        return value.lower()

DATETIME_INPUT_FORMATS = (
    # ISO 8601
    '%Y-%m-%dT%H:%M:%S.%fZ',      # '2006-10-25T14:30:59.123456Z'
    '%Y-%m-%dT%H:%M:%S.%f',       # '2006-10-25T14:30:59.123456'
    '%Y-%m-%dT%H:%M:%S',          # '2006-10-25T14:30:59'
    '%Y-%m-%dT%H:%M:%S.%f+00:00', # '2006-10-25T14:30:59.123456+00:00'
    '%Y-%m-%dT%H:%M:%S+00:00',    # '2006-10-25T14:30:59+00:00'
    # Broken
    '%Y-%m-%dT%I:%M:%S.%f %pZ', # '2006-10-25T2:30:59.123456 PMZ'

    # Human
    '%Y-%m-%d %H:%M:%S',     # '2006-10-25 14:30:59'
    '%Y-%m-%d %H:%M',        # '2006-10-25 14:30'
    '%m/%d/%Y %H:%M:%S',     # '10/25/2006 14:30:59'
    '%m/%d/%Y %H:%M',        # '10/25/2006 14:30'
    '%m/%d/%y %H:%M:%S',     # '10/25/06 14:30:59'
    '%m/%d/%y %H:%M',        # '10/25/06 14:30'
    '%d.%m.%Y %H:%M:%S',     # '25.10.2006 14:30:59'
    '%d.%m.%Y %H:%M',        # '25.10.2006 14:30'
)

def parse_datetime(schema, value, path, timezone_aware=True):
    for spec in DATETIME_INPUT_FORMATS:
        try:
            _date = datetime.strptime(value, spec)
            if timezone_aware:
                _date = _date.replace(tzinfo=UTC)
            return _date
        except ValueError:
            continue
    raise Invalid(schema, path, 'Please enter a valid date/time.', bad_value=value)

DATE_INPUT_FORMATS = (
    '%Y-%m-%d', '%m/%d/%Y', '%m/%d/%y',  # '2006-10-25', '10/25/2006', '10/25/06'
    '%d.%m.%Y', '%d.%m.%y',              # '25.10.2006', '25.10.06'
)

def parse_date(schema, value, path):
    for spec in DATE_INPUT_FORMATS:
        try:
            return datetime.strptime(value, spec).date()
        except ValueError:
            continue
    raise Invalid(schema, path, 'Please enter a valid date.', bad_value=value)

TIME_INPUT_FORMATS = (
    '%H:%M:%S',     # '14:30:59'
    '%H:%M',        # '14:30'
)

def parse_time(schema, value, path):
    for spec in TIME_INPUT_FORMATS:
        try:
            return datetime.strptime(value, spec).time()
        except ValueError:
            continue
    raise Invalid(schema, path, 'Please enter a valid time.', bad_value=value)

FIELD_TYPES_MAPPING = {
    bool: Bool,
    date: Date,
    datetime: DateTime,
    float: Float,
    int: Int,
    str: lambda *args, **kwargs: String(*args, blank=True, **kwargs),
    time: Time,
}

def from_typing(kind, ignore_rest=False, **kwargs):
    if kind.__class__ is typing.Union.__class__:
        union = set(kind.__args__)
        if type(None) in union:
            kwargs['null'] = True
            union -= {type(None)}
        if len(union) == 1:
            return from_typing(list(union)[0], ignore_rest, **kwargs)
        return OneOf([from_typing(f, ignore_rest) for f in union], **kwargs)
    if issubclass(kind, tuple) and hasattr(kind, '_field_types'):
        return NamedTuple(kind, ignore_rest=ignore_rest, **kwargs)
    if issubclass(kind, typing.Dict):
        return Dict([from_typing(f, ignore_rest) for f in kind.__args__],
                    ignore_rest=ignore_rest)
    if issubclass(kind, typing.List):
        return List(from_typing(kind.__args__[0], ignore_rest), **kwargs)
    if issubclass(kind, typing.Tuple):
        # TODO: List and Dict may have to be adjusted for the two modes too!
        kind_args = [f for f in kind.__args__ if f is not Ellipsis]
        if len(kind_args) > 1:
            return Tuple([from_typing(f, ignore_rest) for f in kind_args],
                         **kwargs)
        return Tuple(from_typing(kind_args[0], ignore_rest), **kwargs)
    return FIELD_TYPES_MAPPING[kind](**kwargs)

class NamedTuple(Dict):
    """Schema for a typing.NamedTuple that contains type annotations."""

    def __init__(self, named_tuple, **kwargs):
        self.named_tuple = named_tuple
        super().__init__({name: from_typing(kind, kwargs.get('ignore_rest', False))
                          for name, kind in named_tuple._field_types.items()},
                         **kwargs)

    def _convert(self, value, path, named_tuple_to_dict=False, **kwargs):
        orig = value
        if isinstance(value, self.named_tuple):
            value = value._asdict()
        try:
            result_dict = super()._convert(value, path,
                                           named_tuple_to_dict=named_tuple_to_dict, **kwargs)
        except Invalid as e:
            e.bad_value = orig
            raise e
        if named_tuple_to_dict:
            return result_dict
        return self.named_tuple(**result_dict)

    def to_dict(self, value):
        assert isinstance(value, self.named_tuple)
        return self.convert(value, named_tuple_to_dict=True)
