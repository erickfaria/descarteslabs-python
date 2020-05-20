from google.protobuf.descriptor import FieldDescriptor

from descarteslabs.common.proto.formats import formats_pb2


def cast_bool(value):
    if isinstance(value, bool):
        return value
    else:
        value = value.lower()
        assert value in ("true", "false", "1", "0")
        cast_value = value == "true" or value == "1"
        return cast_value


proto_field_type_to_python_type = {
    FieldDescriptor.TYPE_DOUBLE: float,
    FieldDescriptor.TYPE_FLOAT: float,
    FieldDescriptor.TYPE_INT64: int,
    FieldDescriptor.TYPE_UINT64: int,
    FieldDescriptor.TYPE_INT32: int,
    FieldDescriptor.TYPE_BOOL: cast_bool,
    FieldDescriptor.TYPE_STRING: str,
    FieldDescriptor.TYPE_UINT32: int,
    FieldDescriptor.TYPE_ENUM: str,
}
# ^ A mapping from proto TYPE_* value to python type (only includes the ones we need)
# https://github.com/protocolbuffers/protobuf/blob/master/python/google/protobuf/descriptor.py#L461-L479


mimetype_to_type = {
    field_descriptor.GetOptions().Extensions[formats_pb2.mimetype]: getattr(
        formats_pb2, field_descriptor.message_type.name
    )
    for field_name, field_descriptor in formats_pb2.Format.DESCRIPTOR.fields_by_name.items()
    if not field_name.startswith("has_")
}


format_name_to_type = {
    field_name: getattr(formats_pb2, field_descriptor.message_type.name)
    for field_name, field_descriptor in formats_pb2.Format.DESCRIPTOR.fields_by_name.items()
    if not field_name.startswith("has_")
}


message_type_to_field_names_and_types = {
    getattr(formats_pb2, message_name): {
        field_name: proto_field_type_to_python_type[field_descriptor.type]
        for field_name, field_descriptor in message_descriptor.fields_by_name.items()
    }
    for message_name, message_descriptor in formats_pb2.DESCRIPTOR.message_types_by_name.items()
    if not message_name == "Format"
}


def mimetype_to_proto(mimetype: str) -> formats_pb2.Format:
    type_str, *params = mimetype.split(";")
    try:
        proto_type = mimetype_to_type[type_str]
    except KeyError:
        raise ValueError(
            "Unknown MIME type {}. Must be one of: {}".format(
                type_str, list(mimetype_to_type)
            )
        )

    parsed_params = {}
    for p in params:
        try:
            key, value = p.strip().split("=")
            parsed_params[key] = value
        except ValueError:
            raise ValueError(
                "Invalid MIME type {}. If the final character in your MIME type is a semicolon, remove it.".format(
                    mimetype
                )
            )

    return user_format_options_to_proto(proto_type, parsed_params)


def user_format_to_proto(format_: dict) -> formats_pb2.Format:
    # Classic dictionary mutation
    format_copy = format_.copy()
    try:
        format_name = format_copy.pop("type")
    except KeyError:
        raise ValueError(
            "The format dictionary must include a serialization type "
            "(like `'type': 'json'`), but key 'type' does not exist."
        )

    try:
        proto_type = format_name_to_type[format_name]
    except KeyError:
        raise ValueError(
            "Unknown format {!r}. Must be one of: {}".format(
                format_name, list(format_name_to_type)
            )
        )

    return user_format_options_to_proto(proto_type, format_copy)


def user_format_options_to_proto(proto_type: type, params: dict) -> formats_pb2.Format:
    field_name = proto_type.__name__.lower()
    fields_to_types = message_type_to_field_names_and_types[proto_type]

    proto_params = {}
    for key, value in params.items():
        not_key = False
        try:
            cast_func = fields_to_types[key]
        except KeyError:
            try:
                cast_func = fields_to_types["not_" + key]
                not_key = True
            except KeyError:
                raise ValueError(
                    "Unsupported parameter '{}' for format '{}'. For supported parameters, "
                    "see the {} protobuf message at "
                    "https://github.com/descarteslabs/descarteslabs-python/blob/master/descarteslabs/common/proto/formats/formats.proto".format(  # noqa
                        key, field_name, proto_type.__name__
                    )
                ) from None

        try:
            cast_value = cast_func(value)
        except (AssertionError, ValueError, AttributeError):
            raise ValueError(
                "Parameter {!r} must be castable to {}, but it was not.".format(
                    key, cast_func.__name__
                )
            )

        if not_key:
            proto_params["not_" + key] = not cast_value
        else:
            proto_params[key] = cast_value

    specific_format = proto_type(**proto_params)

    return formats_pb2.Format(
        **{field_name: specific_format, "has_" + field_name: True}
    )


def format_proto_to_user_facing_format(format_: formats_pb2.Format) -> dict:
    output_format = {}
    if format_.has_pyarrow:
        specific_format = format_.pyarrow
        type_ = "pyarrow"
    elif format_.has_json:
        specific_format = format_.json
        type_ = "json"
    elif format_.has_geojson:
        raise NotImplementedError
    elif format_.has_csv:
        raise NotImplementedError
    elif format_.has_png:
        raise NotImplementedError
    elif format_.has_geotiff:
        specific_format = format_.geotiff
        type_ = "geotiff"
    elif format_.has_msgpack:
        specific_format = format_.msgpack
        type_ = "msgpack"
    else:
        raise ValueError("Invalid Format protobuf: none of the has_ values are set.")

    fields_to_types = message_type_to_field_names_and_types[type(specific_format)]

    output_format["type"] = type_
    for key, field_type in fields_to_types.items():
        val = getattr(specific_format, key)

        if key.startswith("not_"):
            key = key.split("_")[1]
            val = not val

        if field_type is str and isinstance(val, int):
            # Could be a enum or string
            # We try coverting it to an enum value
            enum = key.capitalize()
            try:
                val = getattr(specific_format, enum).Name(val)
            except AttributeError:
                pass

        output_format[key] = val

    return output_format
