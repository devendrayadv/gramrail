"""Stable errors shared by the library, HTTP API, and CLI."""

class RailError(Exception):
    code = "invalid_request"
    status = 400


class NotFound(RailError):
    code = "not_found"
    status = 404


class Conflict(RailError):
    code = "conflict"
    status = 409


class Forbidden(RailError):
    code = "forbidden"
    status = 403


class LeaseLost(Conflict):
    code = "lease_lost"


class InvalidInput(RailError):
    code = "invalid_input"
