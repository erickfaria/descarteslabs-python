from ..core import _type_params_issubclass
from .. import Proxytype, GenericProxytype


# NOTE: we test with non-Proxytype classes for this first test to be a little more hermetic,
# since the GenericProxytypeMetaclass messes around with `isinstance` (to recursively call `_type_params_issubclass`)


class Alive(object):
    pass


class Animal(Alive):
    pass


class Bear(Animal):
    pass


class Plant(Alive):
    pass


class Spruce(Plant):
    pass


class TestTypeParamsIssubclass(object):
    def test_base_case(self):
        assert _type_params_issubclass(Bear, Animal)
        assert _type_params_issubclass(Bear, Alive)
        assert _type_params_issubclass(Bear, Bear)

        assert not _type_params_issubclass(Bear, Plant)
        assert not _type_params_issubclass(Bear, Spruce)
        assert not _type_params_issubclass(Plant, Spruce)
        assert not _type_params_issubclass(Bear, int)

        assert not _type_params_issubclass(Bear, (Animal,))
        assert not _type_params_issubclass(Bear, {"x": Animal})
        assert not _type_params_issubclass((Bear,), {"x": Animal})

    def test_tuples(self):
        assert _type_params_issubclass(tuple(), tuple())
        assert _type_params_issubclass((Bear,), (Animal,))
        assert _type_params_issubclass((Bear, Spruce), (Animal, Plant))

        assert not _type_params_issubclass((Bear, Spruce), (Animal, Animal))
        assert not _type_params_issubclass((int, Alive), (Plant, Animal))
        assert not _type_params_issubclass((Bear, Spruce), (Animal,))
        assert not _type_params_issubclass((Bear,), (Animal, Plant))

    def test_dicts(self):
        assert _type_params_issubclass({}, {})
        assert _type_params_issubclass({"x": Spruce}, {"x": Plant})
        assert _type_params_issubclass(
            {"x": Spruce, "y": Bear}, {"x": Plant, "y": Bear}
        )

        assert not _type_params_issubclass({}, {"x": Plant})
        assert not _type_params_issubclass({"foo": Spruce}, {"bar": Plant})
        assert not _type_params_issubclass({"x": Spruce}, {"x": Animal})
        assert not _type_params_issubclass(
            {"x": Spruce, "y": Bear}, {"x": Plant, "y": Plant}
        )

    def test_nested(self):
        assert _type_params_issubclass({"x": tuple()}, {"x": tuple()})
        assert _type_params_issubclass(({},), ({},))
        assert _type_params_issubclass(
            ({"x": Bear, "y": Plant},), ({"x": Bear, "y": Alive},)
        )
        assert _type_params_issubclass(
            ({"x": Bear, "y": Plant}, Spruce), ({"x": Bear, "y": Alive}, Plant)
        )
        assert _type_params_issubclass(
            {"x": (Plant, (Spruce, Animal)), "y": Bear},
            {"x": (Alive, (Plant, Animal)), "y": Animal},
        )

        assert not _type_params_issubclass({"x": tuple()}, {"x": (Bear,)})
        assert not _type_params_issubclass(
            ({"x": Bear, "y": Plant},), ({"x": Bear, "y": Bear},)
        )
        assert not _type_params_issubclass(
            {"x": (Plant, (Spruce, Animal)), "y": Bear},
            {"x": (Alive, (Animal, Animal)), "y": Animal},
        )


# Now we test the full `issubclass` on actual Proxytypes


class Foo(Proxytype):
    pass


class FooChild(Foo):
    pass


class Bar(Proxytype):
    pass


class BarChild(Bar):
    pass


class Containy(GenericProxytype):
    pass


class SubContainy(Containy):
    pass


class OtherContainy(GenericProxytype):
    pass


def test_singleton_concrete_subtypes():
    assert Containy[Foo] is Containy[Foo]
    assert Containy[Bar] is Containy[Bar]
    assert Containy[Foo] is not Containy[Bar]
    assert Containy[BarChild] is not Containy[Bar]

    assert Containy[Containy[Foo]] is Containy[Containy[Foo]]
    assert OtherContainy[Containy[Foo]] is OtherContainy[Containy[Foo]]
    assert Containy[Containy[Bar]] is not SubContainy[Containy[Bar]]

    assert SubContainy[Foo] is SubContainy[Foo]
    assert SubContainy[Foo] is not Containy[Foo]

    assert Containy[Foo] is not OtherContainy[Foo]


class TestCovariantSubclass(object):
    def test_basic(self):
        assert issubclass(Proxytype, Proxytype)
        assert issubclass(GenericProxytype, GenericProxytype)
        assert issubclass(Containy, GenericProxytype)

        assert not issubclass(Bar, BarChild)
        assert not issubclass(Containy, SubContainy)
        assert not issubclass(Containy, OtherContainy)

    def test_concrete_basic(self):
        assert issubclass(Containy[Foo], Containy)
        assert issubclass(Containy[Foo], Containy[Foo])
        assert issubclass(Containy[SubContainy[Foo]], Containy[SubContainy[Foo]])
        assert issubclass(Containy[SubContainy[Foo]], Containy[SubContainy])

        assert not issubclass(Containy, Containy[Foo])
        assert not issubclass(OtherContainy[Foo], Containy[Foo])
        assert not issubclass(Containy[Foo], SubContainy[Foo])

    def test_covariance(self):
        assert issubclass(Containy[BarChild], Containy[Bar])
        assert issubclass(SubContainy[Bar], Containy[Bar])
        assert issubclass(SubContainy[BarChild], Containy[Bar])
        assert issubclass(SubContainy[BarChild], Containy)

        assert not issubclass(Containy[Bar], Containy[BarChild])
        assert not issubclass(Containy[Bar], SubContainy[Bar])
        assert not issubclass(Containy[Bar], SubContainy[BarChild])
        assert not issubclass(Containy, SubContainy[BarChild])


class CustomizedClassGetitem(GenericProxytype):
    @staticmethod
    def __class_getitem_hook__(name, bases, dct, type_params):
        dct["my_name"] = name
        dct["foo"] = type_params[0]
        dct["bar"] = type_params[1]

        return name, bases, dct


def test_class_getitem_hook():
    custom = CustomizedClassGetitem[Foo, Bar]

    assert custom.my_name == "CustomizedClassGetitem[Foo, Bar]"
    assert custom.foo is Foo
    assert custom.bar is Bar


class InitSubclasser(GenericProxytype):
    @classmethod
    def __init_subclass__(subcls):
        assert subcls is not InitSubclasser
        assert subcls.foo == "bar"
        subcls.bar = "baz"


def test_init_subclass():
    class Subclass(InitSubclasser):
        foo = "bar"

    assert Subclass.foo == "bar"  # on base
    assert Subclass.bar == "baz"  # added by __init_subclass__

    assert not hasattr(InitSubclasser, "foo")
    assert not hasattr(InitSubclasser, "bar")