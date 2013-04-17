from datetime import datetime, date, time
from pyutils.encoding import force_str, force_unicode
from time import strptime
import re

class Invalid(Exception):
    def __init__(self, path=(), messages=(), children=()):
        if not isinstance(messages, (list, tuple)):
            messages = [messages]
        self.messages = {}
        if messages:
            self.messages[path] = list(messages)
        self.add(children)

    def __str__(self):
        return force_str(unicode(self))

    def __unicode__(self):
        result = []
        for path, messages in self.flattened():
            prefix = path + ': ' if path else ''
            for index, message in enumerate(messages):
                if index == 0:
                    result.append(prefix + message)
                else:
                    result.append(message.rjust(len(prefix)))

        if len(result) == 1:
            return result[0]
        return '\n' + '\n'.join(result)

    def flattened(self):
        return {'.'.join(map(force_unicode, path)): submessages
                for path, submessages in self.messages.items()}

    def add(self, errors):
        if not hasattr(errors, '__iter__'):
            errors = (errors,)

        for error in errors:
            for path, messages in error.messages.items():
                self.messages.setdefault(path, []).extend(messages)

class MaxLength(object):
    def __init__(self, max_length):
        self.max_length = max_length

    def check(self, value, path):
        if len(value) > self.max_length:
            raise Invalid(path, 'Ensure this value has at most %d characters '
                                '(it has %d).' % (self.max_length, len(value)))

class MinValue(object):
    def __init__(self, min_value):
        self.min_value = min_value

    def check(self, value, path):
        if value < self.min_value:
            raise Invalid(path, 'This value must be larger than %s.'
                                % self.min_value)

class MaxValue(object):
    def __init__(self, max_value):
        self.max_value = max_value

    def check(self, value, path):
        if value < self.min_value:
            raise Invalid(path, 'This value must be smaller than %s.'
                                % self.max_value)

class Equals(object):
    def __init__(self, value):
        self.value = value

    def check(self, value, path):
        if value != self.value:
            raise Invalid(path, 'This value must be equal to %s.'
                                % self.value)

class In(object):
    def __init__(self, choice):
        self.choice = choice

    def check(self, value, path):
        if value not in self.choice:
            raise Invalid(path, 'This value must be one of: %s'
                                % ', '.join(map(unicode, self.choice)))

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

class EmailValidator(object):
    def check(self, value, path):
        if not email_re.match(value):
            # Trivial case failed. Try for possible IDN domain-part
            if value and u'@' in value:
                parts = value.split(u'@')
                try:
                    parts[-1] = parts[-1].encode('idna')
                except UnicodeError:
                    raise
                value = u'@'.join(parts)
            if email_re.match(value):
                return
            raise Invalid(path, 'Enter a valid e-mail address.')

class Schema(object):
    default_validators = []

    def __init__(self, null=False, optional=False, validators=None):
        self.null = null
        self.optional = optional
        self.validators = self.default_validators[:]
        if validators:
            self.validators.extend(validators)

    def convert(self, value, path=()):
        if value is None:
            if not self.null:
                raise Invalid(path, 'This value is required.')
            return None
        value = self._convert(value, path)

        errors = []
        for validator in self.validators:
            try:
                validator.check(value, path)
            except Invalid as error:
                errors.append(error)
        if errors:
            raise Invalid(path, children=errors)
        return value

    def _convert(self, value, path=()):
        raise NotImplementedError()

class OneOf(Schema):
    def __init__(self, choice=(), **kwargs):
        self.choice = list(choice)
        super(OneOf, self).__init__(**kwargs)

    def _convert(self, value, path):
        for schema in self.choice:
            if isinstance(schema, (tuple, list)):
                checker, schema = schema
                try:
                    if not checker(value):
                        continue
                except:
                    continue
                return schema.convert(value, path)
            else:
                try:
                    return schema.convert(value, path)
                except Invalid:
                    pass
        raise Invalid(path, "This value doesn't match any acceptable schema.")

class NestedSchema(Schema):
    def __init__(self, schema=None, **kwargs):
        self.schema = schema
        super(NestedSchema, self).__init__(**kwargs)

class Dict(NestedSchema):
    def _convert(self, value, path):
        if not isinstance(value, dict):
            raise Invalid(path, 'This value must be a dict.')

        if self.schema is None:
            return dict(value)

        errors = []
        result = {}
        # We support two modes of operation.
        # a) Only the type of the key and the value are specified. Any keys are accepted.
        #    In this case, self.schema is a tuple.
        # b) The complete set of allowed keys is specified.
        #    In this case self.schema is a dict.
        if isinstance(self.schema, (tuple, list)):
            key_schema, value_schema = self.schema
            for key, value in value.items():
                try:
                    result_key = key_schema.convert(key, path + (key,))
                except Invalid as error:
                    errors.append(error)
                try:
                    result[result_key] = value_schema.convert(value, path + (key,))
                except Invalid as error:
                    errors.append(error)

                if errors:
                    raise Invalid(path, children=errors)
        else:
            seen = set()
            for key, schema in self.schema.items():
                if schema.optional and key not in value:
                    continue

                seen.add(key)
                try:
                    if key not in value:
                        raise Invalid(path + (key,), 'The "%s" entry is missing.'
                                                     % key)
                    result[key] = schema.convert(value[key], path + (key,))
                except Invalid as error:
                    errors.append(error)

            error = None
            non_converted = set(value) - seen
            if non_converted:
                error = Invalid(path, 'Unconverted values: %s' % ', '.join(non_converted))
            if errors:
                if not error:
                    error = Invalid(path)
                error.add(errors)
            if error is not None:
                raise error

        return result

class IterableSchema(NestedSchema):
    _type_error = None
    _type = None

    def _convert(self, value, path):
        if not hasattr(value, '__iter__') or isinstance(value, basestring):
            raise Invalid(path, self._type_error)

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
            if len(value) != len(self.schema):
                error = Invalid(path, 'This value must have %d entries.'
                                      % len(self.schema))
                errors.append(error)
            for index, subvalue in enumerate(value):
                schema = self.schema[index]
                try:
                    result.append(schema.convert(subvalue, path + (index,)))
                except Invalid as error:
                    errors.append(error)
        else:
            for index, subvalue in enumerate(value):
                try:
                    result.append(self.schema.convert(subvalue, path + (index,)))
                except Invalid as error:
                    errors.append(error)

        if errors:
            raise Invalid(path, children=errors)

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
    def _convert(self, value, path):
        if isinstance(value, str):
            value = force_unicode(value)
        return value

class String(Schema):
    # Let's wrap the converter in a list, so it won't become a method.
    _converters = [force_unicode]

    def __init__(self, blank=False, **kwargs):
        super(String, self).__init__(**kwargs)
        self.blank = blank

    def convert(self, value, path=()):
        if value == '':
            if not self.blank:
                raise Invalid(path, 'This value is required.')
            return value
        return super(String, self).convert(value, path)

    def _convert(self, value, path):
        for converter in self._converters:
            value = converter(value)
        return value

class Blob(String):
    _converters = [force_str]

class Number(Schema):
    # Let's wrap the converter in a list, so it won't become a method.
    _converters = []
    _error = None

    def _convert(self, value, path):
        try:
            for converter in self._converters:
                value = converter(value)
            return value
        except ValueError:
            raise Invalid(path, self._error)

class Int(Number):
    _converters = [int]
    _error = 'This value must be an integer.'

class Long(Int):
    _converters = [long]

class Float(Number):
    _converters = [float]
    _error = 'This value must be a number.'

class Bool(Schema):
    def _convert(self, value, path):
        if isinstance(value, basestring):
            return value.lower() not in ('0', 'false')
        return bool(value)

class DateTime(Schema):
    def _convert(self, value, path):
        if isinstance(value, basestring):
            return parse_datetime(value, path)
        if not isinstance(value, datetime):
            raise Invalid(path, 'Please provide a datetime object.')
        return value

class Date(Schema):
    def _convert(self, value, path):
        if isinstance(value, basestring):
            return parse_date(value, path)
        if isinstance(value, datetime):
            return value.date()
        if not isinstance(value, date):
            raise Invalid(path, 'Please provide a date object.')
        return value

class Time(Schema):
    def _convert(self, value, path):
        if isinstance(value, basestring):
            return parse_time(value, path)
        if isinstance(value, datetime):
            return value.time()
        if not isinstance(value, time):
            raise Invalid(path, 'Please provide a time object.')
        return value

class Email(String):
    default_validators = [MaxLength(254), EmailValidator()]

DATETIME_INPUT_FORMATS = (
    # ISO 8601
    '%Y-%m-%dT%H:%M:%S.%f',  # '2006-10-25T14:30:59.123456'
    '%Y-%m-%dT%H:%M:%S',     # '2006-10-25T14:30:59'

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

def parse_datetime(value, path):
    for format in DATETIME_INPUT_FORMATS:
        try:
            return datetime(*strptime(value, format)[:6])
        except ValueError:
            continue
    raise Invalid(path, 'Please enter a valid date/time.')

DATE_INPUT_FORMATS = (
    '%Y-%m-%d', '%m/%d/%Y', '%m/%d/%y',  # '2006-10-25', '10/25/2006', '10/25/06'
    '%d.%m.%Y', '%d.%m.%y',              # '25.10.2006', '25.10.06'
)

def parse_date(value, path):
    for format in DATE_INPUT_FORMATS:
        try:
            return date(*strptime(value, format)[:3])
        except ValueError:
            continue
    raise Invalid(path, 'Please enter a valid date.')

TIME_INPUT_FORMATS = (
    '%H:%M:%S',     # '14:30:59'
    '%H:%M',        # '14:30'
)

def parse_time(value, path):
    for format in TIME_INPUT_FORMATS:
        try:
            return time(*strptime(value, format)[3:6])
        except ValueError:
            continue
    raise Invalid(path, 'Please enter a valid time.')
