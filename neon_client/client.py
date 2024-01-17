import os

# from collections.abc import Sequence

import requests
from pydantic import BaseModel

from . import schema

import typing as t


__VERSION__ = "0.1.0"

NEON_API_KEY_ENVIRON = "NEON_API_KEY"
NEON_API_BASE_URL = "https://console.neon.tech/api/v2/"


def compact_mapping(obj):
    """Compact a mapping by removing None values."""

    return {k: v for k, v in obj.items() if v is not None}


class NeonClientException(requests.exceptions.HTTPError):
    pass


class NeonResource:
    def __init__(
        self,
        client,
        obj,
        data_model: BaseModel,
    ):
        """A Neon API key.

        Args:
            client (NeonAPI): The Neon API client.
            obj (dict): The API key data.
            data_model (BaseModel, optional): The data model to use for deserialization. Defaults to None.
        """
        self._client = client
        self._data = obj
        self._data_model = data_model
        self.__cached_obj = None

    @property
    def obj(self):
        """The API key object."""

        if not self.__cached_obj:
            self.__cached_obj = self._data_model.model_construct(**self._data)

        return self.__cached_obj

    def __getattribute__(self, name):
        """Get an attribute from the API key object or the API key data."""

        try:
            return super().__getattribute__(name)
        except AttributeError:
            return getattr(self.obj, name)

    def __getitem__(self, key):
        """Get an item from the API key object or the API key data."""

        return getattr(self.obj, key, None) or self.obj[key]

    def __repr__(self):
        """Return a string representation of the API key."""

        return repr(self.obj)


class APIKey(NeonResource):
    """A Neon API key."""

    @classmethod
    def create(cls, client, key_name: str):
        """Create a new API key."""

        obj = schema.ApiKeyCreateRequest(key_name=key_name)
        r = client.request("POST", "api_keys", json=obj.model_dump())

        return cls(client=client, obj=r, data_model=schema.ApiKeyCreateResponse)

    @classmethod
    def list(cls, client):
        """Get a list of API keys."""

        r = client.request("GET", "api_keys")
        return [
            cls(client=client, obj=x, data_model=schema.ApiKeysListResponseItem)
            for x in r
        ]

    @classmethod
    def revoke_request(cls, client, api_key):
        """Revoke an API key."""

        r = client.request("DELETE", f"api_keys/{ api_key.obj.id }")

        return cls(client=client, obj=r, data_model=schema.ApiKeyRevokeResponse)

    def revoke(self):
        """Revoke the API key."""

        return self.revoke_request(self._client, self)


class User(NeonResource):
    """A Neon user."""

    @classmethod
    def get_current_user_info(cls, client):
        """Get the current user."""

        r = client.request("GET", "users/me")

        return cls(
            client=client,
            obj=r,
            data_model=schema.CurrentUserInfoResponse,
        )


class Project(NeonResource):
    @classmethod
    def list(
        cls,
        client,
        *,
        shared: bool = False,
        cursor: int | None = None,
        limit: int | None = None,
    ):
        """Get a list of projects."""

        r_path = "projects" if not shared else "projects/shared"
        r_params = {"cursor": cursor, "limit": limit}

        r = client.request("GET", r_path, params=r_params)

        return [
            cls(client=client, obj=x, data_model=schema.ProjectListItem)
            for x in r["projects"]
        ]


class Branch(NeonResource):
    @classmethod
    def list(
        cls,
        client,
        project_id: str,
        *,
        cursor: int | None = None,
        limit: int | None = None,
    ):
        """Get a list of projects."""

        r_path = "/".join(["projects", project_id, "branches"])
        r_params = compact_mapping({"cursor": cursor, "limit": limit})

        # Make the request.
        r = client.request("GET", r_path, params=r_params)

        return [
            cls(client=client, obj=x, data_model=schema.ProjectListItem)
            for x in r["branches"]
        ]

    @classmethod
    def create(
        cls,
        client,
        project_id: str,
        *,
        endpoints: t.List[schema.BranchCreateRequestEndpointOptions] | None = None,
        branch: schema.Branch2 | None = None,
        **kwargs,
    ):
        """Create a new branch."""

        # Construct the request object.
        kwargs.setdefault("endpoints", endpoints)
        kwargs.setdefault("branch", branch)

        # Validate and prepare the request body.
        obj = schema.BranchCreateRequest(**kwargs)

        # Make the request.
        r_path = client.url_join("projects", project_id, "branches")

        if obj.endpoints or obj.branch:
            r = client.request("POST", r_path, json=obj.model_dump())
        else:
            r = client.request("POST", r_path)

        return cls(client=client, obj=r, data_model=schema.BranchResponse)


class Operation(NeonResource):
    pass


class NeonAPI:
    def __init__(self, api_key: str, *, base_url=None):
        """A Neon API client."""

        if not base_url:
            base_url = NEON_API_BASE_URL

        # Private attributes.
        self._api_key = api_key
        self._session = requests.Session()

        # Public attributes.
        self.base_url = base_url
        self.user_agent = f"neon-client/{__VERSION__}"

    def __repr__(self):
        return f"<NeonAPI base_url={self.base_url!r}>"

    def request(self, method: str, path: str, **kwargs):
        """Send an HTTP request to the specified path using the specified method."""

        # Set HTTP headers for outgoing requests.
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {self._api_key}"
        headers["Accept"] = "application/json"
        headers["Content-Type"] = "application/json"
        headers["User-Agent"] = self.user_agent

        # Send the request.
        r = self._session.request(
            method, self.base_url + path, headers=headers, **kwargs
        )

        # Check the response status code.
        try:
            r.raise_for_status()
        except requests.exceptions.HTTPError:
            raise NeonClientException(r.text)

        # Deserialize the response.
        return r.json()

    def url_join(self, *args):
        """Join multiple URL path components."""

        return "/".join(args)

    @classmethod
    def from_environ(cls):
        """Create a new Neon API client from the NEON_API_KEY environment variable."""

        return cls(os.environ[NEON_API_KEY_ENVIRON])

    def me(self):
        """Get the current user."""
        return User.get_current_user_info(client=self)

    def api_keys(self):
        """Get a list of API keys."""
        return APIKey.list(client=self)
