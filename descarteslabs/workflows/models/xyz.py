import json
import threading

import six

import grpc
from descarteslabs.common.proto import xyz_pb2

from .. import _channel
from ..cereal import deserialize_typespec, serialize_typespec
from ..client import Client
from .utils import pb_datetime_to_milliseconds, pb_milliseconds_to_datetime


class XYZ(object):
    """
    Stores proxy objects to be rendered by an XYZ tile server.

    Similar to a `Workflow`, but meant for storing proxy objects
    so the XYZ tile service can display them, rather than for persisting
    and sharing workflows between users.

    Use `.url` to generate an XYZ URL template, and `.iter_tile_errors`
    or `.error_listener` to retrieve error messages that happen while
    computing them.
    """
    BASE_URL = "https://workflows.descarteslabs.com"

    def __init__(self, proxy_object, proto_message, client=None):
        """
        Construct a XYZ object from a proxy object and Protobuf message.

        Do not use this method directly; use the `XYZ.build` and `XYZ.get`
        classmethods instead.

        Parameters
        ----------
        proxy_object: Proxytype
            The proxy object to store in this XYZ
        proto_message: xyz_pb2.XYZ message
            Protobuf message for the XYZ
        client : Compute, optional
            Allows you to use a specific client instance with non-default
            auth and parameters
        """
        if client is None:
            client = Client()
        self._object = proxy_object
        self._message = proto_message
        self._client = client

    @classmethod
    def _from_proto(cls, message, client=None):
        typespec = json.loads(message.serialized_typespec)
        proxytype = deserialize_typespec(typespec)

        if message.serialized_graft:
            graft = json.loads(message.serialized_graft)
            obj = proxytype._from_graft(graft)
        else:
            raise AttributeError(
                (
                    "The serialized graft attribute does not exist or "
                    "acces is not authorized for XYZ '{}'. To share "
                    "objects with others, please use a Workflow instead."
                ).format(message.id)
            )

        return cls(obj, message, client=client)

    @classmethod
    def build(cls, proxy_object, name="", description="", client=None):
        """
        Construct a new XYZ from a proxy object.

        Note that this does not persist the `XYZ`,
        call `save()` on the returned `XYZ` to do that.

        Parameters
        ----------
        proxy_object: Proxytype
            The proxy object to store in this XYZ
        name: str, default ""
            Name for the new XYZ
        description: str, default ""
            Long-form description of this XYZ. Markdown is supported.
        client : Compute, optional
            Allows you to use a specific client instance with non-default
            auth and parameters

        Returns
        -------
        XYZ
        """
        typespec = serialize_typespec(type(proxy_object))
        graft = proxy_object.graft

        message = xyz_pb2.XYZ(
            name=name,
            description=description,
            serialized_graft=json.dumps(graft),
            serialized_typespec=json.dumps(typespec),
            channel=_channel.__channel__,
        )
        return cls(proxy_object, message, client=client)

    @classmethod
    def get(cls, xyz_id, client=None):
        """
        Get an existing XYZ by id.

        Parameters
        ----------
        id : string
            The unique id of a `XZY` object
        client : Compute, optional
            Allows you to use a specific client instance with non-default
            auth and parameters

        Returns
        -------
        XYZ
        """
        if client is None:
            client = Client()

        message = client.api["GetXYZ"](
            xyz_pb2.GetXYZRequest(xyz_id=xyz_id), timeout=client.DEFAULT_TIMEOUT
        )
        return cls._from_proto(message, client)

    def update(self, *args, **kwargs):
        raise NotImplementedError("XYZ.update not implemented")

    def save(self):
        """
        Persist this XYZ layer.

        After saving, ``self.id`` will contain the new ID of the XYZ layer.
        """
        message = self._client.api["CreateXYZ"](
            xyz_pb2.CreateXYZRequest(xyz=self._message),
            timeout=self._client.DEFAULT_TIMEOUT,
        )
        self._message = message

    def url(self, session_id=None, **query_args):
        """
        XYZ tile URL format-string, like ``https://workflows.descarteslabs.com/v0-5/xyz/1234567/{z}/{x}/{y}.png``

        Parameters
        ----------
        session_id: str, optional, default None
            Unique, client-generated ID that error logs will be stored under.
            Since multiple users may access tiles from the same `XYZ` object,
            each user should set their own ``session_id`` to get individual error logs.
        query_args: dict[str, str], optional, default None
            Additional query arguments to add to the URL. Keys and values must be strings.

        Returns
        -------
        url: str

        Raises
        ------
        ValueError
            If the `XYZ` object has no `id` and `.save` has not been called yet.
        """
        if self.id is None:
            raise ValueError(
                "This XYZ object has not been persisted yet; call .save() to do so."
            )
        url = "{base}/{channel}/xyz/{id}/{{z}}/{{x}}/{{y}}.png".format(
            base=self.BASE_URL, channel=self.channel, id=self.id
        )
        if session_id:
            query_args["session_id"] = session_id

        if query_args:
            url = (
                url
                + "?"
                + "&".join(
                    arg + "=" + value for arg, value in six.iteritems(query_args)
                )
            )
        return url

    def iter_tile_errors(self, session_id, start_datetime=None):
        """
        Iterator over errors generated while computing tiles

        Parameters
        ----------
        session_id: str
            Unique, client-generated that error logs are stored under.
        start_datetime: datetime.datetime
            Only return errors occuring after this datetime

        Yields
        ------
        error: descarteslabs.common.proto.xyz_pb2.XYZError
            Errors in protobuf message objects,
            with fields ``code``, ``message``, ``timestamp``, ``session_id``.
        """
        return _tile_error_stream(
            self.id, session_id, start_datetime, client=self._client
        )

    def error_listener(self):
        "An `XYZErrorListener` to trigger callbacks when errors occur computing tiles"
        return XYZErrorListener(self.id, client=self._client)

    @property
    def object(self):
        """
        Proxytype: The proxy object of this XYZ.

        Raises ValueError if the XYZ is not compatible with the current channel.
        """
        if self.channel != _channel.__channel__:
            raise ValueError(
                "This client is compatible with channel '{}', "
                "but the XYZ '{}' is only defined for channel '{}'.".format(
                    _channel.__channel__, self.id, self.channel
                )
            )
        return self._object

    @property
    def type(self):
        "type: The type of the proxy object."
        return type(self._object)

    @property
    def id(self):
        """
        str or None: The globally unique identifier for the XYZ,
        or None if it hasn't been saved yet.
        """
        return None if self._message.id == "" else self._message.id

    @property
    def created_timestamp(self):
        """
        datetime.datetime or None: The UTC date this XYZ was created,
        or None if it hasn't been saved yet. Cannot be modified.
        """
        return pb_milliseconds_to_datetime(self._message.created_timestamp)

    @property
    def updated_timestamp(self):
        """
        datetime.datetime or None: The UTC date this XYZ was most recently modified,
        or None if it hasn't been saved yet. Updated automatically.
        """
        return pb_milliseconds_to_datetime(self._message.updated_timestamp)

    @property
    def name(self):
        "str: The name of this XYZ."
        return self._message.name

    @property
    def description(self):
        "str: A long-form description of this xyz. Markdown is supported."
        return self._message.description

    @property
    def channel(self):
        "str: The channel name this XYZ is compatible with."
        return self._message.channel

    @property
    def owners(self):
        raise NotImplementedError("ACLs are not yet supported for XYZs")

    @property
    def readers(self):
        raise NotImplementedError("ACLs are not yet supported for XYZs")

    @property
    def writers(self):
        raise NotImplementedError("ACLs are not yet supported for XYZs")


class XYZErrorListener(object):
    """
    Calls callback functions in a background thread when XYZ errors occur.

    Note: the thread is automatically cleaned up on garbage collection.

    Example
    -------
    >>> xyz = wf.XYZ.build(wf.Image.from_id("landsat:LC08:PRE:TOAR:meta_LC80270312016188_v1"))
    >>> xyz.save()  # doctest: +SKIP
    >>> listener = xyz.error_listener()
    >>> listener.add_callback(lambda msg: print(msg.code, msg.message))
    >>> listener.listen("my_session_id", start_datetime=datetime.datetime.now())  # doctest: +SKIP
    >>> # later
    >>> listener.stop()  # doctest: +SKIP
    """
    def __init__(self, xyz_id, client=None):
        self.xyz_id = xyz_id
        self.callbacks = []
        self._rendezvous = None
        self._thread = None
        self._client = client if client is not None else Client()

    def add_callback(self, callback):
        """
        Function will be called with ``descarteslabs.common.proto.xyz_pb2.XYZError`` on each error.

        Parameters
        ----------
        callback: callable
            Function that takes one argument, a ``descarteslabs.common.proto.xyz_pb2.XYZError``
            protobuf message object. This message contains the fields ``code``, ``message``,
            ``timestamp``, ``session_id``.

            The function will be called within a separate thread,
            therefore it must behave thread-safely. Any errors raised by the function will
            terminate the listener.
        """
        self.callbacks.append(callback)

    def listen(self, session_id, start_datetime=None):
        """
        Start listening for errors.

        Parameters
        ----------
        session_id: str
            Unique, client-generated ID that error logs are stored under.
            See `XYZ.url` for more information.
        start_datetime: datetime.datetime
            Only listen for errors occuring after this datetime.
        """
        self._rendezvous = _tile_error_stream(
            self.xyz_id, session_id, start_datetime=start_datetime, client=self._client
        )
        self._thread = threading.Thread(target=self._listener)
        self._thread.daemon = True
        self._thread.start()

    def running(self):
        "bool: whether this is an active listener"
        return self._thread and self._thread.is_alive()

    def stop(self, timeout=None):
        """
        Cancel and clean up the listener. Blocks up to ``timeout`` seconds, or forever if None.

        Returns True if the background thread stopped successfully.
        """
        self._rendezvous.cancel()
        self._thread.join(timeout)
        return not self._thread.is_alive()

    def _listener(self):
        try:
            for msg in self._rendezvous:
                for callback in self.callbacks:
                    callback(msg)
        except grpc.RpcError:
            return

    def __del__(self):
        if self.running():
            self.stop(0)


def _tile_error_stream(xyz_id, session_id, start_datetime=None, client=None):
    if client is None:
        client = Client()

    if start_datetime is None:
        start_timestamp = 0
    else:
        start_timestamp = pb_datetime_to_milliseconds(start_datetime)

    msg = xyz_pb2.GetXYZSessionErrorsRequest(
        session_id=session_id, xyz_id=xyz_id, start_timestamp=start_timestamp
    )
    return client.api["GetXYZSessionErrors"](msg)